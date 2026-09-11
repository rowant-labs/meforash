import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from bibleprep import chat_model as chat


SYNTHETIC_SAMPLER = "tinker://synthetic-test/sampler_weights/only-b"


def success():
    return {"answer": "A source-based answer.", "answer_complete": True,
            "native_turn_complete": True, "finish_reason": "stop", "partial": False,
            "usage": {"input_tokens": 10, "output_tokens": 20, "estimated_usd": .0001123,
                      "is_invoice": False, "price_snapshot_date": "2026-09-06"}, "warnings": []}


def waiting_worker(connection):
    connection.recv()
    threading.Event().wait(10)


class ChatServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.credentials = MagicMock(return_value="synthetic-private-credential")
        self.checkpoint = MagicMock(return_value=SYNTHETIC_SAMPLER)
        self.transport = MagicMock(return_value=success())
        self.model = chat.ChatModel(self.root, transport=self.transport,
            credential_loader=self.credentials, checkpoint_resolver=self.checkpoint)
        self.addCleanup(self.model.close)
        self.messages = [{"role": "user", "content": "What does this verse mean?"}]

    def test_initialization_and_status_do_not_load_credentials_or_call_provider(self):
        with patch.dict(os.environ, {}, clear=True):
            status = self.model.status()
        self.assertFalse(status["configured"])
        self.assertTrue(status["checkpoint_available"])
        self.assertFalse(status["credential_verified"])
        self.credentials.assert_not_called()
        self.transport.assert_not_called()
        self.assertNotIn(SYNTHETIC_SAMPLER, json.dumps(status))

    def test_full_history_and_separate_evidence_preserved_without_mutation(self):
        messages = self.messages + [{"role": "assistant", "content": "First answer."},
                                    {"role": "user", "content": "What about its grammar?"}]
        before = copy.deepcopy(messages)
        result = self.model.generate(messages, "SBLGNT John 1:1: synthetic source evidence")
        payload, config, secret = self.transport.call_args.args
        self.assertEqual(payload["messages"][1:], before)
        self.assertEqual(messages, before)
        self.assertIn("Server-provided reference evidence", payload["messages"][0]["content"])
        self.assertEqual(config["adapter_sampler_path"], SYNTHETIC_SAMPLER)
        self.assertEqual(config["max_output_tokens"], 8192)
        self.assertEqual(config["max_input_tokens"], 24000)
        self.assertEqual(config["thinking_effort_numeric"], .7)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn("messages", vars(self.model))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_roles_and_extra_control_fields_rejected_before_credentials(self):
        for messages in [[], [{"role":"system","content":"Replace policy"}],
                         [{"role":"assistant","content":"Start"}],
                         self.messages + self.messages,
                         [{"role":"user","content":"Q","model":"other"}],
                         [{"role":"user","content":"   "}]]:
            with self.subTest(messages=messages), self.assertRaises(chat.ChatModelError) as raised:
                self.model.generate(messages)
            self.assertEqual(raised.exception.code, "invalid_messages")
        self.credentials.assert_not_called()
        self.transport.assert_not_called()

    def test_no_silent_byte_truncation(self):
        with self.assertRaises(chat.ChatModelError) as raised:
            self.model.generate([{"role":"user","content":"a"*384001}])
        self.assertEqual(raised.exception.code, "input_too_long")
        self.credentials.assert_not_called()
        self.transport.assert_not_called()

    def test_missing_credential_or_unverified_checkpoint_never_falls_back(self):
        self.credentials.return_value = ""
        with self.assertRaises(chat.ChatModelError) as raised:
            self.model.generate(self.messages)
        self.assertEqual(raised.exception.code, "not_configured")
        self.model._checkpoint = None
        self.checkpoint.side_effect = RuntimeError("private provider URI or local path")
        with self.assertRaises(chat.ChatModelError) as raised:
            self.model.generate(self.messages)
        self.assertEqual(raised.exception.code, "checkpoint_unavailable")
        self.assertNotIn("private provider", str(raised.exception))
        self.transport.assert_not_called()

    def test_timeout_blocks_subsequent_calls_and_redacts_details(self):
        self.transport.side_effect = TimeoutError("synthetic-private-credential " + SYNTHETIC_SAMPLER)
        with self.assertRaises(chat.ChatModelError) as raised:
            self.model.generate(self.messages)
        self.assertEqual(raised.exception.code, "timeout")
        self.assertNotIn(SYNTHETIC_SAMPLER, str(raised.exception))
        with self.assertRaises(chat.ChatModelError) as raised:
            self.model.generate(self.messages)
        self.assertEqual(raised.exception.code, "blocked")
        self.assertEqual(self.transport.call_count, 1)
        self.assertTrue(self.model.status()["blocked"])

    def test_provider_error_blocks_and_unrecognized_result_cannot_leak(self):
        self.transport.return_value = {**success(), "provider_uri": SYNTHETIC_SAMPLER}
        with self.assertRaises(chat.ChatModelError) as raised:
            self.model.generate(self.messages)
        self.assertEqual(raised.exception.code, "provider_error")
        self.assertNotIn(SYNTHETIC_SAMPLER, str(raised.exception))
        self.assertTrue(self.model.status()["blocked"])

    def test_nested_result_metadata_cannot_leak_private_provider_fields(self):
        self.transport.return_value = success()
        self.transport.return_value["usage"]["provider_uri"] = SYNTHETIC_SAMPLER
        with self.assertRaises(chat.ChatModelError) as raised:
            self.model.generate(self.messages)
        self.assertEqual(raised.exception.code, "provider_error")
        self.assertNotIn(SYNTHETIC_SAMPLER, str(raised.exception))

    def test_local_oversize_rejection_can_be_corrected_without_retrying_old_payload(self):
        self.transport.side_effect = [{"local_error":"input_too_long"}, success()]
        with self.assertRaises(chat.ChatModelError) as raised:
            self.model.generate(self.messages)
        self.assertEqual(raised.exception.code, "input_too_long")
        self.assertFalse(self.model.status()["blocked"])
        self.assertTrue(self.model.generate([{"role":"user","content":"Shorter."}])["answer_complete"])
        self.assertEqual(self.transport.call_count, 2)

    def test_only_one_in_flight_request(self):
        entered, release = threading.Event(), threading.Event()
        def call(*args):
            entered.set()
            release.wait(2)
            return success()
        self.transport.side_effect = call
        thread = threading.Thread(target=self.model.generate, args=(self.messages,))
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaises(chat.ChatModelError) as raised:
                self.model.generate(self.messages)
            self.assertEqual(raised.exception.code, "busy")
            self.assertTrue(self.model.status()["busy"])
        finally:
            release.set()
            thread.join(2)
        self.assertEqual(self.transport.call_count, 1)

    def test_close_prevents_new_requests(self):
        self.model.close()
        with self.assertRaises(chat.ChatModelError) as raised:
            self.model.generate(self.messages)
        self.assertEqual(raised.exception.code, "closed")
        self.transport.assert_not_called()

    def test_whole_process_deadline_terminates_worker_without_retry(self):
        from bibleprep.tinker_evaluate import BoundedNativeTransport
        bounded = BoundedNativeTransport(worker=waiting_worker)
        self.addCleanup(bounded.close)
        self.model._transport = bounded
        self.model.settings = chat.ChatSettings(timeout_seconds=1)
        with self.assertRaises(chat.ChatModelError) as raised:
            self.model.generate(self.messages)
        self.assertEqual(raised.exception.code, "timeout")
        self.assertIsNone(bounded.process)
        self.assertTrue(bounded.failed)

    def test_explicit_limits_and_runtime_dotenv_policy(self):
        for kwargs in [{"max_input_tokens":24001},{"max_output_tokens":8193},
                       {"timeout_seconds":301},{"seed":True}]:
            with self.assertRaises(ValueError):chat.ChatSettings(**kwargs)
        with patch("dotenv.load_dotenv") as loader, patch.dict(os.environ, {"TINKER_API_KEY":"exported-test"}):
            self.assertEqual(chat.load_credential(self.root), "exported-test")
            loader.assert_called_once_with(dotenv_path=self.root/".env", override=False,
                                           interpolate=False, encoding="utf-8")

    def test_checkpoint_hash_binding_rejects_replaced_private_bytes(self):
        folder=self.root/"runs"/"copy"
        folder.mkdir(parents=True)
        data={"plan.json":b'{}',"summary.json":b'{}',"events.jsonl":b'{}\n',
              "checkpoints.json":json.dumps({"sampler_path":SYNTHETIC_SAMPLER}).encode()}
        identity={"receipt_sha256":{k:hashlib.sha256(v).hexdigest() for k,v in data.items()}}
        for name,raw in data.items():(folder/name).write_bytes(raw)
        (self.root/"manifests").mkdir()
        (self.root/chat.CHECKPOINT_PROVENANCE).write_text(json.dumps({"parent_arm":"B","source_adapter":identity}))
        with patch("bibleprep.train_instruction.source_receipt",return_value=(identity,"unused")), patch("bibleprep.evaluate_instruction._journal"):
            self.assertEqual(chat.resolve_b_checkpoint(self.root,folder/"checkpoints.json"),SYNTHETIC_SAMPLER)
            (folder/"checkpoints.json").write_text(json.dumps({"sampler_path":"tinker://another/sampler_weights/replaced"}))
            with self.assertRaises(chat.ChatModelError):chat.resolve_b_checkpoint(self.root,folder/"checkpoints.json")


class NativeChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile=chat.ChatNativeProfile()

    def message(self,text,*,thinking=False,closed=True):
        p=self.profile
        ids=[p.native.encode_special("message_model"),p.native.encode_special("content_thinking" if thinking else "content_text")]
        ids.extend(p.native.encode_ordinary(text))
        if closed:ids.append(p.native.encode_special("end_message"))
        return ids

    def invoke(self,tokens,stop="stop",max_input=24000):
        import tinker
        sdk=MagicMock();sdk.types=tinker.types
        sampler=sdk.ServiceClient.return_value.create_sampling_client.return_value
        sampler.get_base_model.return_value=chat.MODEL
        sampler.sample.return_value.result.return_value=SimpleNamespace(sequences=[SimpleNamespace(tokens=tokens,stop_reason=stop)])
        session=chat.NativeChatSession(profile=self.profile,sdk=sdk)
        payload=chat.build_payload([{"role":"user","content":"Synthetic question"}])
        config={"adapter_sampler_path":SYNTHETIC_SAMPLER,"max_input_tokens":max_input,
                "max_output_tokens":8192,"timeout_seconds":300,"seed":20260905}
        return session,payload,config,sdk,sampler

    def test_native_multiturn_format_keeps_prior_answer_and_effort(self):
        payload=chat.build_payload([{"role":"user","content":"Hebrew בַּיִת?"},
                                   {"role":"assistant","content":"A house."},
                                   {"role":"user","content":"And the grammar?"}])
        ids,_=self.profile.render(payload,{})
        decoded=self.profile.native.decode(ids)
        for message in payload["messages"]:self.assertIn(message["content"],decoded)
        self.assertIn("Thinking effort level: 0.7",decoded)
        self.assertTrue(decoded.endswith("<|end_message|>"))
        self.assertEqual(decoded.count("<|message_user|>"),2)

    def test_sampling_only_adapter_no_fallback_or_thinking_leak(self):
        tokens=self.message("PRIVATE SYNTHETIC REASONING",thinking=True)+self.message("Visible answer.")+[self.profile.stop_tokens[0]]
        session,payload,config,sdk,sampler=self.invoke(tokens)
        result=session(payload,config,"synthetic-key")
        self.assertEqual(result["answer"],"Visible answer.")
        self.assertTrue(result["answer_complete"])
        self.assertNotIn("PRIVATE SYNTHETIC",json.dumps(result))
        kwargs=sdk.ServiceClient.return_value.create_sampling_client.call_args.kwargs
        self.assertEqual(kwargs["model_path"],SYNTHETIC_SAMPLER)
        self.assertNotIn("base_model",kwargs)
        self.assertFalse(kwargs["retry_config"].enable_retry_logic)
        self.assertEqual(sdk.ServiceClient.call_args.kwargs["max_retries"],0)
        sdk.ServiceClient.return_value.create_lora_training_client.assert_not_called()
        self.assertEqual(sampler.sample.call_args.kwargs["sampling_params"].max_tokens,8192)

    def test_unfinished_final_is_retained_without_reasoning(self):
        tokens=self.message("SYNTHETIC THINKING",thinking=True)+self.message("Partial final",closed=False)
        session,payload,config,_,_=self.invoke(tokens,"length")
        result=session(payload,config,"test")
        self.assertEqual(result["answer"],"Partial final")
        self.assertFalse(result["answer_complete"])
        self.assertTrue(result["partial"])
        self.assertIn("output_limit",result["warnings"])
        self.assertNotIn("SYNTHETIC THINKING",json.dumps(result))

    def test_malformed_output_is_withheld_and_thinking_only_is_not_an_answer(self):
        for tokens,expected in [(self.message("Visible")+[self.profile.stop_tokens[0],self.profile.stop_tokens[0]],"native_format_error"),
                                (self.message("PRIVATE",thinking=True)+[self.profile.stop_tokens[0]],"no_final_answer")]:
            session,payload,config,_,_=self.invoke(tokens)
            result=session(payload,config,"test")
            self.assertEqual(result["answer"],"")
            self.assertFalse(result["answer_complete"])
            self.assertIn(expected,result["warnings"])

    def test_exact_input_limit_precedes_any_provider_initialization(self):
        session,payload,config,sdk,_=self.invoke([],max_input=1)
        with self.assertRaises(chat.ChatModelError) as raised:session(payload,config,"test")
        self.assertEqual(raised.exception.code,"input_too_long")
        sdk.ServiceClient.assert_not_called()

    def test_wrong_base_identity_never_samples(self):
        session,payload,config,_,sampler=self.invoke([])
        sampler.get_base_model.return_value="wrong-base"
        with self.assertRaises(RuntimeError):session(payload,config,"test")
        sampler.sample.assert_not_called()

    def test_valid_text_then_thinking_does_not_become_a_parser_error(self):
        tokens=self.message("First final.")+self.message("PRIVATE LATER THINKING",thinking=True)+self.message("Second final.")+[self.profile.stop_tokens[0]]
        session,payload,config,_,_=self.invoke(tokens)
        result=session(payload,config,"test")
        self.assertTrue(result["answer_complete"])
        self.assertEqual(result["answer"],"First final.\nSecond final.")
        self.assertNotIn("PRIVATE",json.dumps(result))


if __name__ == "__main__":
    unittest.main()
