import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from bibleprep import evaluate as ev
from bibleprep import tinker_evaluate as te


def waiting_worker(connection):
    connection.recv()
    time.sleep(10)


def reply_worker(connection):
    payload, config, secret = connection.recv()
    connection.send({"ok": True, "response": {"choices": [], "fixture": payload["fixture"]}})
    connection.close()


class HarmonyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Pinned local assets only. No provider SDK client or key is used.
        cls.tokenizer = te.load_pinned_tokenizer()

    def parse(self, text, stop="stop"):
        return te.parse_harmony(te.token_ids(self.tokenizer, text), self.tokenizer, stop)

    def test_analysis_and_final_are_separate(self):
        result = self.parse("<|channel|>analysis<|message|>Private reasoning.<|end|>"
                            "<|start|>assistant<|channel|>final<|message|>Visible answer.<|return|>")
        self.assertEqual(result["content"], "Visible answer.")
        self.assertEqual(result["finish_reason"], "stop")
        self.assertGreater(result["analysis_content_tokens"], 0)
        self.assertNotIn("Private reasoning", json.dumps(result))

    def test_truncated_analysis_never_becomes_an_answer(self):
        result = self.parse("<|channel|>analysis<|message|>Still thinking", "length")
        self.assertEqual(result["content"], "")
        self.assertEqual(result["finish_reason"], "length")

    def test_partial_final_remains_incomplete(self):
        result = self.parse("<|channel|>final<|message|>Partial answer", "length")
        self.assertEqual(result["content"], "Partial answer")
        self.assertEqual(result["finish_reason"], "length")
        self.assertFalse(result["turn_end_observed"])

    def test_plain_text_without_channel_is_not_assumed_final(self):
        result = self.parse("An answer without its Harmony channel.")
        self.assertEqual(result["content"], "")
        self.assertEqual(result["finish_reason"], "incomplete_harmony")

    def test_tool_call_and_malformed_extra_turn_never_complete(self):
        tool = self.parse(" to=functions.lookup<|channel|>commentary<|message|>{}<|call|>")
        self.assertEqual(tool["finish_reason"], "tool_calls")
        extra = self.parse("<|channel|>final<|message|>Answer<|return|>extra")
        self.assertEqual(extra["finish_reason"], "incomplete_harmony")

    def test_template_sets_reasoning_date_and_preserves_rubric_allowlist(self):
        config = {"reasoning_effort": "low", "prompt_date": "2001-02-03"}
        payload = {"messages": [{"role": "system", "content": "Policy"},
                                {"role": "user", "content": "Explain λόγος."}],
                   "gold_answer": "must not be sent"}
        rendered, ids = te.render_prompt(payload, config, self.tokenizer)
        self.assertIn("Reasoning: low", rendered)
        self.assertIn("Current date: 2001-02-03", rendered)
        self.assertIn("<|start|>developer", rendered)
        self.assertIn("λόγος", rendered)
        self.assertNotIn("must not be sent", rendered)
        self.assertEqual(ids, te.token_ids(self.tokenizer, rendered))

    def test_complete_vocabulary_and_unicode_parity_is_checked(self):
        report = te.assert_tokenizer_parity(self.tokenizer, self.tokenizer)
        self.assertTrue(report["all_prompt_token_ids_compared"])
        fake = Mock(wraps=self.tokenizer)
        fake.get_vocab.return_value = {"different": 1}
        with self.assertRaises(ev.EvaluationError):
            te.assert_tokenizer_parity(self.tokenizer, fake)
        fake = Mock(wraps=self.tokenizer)
        fake.encode.return_value = [1]
        with self.assertRaises(ev.EvaluationError):
            te.assert_tokenizer_parity(self.tokenizer, fake)

    def test_native_response_accounts_exact_tokens_and_does_not_fabricate_invoice(self):
        transport = te.NativeTransport()
        generated = te.token_ids(self.tokenizer,
                                "<|channel|>analysis<|message|>Think.<|end|>"
                                "<|start|>assistant<|channel|>final<|message|>Answer.<|return|>")
        output = SimpleNamespace(sequences=[SimpleNamespace(tokens=generated, stop_reason="stop")],
                                 prompt_cache_hit_tokens=0)
        transport.sampler = Mock()
        transport.sampler.sample.return_value.result.return_value = output
        transport.pinned = transport.live = self.tokenizer
        transport.base_model = "openai/gpt-oss-120b"
        transport.parity = {"fixture": True}
        transport.types = SimpleNamespace(SamplingParams=lambda **kwargs: kwargs,
                                          ModelInput=SimpleNamespace(from_ints=lambda tokens: tokens))
        config = {"max_input_tokens": 6000, "max_output_tokens": 4096, "timeout_seconds": 1,
                  "temperature": 0.0, "seed": 3, "reasoning_effort": "low", "prompt_date": "2001-02-03",
                  "accounting_source": "submitted_prompt_and_returned_sequence_token_counts"}
        payload = {"messages": [{"role": "user", "content": "Hello"}]}
        response = transport(payload, config, "not-a-real-key")
        self.assertEqual(response["usage"]["completion_tokens"], len(generated))
        self.assertEqual(response["usage"]["prompt_tokens"], len(te.render_prompt(payload, config, self.tokenizer)[1]))
        self.assertFalse(response["native_tinker"]["accounting_is_invoice"])
        self.assertNotIn("Think.", json.dumps(response))
        request = transport.sampler.sample.call_args.kwargs
        self.assertEqual(request["sampling_params"]["max_tokens"], 4096)
        self.assertEqual(request["sampling_params"]["stop"],
                         [te.token_ids(self.tokenizer, marker)[0] for marker in ("<|return|>", "<|call|>")])


class TinkerRunTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = vars(te.parser().parse_args([]))
        self.config.pop("execute")
        self.config.pop("resume")
        self.config.update(run_dir=str(self.root / "runs/run"), max_cases=1)
        patcher = patch.object(ev, "RUNS_ROOT", self.root / "runs")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dry_run_has_no_sdk_initialization_key_read_or_network(self):
        with patch.object(te.NativeTransport, "initialize") as initialize, \
                patch.object(ev, "load_project_environment") as environment, \
                patch.dict(os.environ, {}, clear=True):
            result = te.run(self.config)
        initialize.assert_not_called()
        environment.assert_not_called()
        self.assertEqual(result["mode"], "dry_run")
        manifest = json.loads((Path(self.config["run_dir"]) / "manifest.json").read_text())
        self.assertEqual(manifest["settings"]["transport"], "native_tinker")
        self.assertEqual(manifest["settings"]["reasoning_effort"], "low")
        self.assertFalse(manifest["settings"]["accounting_is_invoice"])

    def test_execution_requires_prices_and_budget_before_sdk(self):
        with patch.object(te.NativeTransport, "initialize") as initialize:
            with self.assertRaises(ev.EvaluationError):
                te.run(self.config, execute=True)
        initialize.assert_not_called()

    def test_pinned_asset_changes_are_rejected(self):
        with patch.object(te.ev, "digest", return_value="changed"):
            with self.assertRaises(ev.EvaluationError):
                te.local_identity()

    def test_unverified_model_or_endpoint_is_rejected(self):
        self.config["model"] = "unknown-model"
        with self.assertRaises(ev.EvaluationError):
            te.run(self.config)
        self.config["model"] = "openai/gpt-oss-120b"
        self.config["base_url"] = "https://elsewhere.invalid"
        with self.assertRaises(ev.EvaluationError):
            te.run(self.config)

    def test_whole_request_deadline_terminates_worker_and_refuses_retry(self):
        transport = te.BoundedNativeTransport(worker=waiting_worker)
        self.addCleanup(transport.close)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            transport({}, {"timeout_seconds": 0.2}, "fixture-key")
        self.assertLess(time.monotonic() - started, 3)
        self.assertIsNone(transport.process)
        with self.assertRaises(ev.EvaluationError):
            transport({}, {"timeout_seconds": 1}, "fixture-key")

    def test_worker_reply_passes_without_key_in_arguments(self):
        transport = te.BoundedNativeTransport(worker=reply_worker)
        self.addCleanup(transport.close)
        response = transport({"fixture": "answer"}, {"timeout_seconds": 3}, "fixture-key")
        self.assertEqual(response["fixture"], "answer")
        self.assertNotIn("fixture-key", json.dumps(response))

    def test_billing_preflight_stops_before_sdk_or_tokenizer_initialization(self):
        with patch("bibleprep.tinker_access.check_access", return_value={"status": "billing_required"}), \
                patch.object(te, "load_pinned_tokenizer") as tokenizer:
            with self.assertRaises(ev.EvaluationError):
                te.NativeTransport().initialize({"timeout_seconds": 1, "model": "openai/gpt-oss-120b"}, "fixture-key")
        tokenizer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
