import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from bibleprep import evaluate as ev
from bibleprep import tinker_compare as tc
from bibleprep import tinker_evaluate as te


LIGHTNING = "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16"
QWEN = "Qwen/Qwen3.8-27B"
INKLING = "thinkingmachines/Inkling-Small"
INKLING_FULL = "thinkingmachines/Inkling"
ULTRA = "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16"
KIMI = "moonshotai/Kimi-K2.6"
LARGE_MANIFEST = "manifests/comparison-large-models-v1.json"


def basic_config(model=LIGHTNING):
    config = vars(tc.parser().parse_args(["--model", model]))
    config.pop("execute")
    config.pop("resume")
    return config


class ChatProfilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizers = {model: tc.load_pinned_tokenizer(model) for model in (LIGHTNING, QWEN)}

    def parse(self, text, model=LIGHTNING, stop="stop", thinking=True):
        tokenizer = self.tokenizers[model]
        return tc.parse_chatml(te.token_ids(tokenizer, text), tokenizer, stop, thinking=thinking)

    def test_closed_reasoning_is_never_retained(self):
        for model in self.tokenizers:
            with self.subTest(model=model):
                result = self.parse("Private thought</think>\n\nPublic answer<|im_end|>", model)
                self.assertEqual(result["content"], "Public answer")
                self.assertEqual(result["finish_reason"], "stop")
                self.assertGreater(result["analysis_content_tokens"], 0)
                self.assertNotIn("Private thought", json.dumps(result))

    def test_truncated_reasoning_cannot_become_final(self):
        result = self.parse("Private incomplete reasoning", stop="length")
        self.assertEqual(result["content"], "")
        self.assertEqual(result["finish_reason"], "length")

    def test_partial_final_and_missing_end_are_incomplete(self):
        self.assertEqual(self.parse("Reason</think>Partial", stop="length")["finish_reason"], "length")
        self.assertEqual(self.parse("Reason</think>Answer")["finish_reason"], "incomplete_chat_format")
        self.assertEqual(self.parse("Reason</think>Answer<|im_end|>extra")["finish_reason"], "incomplete_chat_format")

    def test_off_mode_allows_plain_final_and_rejects_new_thinking(self):
        self.assertEqual(self.parse("Answer<|im_end|>", thinking=False)["finish_reason"], "stop")
        result = self.parse("<think>Private</think>Answer<|im_end|>", thinking=False)
        self.assertEqual(result["content"], "")
        self.assertEqual(result["finish_reason"], "incomplete_chat_format")

    def test_templates_preserve_policy_unicode_and_model_specific_effort(self):
        for model in self.tokenizers:
            config = tc.configure(basic_config(model))
            payload = {"messages": [{"role": "system", "content": "Exact policy."},
                                     {"role": "user", "content": "Explain בָּרָא and κηρύσσων."}],
                       "gold_answer": "Do not send this."}
            rendered, ids = tc.render_hf_prompt(payload, config, self.tokenizers[model])
            self.assertIn("Exact policy.", rendered)
            self.assertIn("בָּרָא and κηρύσσων", rendered)
            self.assertNotIn("Do not send this", rendered)
            self.assertTrue(rendered.endswith("<|im_start|>assistant\n<think>\n"))
            self.assertEqual(ids, te.token_ids(self.tokenizers[model], rendered))
            if model == QWEN:
                self.assertIn("Reasoning effort is set to low.", rendered)
            else:
                self.assertNotIn("Reasoning effort is set", rendered)

    def test_off_templates_use_distinct_official_suffixes(self):
        for model, suffix in [(LIGHTNING, "<think></think>"), (QWEN, "<think>\n\n</think>\n\n")]:
            config = basic_config(model)
            config["reasoning_effort"] = "off"
            config = tc.configure(config)
            payload = {"messages": [{"role": "system", "content": "Policy"}, {"role": "user", "content": "Question"}]}
            rendered, _ = tc.render_hf_prompt(payload, config, self.tokenizers[model])
            self.assertTrue(rendered.endswith(suffix))

    def test_every_vocabulary_and_unicode_mismatch_is_rejected(self):
        pinned = self.tokenizers[LIGHTNING]
        self.assertTrue(tc.assert_hf_parity(pinned, pinned)["all_prompt_token_ids_compared"])
        different = Mock(wraps=pinned)
        different.get_vocab.return_value = {"different": 1}
        with self.assertRaises(ev.EvaluationError):
            tc.assert_hf_parity(pinned, different)
        different = Mock(wraps=pinned)
        different.encode.return_value = [1]
        with self.assertRaises(ev.EvaluationError):
            tc.assert_hf_parity(pinned, different)

    def test_sampler_accounts_all_generated_tokens_without_reasoning_text(self):
        tokenizer = self.tokenizers[LIGHTNING]
        config = tc.configure(basic_config())
        payload = {"messages": [{"role": "system", "content": "Policy"}, {"role": "user", "content": "Question"}]}
        transport = tc.NativeComparisonTransport()
        generated = te.token_ids(tokenizer, "Private thought</think>Answer<|im_end|>")
        transport.sampler = Mock()
        transport.sampler.sample.return_value.result.return_value = SimpleNamespace(
            sequences=[SimpleNamespace(tokens=generated, stop_reason="stop")], prompt_cache_hit_tokens=0)
        transport.pinned = transport.live = tokenizer
        transport.base_model = LIGHTNING
        transport.parity = {"fixture": True}
        transport.types = SimpleNamespace(SamplingParams=lambda **kwargs: kwargs,
                                          ModelInput=SimpleNamespace(from_ints=lambda tokens: tokens))
        result = transport(payload, config, "fixture-key")
        self.assertEqual(result["usage"]["completion_tokens"], len(generated))
        self.assertEqual(result["usage"]["prompt_tokens"], len(tc.render_hf_prompt(payload, config, tokenizer)[1]))
        self.assertEqual(result["choices"][0]["message"]["content"], "Answer")
        self.assertNotIn("Private thought", json.dumps(result))
        self.assertFalse(result["native_tinker"]["accounting_is_invoice"])
        self.assertEqual(transport.sampler.sample.call_args.kwargs["sampling_params"]["stop"],
                         [te.token_ids(tokenizer, "<|im_end|>")[0]])

    def test_actual_prompt_mismatch_stops_before_sampling(self):
        transport = tc.NativeComparisonTransport()
        transport.sampler = Mock()
        transport.pinned = self.tokenizers[LIGHTNING]
        transport.live = Mock(wraps=transport.pinned)
        transport.live.encode.return_value = [1]
        payload = {"messages": [{"role": "system", "content": "Policy"}, {"role": "user", "content": "Question"}]}
        with self.assertRaises(ev.EvaluationError):
            transport(payload, tc.configure(basic_config()), "fixture-key")
        transport.sampler.sample.assert_not_called()


class ComparisonRunTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = basic_config()
        self.config.update(run_dir=str(self.root / "runs/comparison"), max_cases=1)
        patcher = patch.object(ev, "RUNS_ROOT", self.root / "runs")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dry_run_does_not_read_key_environment_or_initialize_sdk(self):
        with patch.object(tc.NativeComparisonTransport, "initialize") as initialize, \
                patch.object(ev, "load_project_environment") as environment, \
                patch.dict(os.environ, {}, clear=True):
            summary = tc.run(self.config)
        initialize.assert_not_called()
        environment.assert_not_called()
        self.assertEqual(summary["mode"], "dry_run")
        settings = json.loads((Path(self.config["run_dir"]) / "manifest.json").read_text())["settings"]
        self.assertEqual(settings["renderer_profile"], "nemotron3_ultra")
        self.assertEqual(settings["reasoning_effort"], "on")
        self.assertFalse(settings["reasoning_settings_are_cross_model_equivalent"])

    def test_budget_required_before_sdk_initialization(self):
        with patch.object(tc.NativeComparisonTransport, "initialize") as initialize:
            with self.assertRaises(ev.EvaluationError):
                tc.run(self.config, execute=True)
        initialize.assert_not_called()

    def test_complete_deadline_has_bounded_300_second_maximum(self):
        ev.validate_config(self.config, execute=False)
        self.config["timeout_seconds"] = 300
        ev.validate_config(self.config, execute=False)
        self.config["timeout_seconds"] = 301
        with self.assertRaises(ev.EvaluationError):
            ev.validate_config(self.config, execute=False)

    def test_checksum_and_endpoint_mismatches_are_rejected(self):
        with patch.object(ev, "digest", return_value="wrong"):
            with self.assertRaises(ev.EvaluationError):
                tc.configure(self.config)
        self.config["base_url"] = "https://elsewhere.invalid"
        with self.assertRaises(ev.EvaluationError):
            tc.configure(self.config)

    def test_unsupported_model_and_effort_are_rejected(self):
        self.config["reasoning_effort"] = "low"
        with self.assertRaises(ev.EvaluationError):
            tc.configure(self.config)
        self.config["model"] = "unverified/model"
        with self.assertRaises(ev.EvaluationError):
            tc.configure(self.config)

    def test_billing_preflight_stops_before_tokenizer_or_sdk(self):
        with patch("bibleprep.tinker_access.check_access", return_value={"status": "billing_required"}), \
                patch.object(tc, "load_pinned_tokenizer") as tokenizer:
            with self.assertRaises(ev.EvaluationError):
                tc.NativeComparisonTransport().initialize({"timeout_seconds": 1}, "fixture-key")
        tokenizer.assert_not_called()


class TmlProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pinned = tc.load_pinned_tokenizer(INKLING)
        cls.profile = tc.TmlProfile(cls.pinned, INKLING)
        cls.config = tc.configure(basic_config(INKLING))

    def payload(self):
        return {"messages": [{"role": "system", "content": "Policy"},
                             {"role": "user", "content": "Explain בָּרָא and κηρύσσων."}]}

    def sample_tokens(self, thinking="Private thought", answer="Visible answer"):
        native = self.profile.native
        return ([native.encode_special("message_model"), native.encode_special("content_thinking")]
                + list(native.encode_ordinary(thinking)) + [native.encode_special("end_message"),
                native.encode_special("message_model"), native.encode_special("content_text")]
                + list(native.encode_ordinary(answer)) + [native.encode_special("end_message"),
                native.encode_special("content_model_end_sampling")])

    def test_native_prefix_effort_and_complete_vocabulary_parity(self):
        tokens, _ = self.profile.render(self.payload(), self.config)
        rendered = self.profile.native.decode(tokens)
        self.assertTrue(rendered.endswith("<|end_message|>"))
        self.assertNotIn("<|message_model|>", rendered)
        self.assertIn("Thinking effort level: 0.2", rendered)
        self.assertEqual(tokens, te.token_ids(self.pinned, rendered))
        self.assertEqual(self.profile.parity["vocabulary_entries"], 200058)
        self.assertFalse(self.profile.parity["live_sdk_tokenizer_compared"])

    def test_medium_effort_is_native_numeric_point_seven(self):
        config = dict(self.config, reasoning_effort="medium")
        tokens, _ = self.profile.render(self.payload(), config)
        self.assertIn("Thinking effort level: 0.7", self.profile.native.decode(tokens))

    def test_parsed_thinking_is_excluded_from_returned_answer(self):
        _, parser = self.profile.render(self.payload(), self.config)
        result = self.profile.parse(self.sample_tokens(), parser, "stop")
        self.assertEqual(result["content"], "Visible answer")
        self.assertEqual(result["finish_reason"], "stop")
        self.assertNotIn("Private thought", json.dumps(result))
        self.assertIsNone(result["analysis_content_tokens"])

    def test_native_truncation_cannot_return_reasoning_as_final(self):
        _, parser = self.profile.render(self.payload(), self.config)
        native = self.profile.native
        tokens = ([native.encode_special("message_model"), native.encode_special("content_thinking")]
                  + list(native.encode_ordinary("Private unfinished thinking")))
        result = self.profile.parse(tokens, parser, "length")
        self.assertEqual(result["content"], "")
        self.assertEqual(result["finish_reason"], "length")
        self.assertNotIn("Private unfinished thinking", json.dumps(result))

    def test_final_without_native_turn_end_remains_incomplete(self):
        _, parser = self.profile.render(self.payload(), self.config)
        result = self.profile.parse(self.sample_tokens()[:-1], parser, "stop")
        self.assertEqual(result["finish_reason"], "incomplete_tml")
        self.assertFalse(result["turn_end_observed"])

    def test_every_comparison_prompt_has_native_hf_token_parity(self):
        cases, _ = ev.load_cases(tc.ROOT / "evals/comparison-v1.jsonl")
        for case in cases:
            with self.subTest(case=case["id"]):
                tokens, _ = self.profile.render(ev.build_payload(case, self.config), self.config)
                self.assertLessEqual(len(tokens), self.config["max_input_tokens"])

    def test_both_inkling_models_use_their_own_pinned_identity_and_prompt_parity(self):
        cases, _ = ev.load_cases(tc.ROOT / "evals/comparison-v1.jsonl")
        revisions = {}
        for model in (INKLING, INKLING_FULL):
            with self.subTest(model=model):
                config = tc.configure(basic_config(model))
                pinned = tc.load_pinned_tokenizer(model)
                profile = tc.TmlProfile(pinned, model)
                entry, identity, _ = tc.local_identity(model)
                self.assertEqual(entry["id"], model)
                self.assertEqual(config["model"], model)
                self.assertEqual(config["renderer_profile"], "tml_v0")
                self.assertEqual(profile.parity["vocabulary_entries"], 200058)
                revisions[model] = identity["tokenizer_revision"]
                for case in cases:
                    tokens, _ = profile.render(ev.build_payload(case, config), config)
                    self.assertEqual(tokens, te.token_ids(pinned, profile.native.decode(tokens)))
        self.assertEqual(revisions[INKLING_FULL], "828496eeae4c243ff1a22f7f28ff83694f2f7bc9")
        self.assertNotEqual(revisions[INKLING], revisions[INKLING_FULL])

    def test_native_usage_counts_all_tokens_and_never_calls_broken_sdk_accessor(self):
        transport = tc.NativeComparisonTransport()
        generated = self.sample_tokens()
        transport.sampler = Mock()
        transport.sampler.sample.return_value.result.return_value = SimpleNamespace(
            sequences=[SimpleNamespace(tokens=generated, stop_reason="stop")])
        transport.tml = self.profile
        transport.parity = self.profile.parity
        transport.base_model = INKLING
        transport.types = SimpleNamespace(SamplingParams=lambda **kwargs: kwargs,
                                          ModelInput=SimpleNamespace(from_ints=lambda tokens: tokens))
        response = transport(self.payload(), self.config, "fixture-key")
        self.assertEqual(response["usage"]["completion_tokens"], len(generated))
        self.assertNotIn("Private thought", json.dumps(response))
        transport.sampler.get_tokenizer.assert_not_called()

    def test_inkling_dry_run_never_reads_key_or_initializes_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = basic_config(INKLING)
            config.update(run_dir=str(root / "runs/native"), max_cases=1)
            with patch.object(ev, "RUNS_ROOT", root / "runs"), \
                    patch.object(ev, "load_project_environment") as environment, \
                    patch.object(tc.NativeComparisonTransport, "initialize") as initialize:
                summary = tc.run(config)
            self.assertEqual(summary["mode"], "dry_run")
            environment.assert_not_called()
            initialize.assert_not_called()


class LargeProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizers = {model: tc.load_pinned_tokenizer(model, LARGE_MANIFEST) for model in (ULTRA, KIMI)}

    def config(self, model=KIMI, effort=None):
        config = basic_config(model)
        config.update(comparison_manifest=LARGE_MANIFEST, reasoning_effort=effort)
        return tc.configure(config)

    def payload(self):
        return {"messages": [{"role": "system", "content": "Exact policy."},
                             {"role": "user", "content": "Explain בָּרָא and κηρύσσων."}],
                "gold_answer": "Never send this."}

    def parse(self, text, *, thinking=True, stop="stop"):
        return tc.parse_chatml(te.token_ids(self.tokenizers[KIMI], text), self.tokenizers[KIMI], stop,
                               thinking=thinking, marker_names=tc.KIMI_MARKERS)

    def test_separate_manifest_keeps_old_default_and_portable_identity(self):
        old = tc.configure(basic_config())
        new = self.config()
        self.assertNotIn("comparison_manifest", old)
        self.assertEqual(new["comparison_manifest"], LARGE_MANIFEST)
        self.assertEqual(new["tokenizer_revision"], tc.KIMI_TOKENIZER_REVISION)
        self.assertEqual(new["custom_tokenizer_code_sha256"], tc.KIMI_SOURCE_HASHES)
        self.assertNotEqual(old["comparison_manifest_sha256"], new["comparison_manifest_sha256"])
        absolute = basic_config(KIMI)
        absolute["comparison_manifest"] = str(tc.ROOT / LARGE_MANIFEST)
        self.assertEqual(tc.configure(absolute)["comparison_manifest"], LARGE_MANIFEST)
        for path in ("../outside.json", "manifests/../../elsewhere.json", "manifests/invalid.txt"):
            with self.subTest(path=path), self.assertRaises(ev.EvaluationError):
                tc.manifest_path(path)

    def test_kimi_thinking_modes_use_official_parameter_and_prefix(self):
        tokenizer = self.tokenizers[KIMI]
        for effort, ending in [("on", "<think>"), ("off", "<think></think>")]:
            rendered, tokens = tc.render_hf_prompt(self.payload(), self.config(effort=effort), tokenizer)
            self.assertTrue(rendered.endswith("<|im_assistant|>assistant<|im_middle|>" + ending))
            self.assertIn("<|im_system|>system<|im_middle|>Exact policy.<|im_end|>", rendered)
            self.assertIn("בָּרָא and κηρύσσων", rendered)
            self.assertNotIn("Never send this", rendered)
            self.assertEqual(tokens, tokenizer.model.encode(rendered, allowed_special="all"))

    def test_ultra_supports_medium_without_enabling_it_for_lightning(self):
        rendered, _ = tc.render_hf_prompt(self.payload(), self.config(ULTRA, "medium"), self.tokenizers[ULTRA])
        self.assertIn("{reasoning effort: efficient}", rendered)
        self.assertTrue(rendered.endswith("<|im_start|>assistant\n<think>\n"))
        lightning = basic_config()
        lightning["reasoning_effort"] = "medium"
        with self.assertRaises(ev.EvaluationError):
            tc.configure(lightning)
        with self.assertRaises(ev.EvaluationError):
            self.config(effort="medium")

    def test_kimi_local_checks_do_not_claim_independent_or_sdk_parity(self):
        result = tc.assert_kimi_parity(self.tokenizers[KIMI])
        self.assertEqual(result["vocabulary_entries"], 163840)
        self.assertFalse(result["live_sdk_tokenizer_compared"])
        self.assertFalse(result["independent_tokenizer_compared"])
        self.assertFalse(result["all_prompt_token_ids_compared"])
        self.assertTrue(result["all_prompt_native_vs_facade_token_ids_compared"])

    def test_kimi_verified_loader_is_offline_and_bypasses_tiktoken_cache(self):
        with patch("tiktoken.load.read_file_cached", side_effect=AssertionError("cache access")), \
                patch("socket.socket.connect", side_effect=AssertionError("network access")), \
                patch("transformers.AutoTokenizer.from_pretrained", side_effect=AssertionError("AutoTokenizer")):
            tokenizer = tc.load_pinned_tokenizer(KIMI, LARGE_MANIFEST)
        self.assertEqual(tokenizer.get_vocab(), self.tokenizers[KIMI].get_vocab())
        # Loading the source must not add __pycache__ files that invalidate later checks.
        tc.local_identity(KIMI, LARGE_MANIFEST)

    def test_unreviewed_custom_python_is_rejected_before_import(self):
        entry, identity, runtime = tc.local_identity(KIMI, LARGE_MANIFEST)
        entry = json.loads(json.dumps(entry))
        next(item for item in entry["files"] if item["path"] == "tokenization_kimi.py")["sha256"] = "0" * 64
        with patch.object(tc, "local_identity", return_value=(entry, identity, runtime)), \
                patch("importlib.util.spec_from_file_location") as loader, self.assertRaises(ev.EvaluationError):
            tc.load_pinned_tokenizer(KIMI, LARGE_MANIFEST)
        loader.assert_not_called()

    def test_kimi_final_only_parsing_requires_closed_thinking_and_turn_end(self):
        good = self.parse("Private thought</think>Public answer<|im_end|>")
        self.assertEqual(good["content"], "Public answer")
        self.assertEqual(good["finish_reason"], "stop")
        self.assertNotIn("Private thought", json.dumps(good))
        truncated = self.parse("Private unfinished thought", stop="length")
        self.assertEqual(truncated["content"], "")
        self.assertEqual(truncated["finish_reason"], "length")
        self.assertEqual(self.parse("Thought</think>Partial", stop="length")["finish_reason"], "length")
        self.assertEqual(self.parse("Thought</think>Answer")["finish_reason"], "incomplete_chat_format")
        self.assertEqual(self.parse("Plain answer<|im_end|>", thinking=False)["finish_reason"], "stop")

    def test_kimi_rejects_new_role_thinking_and_tool_content_in_final(self):
        for text in ("Thought</think><|im_assistant|>Hidden<|im_end|>",
                     "Thought</think><think>Hidden</think>Answer<|im_end|>",
                     "Thought</think><|tool_call_begin|>function.foo<|tool_call_end|><|im_end|>"):
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["content"], "")
                self.assertEqual(result["finish_reason"], "incomplete_chat_format")

    def test_kimi_sampling_counts_all_generated_tokens_without_sdk_accessor(self):
        tokenizer = self.tokenizers[KIMI]
        config = self.config()
        transport = tc.NativeComparisonTransport()
        transport.sampler = Mock()
        tokens = te.token_ids(tokenizer, "Private thought</think>Answer<|im_end|>")
        transport.sampler.sample.return_value.result.return_value = SimpleNamespace(
            sequences=[SimpleNamespace(tokens=tokens, stop_reason="stop")])
        transport.pinned = tokenizer
        transport.base_model = KIMI
        transport.parity = tc.assert_kimi_parity(tokenizer)
        transport.types = SimpleNamespace(SamplingParams=lambda **kwargs: kwargs,
                                          ModelInput=SimpleNamespace(from_ints=lambda tokens: tokens))
        response = transport(self.payload(), config, "fixture-key")
        self.assertEqual(response["usage"]["completion_tokens"], len(tokens))
        self.assertEqual(response["choices"][0]["message"]["content"], "Answer")
        self.assertNotIn("Private thought", json.dumps(response))
        transport.sampler.get_tokenizer.assert_not_called()

    def test_all_comparison_prompts_preserve_pinned_native_kimi_tokens(self):
        cases, _ = ev.load_cases(tc.ROOT / "evals/comparison-v1.jsonl")
        tokenizer = self.tokenizers[KIMI]
        config = self.config()
        for case in cases:
            with self.subTest(case=case["id"]):
                rendered, tokens = tc.render_hf_prompt(ev.build_payload(case, config), config, tokenizer)
                self.assertEqual(tokens, tokenizer.model.encode(rendered, allowed_special="all"))
                self.assertLessEqual(len(tokens), config["max_input_tokens"])

    def test_large_dry_run_does_not_read_environment_or_initialize_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for model in (ULTRA, KIMI, INKLING_FULL):
                config = self.config(model, "medium" if model == INKLING_FULL else "on")
                config.update(run_dir=str(root / "runs" / model.replace("/", "-")), max_cases=1)
                with patch.object(ev, "RUNS_ROOT", root / "runs"), \
                        patch.object(ev, "load_project_environment") as environment, \
                        patch.object(tc.NativeComparisonTransport, "initialize") as initialize:
                    self.assertEqual(tc.run(config)["mode"], "dry_run")
                environment.assert_not_called()
                initialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
