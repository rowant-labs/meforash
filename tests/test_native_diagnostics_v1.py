import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from bibleprep import evaluate as ev
from bibleprep import native_diagnostics_v1 as diagnostic
from bibleprep import tinker_compare as comparison


class NativeDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = "manifests/comparison-large-models-v1.json"
        cls.profile = comparison.TmlProfile(
            comparison.load_pinned_tokenizer(diagnostic.MODEL, cls.manifest), diagnostic.MODEL, cls.manifest)
        cls.payload = {"messages": [{"role": "system", "content": "Synthetic policy."},
                                    {"role": "user", "content": "Synthetic question."}]}
        cls.parse_config = {"reasoning_effort": "medium"}
        cls.visible = "Visible ἀγάπη בַּיִת"
        cls.private = "SYNTHETIC PRIVATE THINKING"

    def token(self, name):
        return self.profile.native.encode_special(name)

    def message(self, text, *, thinking=False, closed=True, author="message_model"):
        ids = [self.token(author), self.token("content_thinking" if thinking else "content_text")]
        ids.extend(self.profile.native.encode_ordinary(text))
        if closed:
            ids.append(self.token("end_message"))
        return ids

    def parse(self, ids, stop="length"):
        return diagnostic.parse_generated(self.profile, self.payload, self.parse_config, ids, stop)

    def config(self, run_dir):
        return {"model": diagnostic.MODEL, "base_url": diagnostic.native.TINKER_URL,
                "comparison_manifest": self.manifest, "reasoning_effort": "medium",
                "temperature": 0.0, "seed": 20260905, "run_dir": str(run_dir),
                "max_cases": 1, "max_input_tokens": 6000, "max_output_tokens": 8192,
                "timeout_seconds": 300, "renderer_profile": "tml_v0"}

    def response(self, run_dir, ids, stop="length"):
        import tinker
        transport = diagnostic.DiagnosticNativeTransport()
        transport.profile = self.profile
        transport.base_model = diagnostic.MODEL
        transport.types = tinker.types
        transport.sampler = MagicMock()
        transport.sampler.sample.return_value.result.return_value = SimpleNamespace(
            sequences=[SimpleNamespace(tokens=ids, stop_reason=stop)], prompt_cache_hit_tokens=0)
        config = self.config(run_dir)
        transport.binding = ev.digest(ev.json_bytes(config))
        result = transport(self.payload, config, "synthetic-unused-secret")
        return result, transport

    def test_unfinished_final_is_recovered_without_complete_message(self):
        result = self.parse(self.message(self.visible, closed=False))
        self.assertEqual(result["completed_final_text"], "")
        self.assertEqual(result["partial_final_text"], self.visible)
        self.assertEqual(result["partial_thinking_text"], "")
        self.assertEqual(result["partial_final_status"], "present")
        self.assertFalse(result["native_turn_complete"])
        self.assertEqual(result["finish_reason"], "length")
        self.assertEqual(result["parse_issues"], [])

    def test_unfinished_thinking_is_never_final(self):
        result = self.parse(self.message(self.private, thinking=True, closed=False))
        self.assertEqual(result["partial_thinking_text"], self.private)
        self.assertEqual(result["partial_final_text"], "")
        self.assertEqual(result["completed_final_text"], "")
        self.assertEqual(result["partial_thinking_status"], "present")
        self.assertNotIn(self.private, json.dumps(diagnostic.public_summary(result)))

    def test_closed_thinking_and_unfinished_final_are_separate(self):
        result = self.parse(self.message(self.private, thinking=True) + self.message(self.visible, closed=False))
        self.assertEqual(result["completed_thinking_text"], self.private)
        self.assertEqual(result["partial_final_text"], self.visible)
        self.assertEqual(result["completed_final_message_count"], 0)
        self.assertEqual(result["completed_thinking_message_count"], 1)

    def test_complete_message_is_not_complete_turn(self):
        result = self.parse(self.message(self.visible))
        self.assertEqual(result["completed_final_text"], self.visible)
        self.assertEqual(result["partial_final_text"], "")
        self.assertTrue(result["parser_at_message_boundary"])
        self.assertFalse(result["native_turn_complete"])
        self.assertEqual(result["finish_reason"], "length")

    def test_complete_turn_preserves_channels_and_unicode(self):
        ids = self.message(self.private, thinking=True) + self.message(self.visible) + [self.token("content_model_end_sampling")]
        result = self.parse(ids, "stop")
        self.assertEqual(result["completed_final_text"], self.visible)
        self.assertEqual(result["completed_thinking_text"], self.private)
        self.assertTrue(result["native_turn_complete"])
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(result["semantic_answer_completeness"], "not_assessed")
        self.assertEqual(result["raw_generated_token_ids_sha256"], ev.digest(ev.json_bytes(ids)))

    def test_empty_or_thinking_only_complete_turn_does_not_imply_answer(self):
        for ids in ([self.token("content_model_end_sampling")],
                    self.message(self.private, thinking=True) + [self.token("content_model_end_sampling")]):
            with self.subTest(ids=len(ids)):
                result = self.parse(ids, "stop")
                self.assertTrue(result["native_turn_complete"])
                self.assertEqual(result["finish_reason"], "incomplete_tml")
                self.assertEqual(result["completed_final_text"], "")

    def test_provider_length_stays_length_even_if_turn_marker_present(self):
        result = self.parse(self.message(self.visible) + [self.token("content_model_end_sampling")])
        self.assertTrue(result["native_turn_complete"])
        self.assertEqual(result["finish_reason"], "length")

    def test_multiple_complete_final_messages_and_partial_tail(self):
        result = self.parse(self.message("First") + self.message("Second") + self.message("Tail", closed=False))
        self.assertEqual(result["completed_final_text"], "First\nSecond")
        self.assertEqual(result["partial_final_text"], "Tail")
        self.assertEqual(result["completed_final_message_count"], 2)
        self.assertEqual(result["final_content_state"], "completed_and_partial")

    def test_empty_open_content_and_header_have_explicit_status(self):
        for name, expected in [("content_text", "partial_final_status"), ("content_thinking", "partial_thinking_status")]:
            result = self.parse([self.token("message_model"), self.token(name)])
            self.assertTrue(result["header_open"])
            self.assertEqual(result[expected], "empty_open_content")
        self.assertTrue(self.parse([self.token("message_model")])["header_open"])

    def test_unframed_and_embedded_boundary_tokens_are_diagnostic_warnings(self):
        for ids in (list(self.profile.native.encode_ordinary("Unframed text")),
                    self.message(self.visible, closed=False) + [self.token("message_user")]):
            result = self.parse(ids)
            self.assertTrue(result["diagnostic_warnings"])
            self.assertFalse(result["native_turn_complete"])

    def test_tokens_after_stop_are_malformed(self):
        for ids, issue in [
            (self.message(self.visible) + [self.token("content_model_end_sampling")] + self.message("Later"), "tokens_after_turn_end"),
        ]:
            result = self.parse(ids, "stop")
            self.assertIn(issue, result["parse_issues"])
            self.assertNotEqual(result["finish_reason"], "stop")

    def test_thinking_after_final_is_valid_typed_content_not_suppression(self):
        ids = self.message(self.visible) + self.message(self.private, thinking=True) + [self.token("content_model_end_sampling")]
        result = self.parse(ids, "stop")
        self.assertEqual(result["parse_issues"], [])
        self.assertIn("thinking_after_final_text", result["diagnostic_warnings"])
        self.assertEqual(result["completed_final_text"], self.visible)
        self.assertEqual(result["completed_thinking_text"], self.private)
        self.assertTrue(result["native_turn_complete"])
        self.assertEqual(result["finish_reason"], "stop")

    def test_other_author_is_not_mistaken_for_assistant_content(self):
        result = self.parse(self.message("User text", author="message_user") + [self.token("content_model_end_sampling")], "stop")
        self.assertIn("unexpected_tml_author", result["diagnostic_warnings"])
        self.assertEqual(result["completed_final_text"], "")

    def test_canonical_official_sft_fixture_parses_with_same_boundaries(self):
        chat = self.profile.chat
        user = chat.Message(author=chat.Author(chat.AuthorKind.User), content=chat.Text("Q"))
        stop = chat.Message(author=chat.Author(chat.AuthorKind.Model), content=chat.ModelEndSampling())
        variants = [
            (chat.Text(self.visible), chat.MessageChannel.Main, None, None),
            (chat.Text(self.visible), chat.MessageChannel.Final, None, None),
            (chat.Thinking(self.private), chat.MessageChannel.Analysis, None, None),
            (chat.Text(self.visible), chat.MessageChannel.Final, "assistant", None),
            (chat.Text(self.visible), chat.MessageChannel.Main, None,
             chat.MessageMetadata(product_metadata=chat.MessageMetadataProduct(message_id=42), tool_call_id="synthetic")),
        ]
        for content, channel, name, metadata in variants:
            with self.subTest(channel=channel, name=name):
                answer = chat.Message(author=chat.Author(chat.AuthorKind.Model, name=name), content=content,
                                      channel_enum=channel, message_metadata=metadata)
                examples = self.profile.renderer.render_for_sft([user, answer, stop])
                ids = [t for example in examples for span in example.input_token_spans for t in span.span.tokens]
                generated = ids[ids.index(self.token("message_model")):]
                result = self.parse(generated, "stop")
                self.assertEqual(result["completed_final_text"], "" if isinstance(content, chat.Thinking) else self.visible)
                self.assertEqual(result["completed_thinking_text"], self.private if isinstance(content, chat.Thinking) else "")
                self.assertTrue(result["native_turn_complete"])
                self.assertEqual(result["parse_issues"], [])
                self.assertEqual(result["diagnostic_warnings"], [])

    def test_public_summary_rejects_arbitrary_strings_and_changed_counts(self):
        result = self.parse(self.message(self.private, thinking=True, closed=False))
        result["injected_secret"] = self.private
        safe = diagnostic.public_summary(result)
        self.assertNotIn("injected_secret", safe)
        self.assertNotIn(self.private, json.dumps(safe))
        for key, value in [("provider_stop_reason", self.private), ("parse_issues", [self.private]),
                           ("partial_thinking_characters", 1)]:
            changed = copy.deepcopy(result)
            changed[key] = value
            with self.assertRaises(ev.EvaluationError):
                diagnostic.public_summary(changed)

    def test_invalid_raw_ids_fail_closed(self):
        for ids in ([True], [-1], [2**32], [1.0], "1", [1] * (diagnostic.MAX_RETAINED_TOKENS + 1)):
            with self.assertRaises(ev.EvaluationError):
                diagnostic.token_ids_sha256(ids)

    def test_unknown_vocabulary_ids_are_retained_but_not_silently_ignored(self):
        ids = [self.token("message_model"), self.token("content_text"), 200100,
               self.token("end_message"), self.token("content_model_end_sampling")]
        result = self.parse(ids, "stop")
        self.assertEqual(result["raw_generated_token_ids"], ids)
        self.assertIn("unknown_native_token_id", result["parse_issues"])
        self.assertFalse(result["native_turn_complete"])

    def test_official_parser_failure_preserves_prior_partial_deltas_without_error_text(self):
        ids = self.message(self.visible, closed=False)
        _, parser = self.profile.render(self.payload, self.parse_config)
        calls = 0

        def consume(token):
            nonlocal calls
            calls += 1
            if calls == len(ids):
                raise self.profile.parse_error("SYNTHETIC SENSITIVE EXCEPTION")
            return parser.parse_token(token)

        wrapped = SimpleNamespace(parse_token=consume, is_at_message_boundary=parser.is_at_message_boundary)
        with patch.object(self.profile, "render", return_value=([], wrapped)):
            result = self.parse(ids)
        self.assertIn("native_tml_parse_error", result["parse_issues"])
        self.assertEqual(result["raw_generated_token_ids"], ids)
        self.assertGreater(result["partial_final_characters"], 0)
        self.assertEqual(result["partial_final_status"], "present_before_parse_error")
        self.assertNotIn("SYNTHETIC SENSITIVE EXCEPTION", json.dumps(result))

    def test_valid_unsupported_tool_content_is_a_warning_not_parse_failure(self):
        ids = [self.token("message_model"), self.token("content_invoke_tool_text")]
        ids.extend(self.profile.native.encode_ordinary("SYNTHETIC TOOL"))
        ids += [self.token("end_message")] + self.message(self.visible) + [self.token("content_model_end_sampling")]
        result = self.parse(ids, "stop")
        self.assertEqual(result["parse_issues"], [])
        self.assertIn("unsupported_tml_content", result["diagnostic_warnings"])
        self.assertTrue(result["native_turn_complete"])
        self.assertEqual(result["completed_final_text"], self.visible)

    def test_sidecar_is_private_and_response_never_contains_thinking_or_partial(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ev, "RUNS_ROOT", Path(directory)):
            response, transport = self.response(directory, self.message(self.private, thinking=True) + self.message(self.visible, closed=False))
            wire = json.dumps(response)
            self.assertNotIn(self.private, wire)
            self.assertNotIn(self.visible, wire)
            metadata = response["native_tinker"]
            receipt = metadata["private_diagnostic_artifact"]
            path = Path(directory) / receipt["file"]
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            data = diagnostic.read_private_artifact(directory, receipt)
            self.assertEqual(data["completed_thinking_text"], self.private)
            safe = diagnostic.verify_private_artifact(response, directory)
            self.assertEqual(safe["private_artifact_sha256"], receipt["sha256"])
            self.assertTrue(safe["raw_generated_token_ids_retained"])
            projection = diagnostic.final_text_for_review(response, directory)
            self.assertEqual(projection["partial_final_text"], self.visible)
            self.assertFalse(projection["native_turn_complete"])
            self.assertNotIn(self.private, json.dumps(projection))
            call = transport.sampler.sample.call_args.kwargs
            self.assertEqual(call["sampling_params"].stop, self.profile.stop_tokens)
            self.assertEqual(call["sampling_params"].max_tokens, 8192)
            self.assertEqual(transport.sampler.sample.return_value.result.call_args.kwargs["timeout"], 300)

    def test_tampered_sidecar_hash_or_rehashed_raw_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ev, "RUNS_ROOT", Path(directory)):
            response, _ = self.response(directory, self.message(self.visible))
            receipt = response["native_tinker"]["private_diagnostic_artifact"]
            path = Path(directory) / receipt["file"]
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.assertRaises(ev.EvaluationError):
                diagnostic.verify_private_artifact(response, directory)
            data = json.loads(original)
            data["raw_generated_token_ids"][2] += 1
            path.write_bytes(ev.json_bytes(data))
            receipt["sha256"] = ev.digest(path.read_bytes())
            with self.assertRaises(ev.EvaluationError):
                diagnostic.verify_private_artifact(response, directory)

    def test_response_summary_and_output_hash_are_bound_to_sidecar(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ev, "RUNS_ROOT", Path(directory)):
            response, _ = self.response(directory, self.message(self.visible))
            for key, value in [("output_tokens_sha256", "0" * 64), ("provider_stop_reason", "stop")]:
                changed = copy.deepcopy(response)
                changed["native_tinker"][key] = value
                with self.assertRaises(ev.EvaluationError):
                    diagnostic.verify_private_artifact(changed, directory)

    def test_malformed_final_is_withheld_from_review_projection(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ev, "RUNS_ROOT", Path(directory)):
            response, _ = self.response(directory, self.message(self.visible) + [self.token("content_model_end_sampling")]
                                        + self.message(self.private, thinking=True, closed=False))
            self.assertEqual(ev.answer_details(response)[0], "")
            projection = diagnostic.final_text_for_review(response, directory)
            self.assertTrue(projection["final_text_withheld_due_to_malformed_structure"])
            self.assertEqual(projection["completed_final_text"], "")
            self.assertEqual(projection["partial_final_text"], "")

    def test_base_and_verified_adapter_route_to_distinct_sampler_arguments(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ev, "RUNS_ROOT", Path(directory)):
            path = Path(directory) / "checkpoint.json"
            path.write_bytes(ev.json_bytes({"sampler_path": "tinker://synthetic/sampler_weights/test"}))
            for adapted in (False, True):
                config = self.config(directory)
                if adapted:
                    config.update(checkpoint_reference_file=str(path), checkpoint_reference_sha256=ev.digest(path.read_bytes()),
                                  adapter_sampler_path="tinker://synthetic/sampler_weights/test")
                service = MagicMock()
                service.create_sampling_client.return_value.get_base_model.return_value = diagnostic.MODEL
                with patch("tinker.ServiceClient", return_value=service), \
                     patch.object(comparison, "configure", side_effect=lambda c: dict(c)), \
                     patch.object(comparison, "load_pinned_tokenizer"), \
                     patch.object(comparison, "TmlProfile", return_value=self.profile):
                    diagnostic.DiagnosticNativeTransport().initialize(config, "synthetic-test-key")
                call = service.create_sampling_client.call_args.kwargs
                self.assertIn("model_path" if adapted else "base_model", call)
                self.assertNotIn("base_model" if adapted else "model_path", call)

    def test_unverified_checkpoint_and_changed_settings_cannot_sample(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ev, "RUNS_ROOT", Path(directory)):
            config = self.config(directory)
            config.update(adapter_sampler_path="tinker://synthetic/sampler_weights/test", checkpoint_reference_sha256="0" * 64)
            with patch("tinker.ServiceClient") as service, patch.object(comparison, "configure", side_effect=lambda c: dict(c)):
                with self.assertRaises(ev.EvaluationError):
                    diagnostic.DiagnosticNativeTransport().initialize(config, "synthetic-test-key")
                service.assert_not_called()
            transport = diagnostic.DiagnosticNativeTransport()
            transport.sampler = MagicMock()
            transport.binding = "0" * 64
            with self.assertRaises(ev.EvaluationError):
                transport(self.payload, self.config(directory), "synthetic-test-key")
            transport.sampler.sample.assert_not_called()


if __name__ == "__main__":
    unittest.main()
