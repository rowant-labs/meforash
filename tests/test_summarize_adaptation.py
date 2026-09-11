import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bibleprep import evaluate as ev
from bibleprep import summarize_adaptation as report


class AdaptationSummaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runs, self.evals = self.root / "runs", self.root / "evals"
        self.runs.mkdir()
        self.evals.mkdir()
        self.cases = [{"id": f"case-{i}", "prompt": "PRIVATE QUESTION CANARY",
                       "expected_behavior": "PRIVATE GOLD CANARY", "review_status": "constructed",
                       "language": language, "category": "translation", "source_refs": []}
                      for i, language in enumerate(("hebrew", "aramaic", "greek", "mixed"))]
        self.dataset = self.evals / "frozen.jsonl"
        self.write_jsonl(self.dataset, self.cases)
        self.settings = {key: "synthetic" for key in report.SAMPLING_KEYS}
        self.settings.update(model=report.MODEL, model_version="provider_revision_unpinned",
                             max_input_tokens=6000, max_output_tokens=8192,
                             output_limit_field="max_completion_tokens", reasoning_effort="medium",
                             evidence_mode="provided", temperature=0.0, seed=20260905,
                             thinking_effort_numeric=0.7, hf_chat_template_used=False,
                             renderer_profile="tml_v0", renderer="official_tml_renderers",
                             tokenizer_sha256="1" * 64, chat_template_sha256="2" * 64,
                             comparison_manifest_sha256="3" * 64,
                             transport="native_tinker_comparison", timeout_seconds=240,
                             input_price_per_million=1.87, output_price_per_million=4.68,
                             private_note="PRIVATE SETTINGS CANARY", private_path="/Users/PRIVATE/account")
        self.calibration, self.training, self.baseline = [self.runs / label for label in
                                                         ("calibration", "training", "baseline")]
        for path, phase in ((self.calibration, "calibration"), (self.training, "full")):
            self.write_training(path, phase)
        self.checkpoint = {"sampler_path": "tinker://PRIVATE_ID:train/sampler_weights/PRIVATE_CHECKPOINT",
                           "training_state_path": "tinker://PRIVATE_STATE/weights/checkpoint"}
        self.write_json(self.training / "checkpoints.json", self.checkpoint)
        self.checkpoint_hash = ev.digest((self.training / "checkpoints.json").read_bytes())
        self.write_eval(self.baseline, self.dataset, self.cases, adapter=False)
        self.shards = []
        for offset in range(2):
            dataset = self.runs / f"shard-{offset}.jsonl"
            cases = self.cases[offset::2]
            self.write_jsonl(dataset, cases)
            directory = self.runs / f"adapted-{offset}"
            self.write_eval(directory, dataset, cases, adapter=True)
            self.shards.append((dataset, directory))

    @staticmethod
    def write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n")

    @staticmethod
    def write_jsonl(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def write_training(self, path, phase):
        recipe = {"model": report.MODEL, "loss_fn": "cross_entropy",
                  "optimization_loss_reduction": "sum", "manifest_sha256": "4" * 64,
                  "private_note": "PRIVATE RECIPE CANARY"}
        recipe_hash = ev.digest(report.canonical(recipe))
        plan = {"phase": phase, "recipe": recipe, "recipe_sha256": recipe_hash,
                "sequence_order_sha256": "5" * 64, "software_sha256": {"PRIVATE_PATH": "6" * 64},
                "run_id": "PRIVATE RUN CANARY", "training_sequences": 2, "training_batches": 1,
                "training_processed_tokens": 200, "training_loss_tokens": 180,
                "planned_estimated_usd": 3.001, "compute_reserve_nano_usd": 1_000_000,
                "checkpoint_reserve_nano_usd": 3_000_000_000, "checkpoint_ttl_seconds": 2592000}
        summary = {"status": "complete", "phase": phase, "recipe_sha256": recipe_hash,
                   "training_batches": 1, "training_processed_tokens": 200, "training_loss_tokens": 180,
                   "baseline_holdout": {"weighted_nll": 0.5, "weighted_loss_sum": 50,
                                        "loss_tokens": 100, "processed_tokens": 120},
                   "end_holdout": {"weighted_nll": 0.4, "weighted_loss_sum": 40,
                                   "loss_tokens": 100, "processed_tokens": 120},
                   "training_weighted_nll": 0.3, "account_id": "PRIVATE ACCOUNT CANARY"}
        self.write_json(path / "plan.json", plan)
        self.write_json(path / "summary.json", summary)

    def write_eval(self, directory, dataset, cases, *, adapter):
        settings = copy.deepcopy(self.settings)
        if adapter:
            settings.update(transport="native_tinker_inkling_adapter",
                            model_state="original_text_lora_adapter",
                            adapter_sampler_path=self.checkpoint["sampler_path"],
                            checkpoint_reference_sha256=self.checkpoint_hash)
        manifest = {"dataset_sha256": ev.digest(dataset.read_bytes()), "system_prompt_sha256": "7" * 64,
                    "settings": settings, "case_ids": [case["id"] for case in cases], "schema_version": 1}
        self.save_eval_manifest(directory, manifest)
        events = []
        for index, case in enumerate(cases):
            events.extend([{"event": "started", "case_id": case["id"], "reserved_cost_usd": 0.1},
                           {"event": "completed", "case_id": case["id"],
                            "accounted_cost_usd": 0.001123, "elapsed_seconds": 10 + index,
                            "answer_complete": True, "finish_reason": "stop", "truncated": False,
                            "usage": {"input_tokens": 100, "output_tokens": 200},
                            "accounting_uncertain": False,
                            "raw_response_redacted": {
                                "private_id": "PRIVATE PROVIDER CANARY",
                                "choices": [{"message": {"content": "PRIVATE ANSWER CANARY"},
                                             "finish_reason": "stop"}],
                                "usage": {"prompt_tokens": 100, "completion_tokens": 200},
                                "native_tinker": {"prompt_sha256": ev.digest(case["id"].encode())}}}])
        self.write_jsonl(directory / "events.jsonl", events)

    def save_eval_manifest(self, directory, manifest):
        identity = {key: manifest[key] for key in (
            "dataset_sha256", "system_prompt_sha256", "settings", "case_ids", "schema_version")}
        manifest["fingerprint"] = ev.digest(ev.json_bytes(identity))
        self.write_json(directory / "manifest.json", manifest)

    def summarize(self):
        return report.summarize(calibration_run=self.calibration, training_run=self.training,
                                baseline_run=self.baseline, dataset=self.dataset,
                                shards=self.shards, root=self.root)

    def test_complete_comparison_verifies_prompts_and_emits_safe_aggregates(self):
        with patch.object(ev, "load_project_environment") as environment, patch.object(ev, "send_request") as network:
            result = self.summarize()
        environment.assert_not_called()
        network.assert_not_called()
        self.assertFalse(result["partial"])
        self.assertEqual(result["comparison_validation"]["paired_prompt_hashes_verified"], 4)
        self.assertTrue(result["comparison_validation"]["all_question_prompt_hashes_verified"])
        adapted = result["english_evaluation"]["adapted_model"]
        self.assertEqual(adapted["counts"]["complete_answers"], 4)
        self.assertEqual(adapted["tokens"], {"input": 400, "output": 800})
        self.assertEqual(adapted["latency_seconds"]["median"], 10.5)
        self.assertAlmostEqual(adapted["cost"]["known_token_estimate_usd"], 0.004492)
        self.assertAlmostEqual(result["training"]["development_pass"]["holdout_nll_change"], -0.1)
        self.assertFalse(result["accuracy_or_improvement_score_assigned"])
        serialized = json.dumps(result)
        for canary in ("PRIVATE", "tinker://", "/Users/", str(self.root), "case-0", "raw_response_redacted", "sampler_path"):
            self.assertNotIn(canary, serialized)

    def test_changed_question_with_same_id_is_rejected_even_if_manifest_rehashed(self):
        dataset, directory = self.shards[0]
        cases, _ = ev.load_cases(dataset)
        cases[0]["prompt"] = "Changed question"
        self.write_jsonl(dataset, cases)
        self.write_eval(directory, dataset, cases, adapter=True)
        with self.assertRaisesRegex(ev.EvaluationError, "change a frozen question"):
            self.summarize()

    def test_overlap_and_missing_shards_are_rejected(self):
        self.shards[1] = self.shards[0]
        with self.assertRaises(ev.EvaluationError):
            self.summarize()
        self.shards.pop()
        with self.assertRaisesRegex(ev.EvaluationError, "cover exactly"):
            self.summarize()

    def test_generation_or_system_prompt_drift_is_rejected(self):
        directory = self.shards[0][1]
        original = json.loads((directory / "manifest.json").read_text())
        for key, value in (("seed", 1), ("max_output_tokens", 100), ("reasoning_effort", "low")):
            changed = copy.deepcopy(original)
            changed["settings"][key] = value
            self.save_eval_manifest(directory, changed)
            with self.subTest(key=key), self.assertRaisesRegex(ev.EvaluationError, "settings differ"):
                self.summarize()
        changed = copy.deepcopy(original)
        changed["system_prompt_sha256"] = "8" * 64
        self.save_eval_manifest(directory, changed)
        with self.assertRaisesRegex(ev.EvaluationError, "settings differ"):
            self.summarize()

    def test_different_checkpoint_is_rejected(self):
        directory = self.shards[0][1]
        manifest = json.loads((directory / "manifest.json").read_text())
        manifest["settings"]["adapter_sampler_path"] = "tinker://OTHER/sampler_weights/model"
        self.save_eval_manifest(directory, manifest)
        with self.assertRaisesRegex(ev.EvaluationError, "training checkpoint"):
            self.summarize()

    def test_prompt_token_hash_mismatch_is_rejected(self):
        journal = self.shards[0][1] / "events.jsonl"
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        events[1]["raw_response_redacted"]["native_tinker"]["prompt_sha256"] = "9" * 64
        self.write_jsonl(journal, events)
        with self.assertRaisesRegex(ev.EvaluationError, "different prompt tokens"):
            self.summarize()

    def test_error_and_incomplete_answers_remain_distinct(self):
        journal = self.shards[0][1] / "events.jsonl"
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        events[1] = {"event": "error", "case_id": events[1]["case_id"],
                     "accounted_cost_usd": 0.1, "elapsed_seconds": 240, "accounting_uncertain": True}
        events[3]["answer_complete"] = False
        events[3]["finish_reason"] = "length"
        events[3]["truncated"] = True
        events[3]["raw_response_redacted"]["choices"][0]["finish_reason"] = "length"
        self.write_jsonl(journal, events)
        result = self.summarize()
        counts = result["english_evaluation"]["adapted_model"]["counts"]
        self.assertEqual((counts["complete_answers"], counts["incomplete_answers"], counts["errors"]), (2, 1, 1))
        self.assertEqual(result["comparison_validation"]["paired_prompt_hashes_verified"], 3)
        self.assertFalse(result["comparison_validation"]["all_question_prompt_hashes_verified"])

    def test_partial_tail_unresolved_and_absent_run_are_not_reported_as_complete(self):
        journal = self.shards[0][1] / "events.jsonl"
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        self.write_jsonl(journal, events[:3])
        with journal.open("a") as handle:
            handle.write('{"event":"completed"')
        absent = self.runs / "not_started"
        self.shards[1] = (self.shards[1][0], absent)
        result = self.summarize()
        counts = result["english_evaluation"]["adapted_model"]["counts"]
        self.assertTrue(result["partial"])
        self.assertEqual((counts["complete_answers"], counts["unresolved"], counts["not_started"]), (1, 1, 2))
        self.assertEqual(counts["missing_results"], 3)

    def test_training_recipe_or_nll_corruption_is_rejected(self):
        path = self.training / "summary.json"
        original = json.loads(path.read_text())
        modified = copy.deepcopy(original)
        modified["end_holdout"]["weighted_nll"] = 5
        self.write_json(path, modified)
        with self.assertRaisesRegex(ev.EvaluationError, "NLL disagrees"):
            self.summarize()
        modified = copy.deepcopy(original)
        modified["recipe_sha256"] = "0" * 64
        self.write_json(path, modified)
        with self.assertRaisesRegex(ev.EvaluationError, "different experiment identities"):
            self.summarize()

    def test_dataset_bytes_manifest_fingerprint_and_duplicate_results_fail_closed(self):
        dataset, directory = self.shards[0]
        original = dataset.read_bytes()
        dataset.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ev.EvaluationError, "exact dataset bytes"):
            self.summarize()
        dataset.write_bytes(original)
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["settings"]["seed"] = 1
        self.write_json(manifest_path, manifest)
        with self.assertRaisesRegex(ev.EvaluationError, "fingerprint"):
            self.summarize()
        self.write_eval(directory, dataset, self.cases[::2], adapter=True)
        journal = directory / "events.jsonl"
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        events.append(events[-1])
        self.write_jsonl(journal, events)
        with self.assertRaisesRegex(ev.EvaluationError, "duplicated"):
            self.summarize()

    def test_changed_execution_deadline_is_visible_but_not_confused_with_token_settings(self):
        directory = self.shards[0][1]
        manifest = json.loads((directory / "manifest.json").read_text())
        manifest["settings"]["timeout_seconds"] = 300
        self.save_eval_manifest(directory, manifest)
        result = self.summarize()
        self.assertEqual(result["english_evaluation"]["adapted_model"]["request_deadline_seconds"], [240, 300])

    def test_missing_usage_is_explicitly_uncertain_even_without_flag(self):
        journal = self.shards[0][1] / "events.jsonl"
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        events[1]["usage"] = None
        events[1]["accounted_cost_usd"] = 0.1
        events[1]["accounting_uncertain"] = False
        self.write_jsonl(journal, events)
        adapted = self.summarize()["english_evaluation"]["adapted_model"]
        self.assertEqual(adapted["counts"]["missing_usage"], 1)
        self.assertAlmostEqual(adapted["cost"]["uncertain_accounted_or_reserved_usd"], 0.1)

    def test_in_progress_training_cannot_be_confused_with_a_finished_adapter(self):
        (self.training / "summary.json").unlink()
        with self.assertRaisesRegex(ev.EvaluationError, "training checkpoint"):
            self.summarize()
        self.shards = [(path, self.runs / f"absent-{i}") for i, (path, _) in enumerate(self.shards)]
        result = self.summarize()
        self.assertTrue(result["partial"])
        self.assertEqual(result["training"]["development_pass"]["status"], "in_progress")
        self.assertIsNone(result["training"]["development_pass"]["end_holdout"])


if __name__ == "__main__":
    unittest.main()
