import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bibleprep import evaluate as ev
from bibleprep import summarize_evaluation as summary


class EvaluationSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runs = self.root / "runs"
        self.reports = self.root / "reports"
        for owner, field, value in ((ev, "RUNS_ROOT", self.runs), (summary, "REPORTS_ROOT", self.reports)):
            patcher = patch.object(owner, field, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.dataset = self.root / "cases.jsonl"
        self.cases = [{"id": str(index), "prompt": "PRIVATE ANSWER AND USER ID CANARY", "language": "hebrew",
                       "category": "translation", "source_refs": [], "expected_behavior": "PRIVATE GOLD CANARY",
                       "review_status": "unreviewed"} for index in range(5)]
        self.dataset.write_text("".join(json.dumps(case) + "\n" for case in self.cases))
        self.dataset_hash = ev.digest(self.dataset.read_bytes())
        self.run_dir = self.runs / "fixture"
        self.run_dir.mkdir(parents=True)
        self.manifest = {
            "case_ids": [case["id"] for case in self.cases], "dataset_sha256": self.dataset_hash,
            "account_id": "PRIVATE ACCOUNT CANARY",
            "settings": {"model": "openai/gpt-oss-120b", "reasoning_effort": "low", "evidence_mode": "provided",
                         "input_price_per_million": 0.33, "output_price_per_million": 0.84,
                         "api_key": "PRIVATE KEY CANARY", "run_dir": "/Users/private-account/secret"},
        }
        self.save_manifest()
        self.events = []

    def save_manifest(self):
        (self.run_dir / "manifest.json").write_text(json.dumps(self.manifest))

    def start(self, case_id):
        self.events.append({"event": "started", "case_id": str(case_id), "reserved_cost_usd": 0.01})

    def complete(self, case_id, *, complete=True, usage=True):
        self.events.append({"event": "completed", "case_id": str(case_id), "answer_complete": complete,
                            "accounted_cost_usd": 0.000201 if usage else 0.01, "accounting_uncertain": not usage,
                            "usage": {"input_tokens": 100, "output_tokens": 200} if usage else None,
                            "human_review": "pending", "format_checks": [{"status": "pass"}],
                            "raw_response_redacted": {"content": "PRIVATE ANSWER AND USER ID CANARY"}})

    def save_events(self):
        (self.run_dir / "events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in self.events))

    def report(self):
        self.save_events()
        return summary.summarize([self.run_dir], dataset=self.dataset)

    def test_partial_counts_separate_completed_incomplete_errors_and_pending(self):
        self.start(0)
        self.complete(0)
        self.start(1)
        self.complete(1, complete=False)
        self.start(2)
        self.events.append({"event": "error", "case_id": "2", "accounted_cost_usd": 0.01, "accounting_uncertain": True})
        self.start(3)
        report = self.report()
        run = report["runs"][0]
        self.assertTrue(report["partial"])
        self.assertEqual(run["status"], "partial")
        self.assertEqual(run["counts"]["successful_answers"], 1)
        self.assertEqual(run["counts"]["incomplete_answers"], 1)
        self.assertEqual(run["counts"]["completed_responses"], 2)
        self.assertEqual(run["counts"]["errors"], 1)
        self.assertEqual(run["counts"]["unresolved_requests"], 1)
        self.assertEqual(run["counts"]["not_started"], 1)
        self.assertEqual(run["counts"]["pending_results"], 2)
        self.assertEqual(run["counts"]["scholarly_reviews_pending"], 2)
        self.assertEqual(run["tokens"]["input"], 200)
        self.assertEqual(run["tokens"]["output"], 400)
        self.assertAlmostEqual(run["cost"]["known_token_estimate_usd"], 0.000402)
        self.assertAlmostEqual(run["cost"]["successful_answer_token_estimate_usd"], 0.000201)
        self.assertAlmostEqual(run["cost"]["uncertain_accounted_or_reserved_usd"], 0.02)
        self.assertAlmostEqual(run["cost"]["journal_accounted_or_reserved_usd"], 0.020402)
        self.assertEqual(run["cost"]["uncertain_requests"], 2)
        self.assertFalse(run["cost"]["provider_invoice_verified"])
        self.assertEqual(run["by_category"]["translation"]["pending"], 2)

    def test_completed_report_has_zero_pending_but_scholarly_review_stays_pending(self):
        for case in self.cases:
            self.start(case["id"])
            self.complete(case["id"])
        report = self.report()
        self.assertFalse(report["partial"])
        self.assertEqual(report["runs"][0]["status"], "complete")
        self.assertEqual(report["totals"]["scholarly_reviews_pending"], 5)
        self.assertEqual(report["totals"]["pending_results"], 0)

    def test_report_excludes_raw_answers_gold_credentials_identities_and_paths(self):
        self.start(0)
        self.complete(0)
        report = self.report()
        serialized = json.dumps(report)
        for canary in ("PRIVATE", "/Users/", str(self.root), "raw_response_redacted", "api_key", "case_ids"):
            self.assertNotIn(canary, serialized)
        self.assertEqual(report["runs"][0]["run"], "fixture")
        self.assertEqual(report["runs"][0]["source_hashes"]["dataset_sha256"], self.dataset_hash)

    def test_mismatched_dataset_never_assigns_guessed_categories(self):
        self.manifest["dataset_sha256"] = "0" * 64
        self.save_manifest()
        report = self.report()
        run = report["runs"][0]
        self.assertFalse(run["category_metadata_matches_dataset"])
        self.assertEqual(set(run["by_category"]), {"unknown"})

    def test_missing_usage_and_unknown_prices_are_explicit(self):
        self.manifest["settings"].pop("input_price_per_million")
        self.save_manifest()
        self.start(0)
        self.complete(0, usage=False)
        report = self.report()
        self.assertIsNone(report["totals"]["known_token_estimate_usd"])
        self.assertEqual(report["runs"][0]["tokens"]["results_missing_usage"], 1)
        self.assertFalse(report["runs"][0]["cost"]["token_estimate_covers_all_started_requests"])

    def test_dry_run_no_journal_and_no_network_or_environment_access(self):
        with patch.object(ev, "load_project_environment") as environment, patch.object(ev, "send_request") as network:
            report = summary.summarize([self.run_dir], dataset=self.dataset)
        environment.assert_not_called()
        network.assert_not_called()
        self.assertEqual(report["runs"][0]["status"], "dry_run")
        self.assertEqual(report["totals"]["started_requests"], 0)

    def test_half_written_journal_tail_is_reported_as_partial_snapshot(self):
        self.start(0)
        self.save_events()
        journal = self.run_dir / "events.jsonl"
        with journal.open("a") as handle:
            handle.write('{"event":"completed"')
        report = summary.summarize([self.run_dir], dataset=self.dataset)
        self.assertTrue(report["runs"][0]["journal_has_incomplete_tail"])
        self.assertEqual(report["totals"]["unresolved_requests"], 1)
        self.assertEqual(report["runs"][0]["source_hashes"]["events_sha256"], ev.digest(journal.read_bytes()))

    def test_duplicate_runs_and_escaped_artifact_paths_are_rejected(self):
        with self.assertRaises(ev.EvaluationError):
            summary.summarize([self.run_dir, self.run_dir], dataset=self.dataset)
        with self.assertRaises(ev.EvaluationError):
            summary.summarize([self.root / "outside"], dataset=self.dataset)
        with self.assertRaises(ev.EvaluationError):
            summary.write_report({}, self.root / "outside.json")

    def test_report_is_atomically_replaced_inside_reports(self):
        target = self.reports / "aggregate.json"
        summary.write_report({"version": 1}, target)
        summary.write_report({"version": 2}, target)
        self.assertEqual(json.loads(target.read_text()), {"version": 2})
        self.assertFalse(target.with_suffix(".json.tmp").exists())

    def test_verified_subset_reuses_only_identical_original_cases(self):
        for case in self.cases:
            self.start(case["id"])
            self.complete(case["id"])
        self.save_events()
        subset = self.root / "subset.jsonl"
        subset.write_text("".join(json.dumps(case) + "\n" for case in self.cases[:2]))
        original = (self.run_dir / "events.jsonl").read_bytes()
        report = summary.summarize([self.run_dir], dataset=self.dataset, subset_dataset=subset)
        run = report["runs"][0]
        self.assertEqual(run["counts"]["successful_answers"], 2)
        self.assertEqual(run["original_selected_cases"], 5)
        self.assertEqual(run["observation_scope"], "verified_subset")
        self.assertEqual(run["tokens"]["input"], 200)
        self.assertEqual(run["source_hashes"]["events_sha256"], ev.digest(original))
        self.assertEqual((self.run_dir / "events.jsonl").read_bytes(), original)
        changed = dict(self.cases[0], prompt="Different question")
        subset.write_text(json.dumps(changed) + "\n")
        with self.assertRaises(ev.EvaluationError):
            summary.summarize([self.run_dir], dataset=self.dataset, subset_dataset=subset)

    def test_subset_refuses_unverified_run_dataset(self):
        subset = self.root / "subset.jsonl"
        subset.write_text(json.dumps(self.cases[0]) + "\n")
        self.manifest["dataset_sha256"] = "0" * 64
        self.save_manifest()
        with self.assertRaises(ev.EvaluationError):
            summary.summarize([self.run_dir], dataset=self.dataset, subset_dataset=subset)


if __name__ == "__main__":
    unittest.main()
