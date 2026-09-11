import copy
import json
import unittest
from unittest.mock import patch

from bibleprep import evaluate as ev
from bibleprep import summarize_repeat_control as control
from tests import test_summarize_adaptation as adaptation_fixture


class RepeatControlSummaryTests(unittest.TestCase):
    def setUp(self):
        # Reuse the tested synthetic artifact builder without inheriting its
        # adaptation tests or touching any real project run.
        self.fixture = adaptation_fixture.AdaptationSummaryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.prefix = f.runs / "repeat-prefix"
        self.tail = f.runs / "repeat-tail"
        self.tail_dataset = f.runs / "tail.jsonl"
        f.write_jsonl(self.tail_dataset, f.cases[2:])
        f.write_eval(self.prefix, f.dataset, f.cases[:2], adapter=False)
        f.write_eval(self.tail, self.tail_dataset, f.cases[2:], adapter=False)
        self.manifest = f.root / "manifests/control.json"
        f.write_json(self.manifest, {
            "frozen_dataset_sha256": ev.digest(f.dataset.read_bytes()),
            "first_four_case_ids": [row["id"] for row in f.cases[:2]],
            "remaining_twenty_case_ids": [row["id"] for row in f.cases[2:]],
            "remaining_dataset_sha256": ev.digest(self.tail_dataset.read_bytes()),
            "total_control_budget_usd": 1.45, "private_id": "PRIVATE CONTROL CANARY"})
        for directory in (f.baseline, self.prefix, self.tail):
            rows = self.events(directory)
            for event in rows:
                if event["event"] == "completed":
                    event["raw_response_redacted"]["native_tinker"]["output_tokens_sha256"] = ev.digest(
                        (event["case_id"] + ":tokens").encode())
            f.write_jsonl(directory / "events.jsonl", rows)

    @staticmethod
    def events(directory):
        return [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]

    def summarize(self):
        f = self.fixture
        return control.summarize(dataset=f.dataset, tail_dataset=self.tail_dataset,
                                 control_manifest=self.manifest, baseline_run=f.baseline,
                                 prefix_run=self.prefix, tail_run=self.tail, root=f.root)

    def test_exact_prefix_and_tail_match_without_leaking_text_or_identities(self):
        with patch.object(ev, "load_project_environment") as environment, patch.object(ev, "send_request") as network:
            result = self.summarize()
        environment.assert_not_called()
        network.assert_not_called()
        self.assertFalse(result["partial"])
        counts = result["comparison"]
        self.assertEqual(counts["paired_returned_responses"], 4)
        self.assertEqual(counts["identical_generated_token_streams"], 4)
        self.assertEqual(counts["exact_nonempty_final_text_matches"], 4)
        self.assertEqual(counts["different_final_texts"], 0)
        self.assertTrue(counts["all_question_prompt_hashes_verified"])
        self.assertAlmostEqual(result["repeat_control_additional_estimated_or_reserved_usd"], 0.004492)
        serialized = json.dumps(result)
        for marker in ("PRIVATE", "tinker://", "/Users/", str(self.fixture.root), "case-0", "raw_response_redacted"):
            self.assertNotIn(marker, serialized)
        self.assertFalse(result["accuracy_or_improvement_score_assigned"])

    def test_full_token_and_final_text_matches_are_distinguished(self):
        rows = self.events(self.prefix)
        rows[1]["raw_response_redacted"]["native_tinker"]["output_tokens_sha256"] = "8" * 64
        rows[3]["raw_response_redacted"]["native_tinker"]["output_tokens_sha256"] = "9" * 64
        rows[3]["raw_response_redacted"]["choices"][0]["message"]["content"] += " "
        self.fixture.write_jsonl(self.prefix / "events.jsonl", rows)
        comparison = self.summarize()["comparison"]
        self.assertEqual(comparison["identical_generated_token_streams"], 2)
        self.assertEqual(comparison["different_generated_token_streams"], 2)
        self.assertEqual(comparison["exact_final_text_matches"], 3)
        self.assertEqual(comparison["different_final_texts"], 1)

    def test_prompt_hash_mismatch_fails_closed(self):
        rows = self.events(self.prefix)
        rows[1]["raw_response_redacted"]["native_tinker"]["prompt_sha256"] = "0" * 64
        self.fixture.write_jsonl(self.prefix / "events.jsonl", rows)
        with self.assertRaisesRegex(ev.EvaluationError, "prompt token hashes differ"):
            self.summarize()

    def test_missing_full_output_hash_cannot_be_silently_treated_as_equal(self):
        rows = self.events(self.tail)
        del rows[1]["raw_response_redacted"]["native_tinker"]["output_tokens_sha256"]
        self.fixture.write_jsonl(self.tail / "events.jsonl", rows)
        with self.assertRaisesRegex(ev.EvaluationError, "provenance hash"):
            self.summarize()

    def test_changed_tail_content_and_bad_prefix_identity_are_rejected(self):
        f = self.fixture
        rows, _ = ev.load_cases(self.tail_dataset)
        rows[0]["prompt"] = "Changed question"
        f.write_jsonl(self.tail_dataset, rows)
        manifest = json.loads(self.manifest.read_text())
        manifest["remaining_dataset_sha256"] = ev.digest(self.tail_dataset.read_bytes())
        f.write_json(self.manifest, manifest)
        with self.assertRaisesRegex(ev.EvaluationError, "exact frozen prefix and tail"):
            self.summarize()
        f.write_jsonl(self.tail_dataset, f.cases[2:])
        manifest["remaining_dataset_sha256"] = ev.digest(self.tail_dataset.read_bytes())
        manifest["first_four_case_ids"].reverse()
        f.write_json(self.manifest, manifest)
        with self.assertRaisesRegex(ev.EvaluationError, "exact frozen prefix and tail"):
            self.summarize()

    def test_an_adapter_cannot_be_used_as_the_unchanged_control(self):
        manifest = json.loads((self.prefix / "manifest.json").read_text())
        manifest["settings"]["adapter_sampler_path"] = "tinker://PRIVATE_ADAPTER/sampler_weights/test"
        self.fixture.save_eval_manifest(self.prefix, manifest)
        with self.assertRaisesRegex(ev.EvaluationError, "unchanged base model"):
            self.summarize()

    def test_generation_and_system_prompt_changes_are_rejected(self):
        original = json.loads((self.prefix / "manifest.json").read_text())
        changed = copy.deepcopy(original)
        changed["settings"]["temperature"] = 0.1
        self.fixture.save_eval_manifest(self.prefix, changed)
        with self.assertRaisesRegex(ev.EvaluationError, "generation settings"):
            self.summarize()
        changed = copy.deepcopy(original)
        changed["system_prompt_sha256"] = "8" * 64
        self.fixture.save_eval_manifest(self.prefix, changed)
        with self.assertRaisesRegex(ev.EvaluationError, "generation settings"):
            self.summarize()

    def test_incomplete_error_and_pending_results_are_explicit(self):
        rows = self.events(self.prefix)
        rows[1]["answer_complete"] = False
        rows[1]["finish_reason"] = "length"
        rows[1]["truncated"] = True
        rows[1]["raw_response_redacted"]["choices"][0]["finish_reason"] = "length"
        rows[3] = {"event": "error", "case_id": rows[3]["case_id"], "elapsed_seconds": 240,
                   "accounting_uncertain": True, "accounted_cost_usd": 0.1}
        self.fixture.write_jsonl(self.prefix / "events.jsonl", rows)
        rows = self.events(self.tail)
        self.fixture.write_jsonl(self.tail / "events.jsonl", rows[:1])
        with (self.tail / "events.jsonl").open("a") as handle:
            handle.write('{"event":"completed"')
        result = self.summarize()
        self.assertTrue(result["partial"])
        counts = result["observations"]["repeat_control"]["counts"]
        self.assertEqual((counts["incomplete_answers"], counts["errors"], counts["unresolved"], counts["not_started"]), (1, 1, 1, 1))
        self.assertEqual(result["comparison"]["paired_returned_responses"], 1)
        self.assertFalse(result["comparison"]["all_question_prompt_hashes_verified"])

    def test_first_run_must_have_recorded_full_dataset_hash(self):
        manifest = json.loads((self.prefix / "manifest.json").read_text())
        manifest["dataset_sha256"] = "0" * 64
        self.fixture.save_eval_manifest(self.prefix, manifest)
        with self.assertRaisesRegex(ev.EvaluationError, "exact dataset bytes"):
            self.summarize()


if __name__ == "__main__":
    unittest.main()
