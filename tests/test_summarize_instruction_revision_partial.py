import copy
import json
import math
import unittest
from unittest.mock import patch

from bibleprep import summarize_instruction_revision_partial as subject
from tests import test_summarize_instruction_revision as fixture_tests


class PartialRevisionSummaryTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_tests.RevisionSummaryTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.root = self.base.root
        self.error_case = self.base.cases[4]["id"]
        self.contingency = {"original_protocol": {"sha256": self.base.protocol_hash},
            "stopped_arms": {"E": {"terminal_error_case_id": self.error_case, "policy": "no_retry_or_further_requests"}}}
        self.contingency_hash = "a" * 64
        guard = patch.object(subject, "load_contingency", return_value=(self.contingency, self.contingency_hash))
        guard.start()
        self.addCleanup(guard.stop)
        settings = self.base.old.settings
        self.reservation = subject.ev.estimated_cost(settings["max_input_tokens"], settings["max_output_tokens"], settings)
        for arm in "ABEF":
            for event in self.base.events[arm]:
                if event["event"] == "started":
                    event["reserved_cost_usd"] = self.reservation
                else:
                    event["raw_response_redacted"]["native_tinker"]["private_diagnostic_artifact"] = {
                        "file": "PRIVATE SIDECAR CANARY", "sha256": "d" * 64}
            self.base.save_events(arm)
        events = self.base.events["E"][:9]
        events.append({"event": "error", "case_id": self.error_case, "elapsed_seconds": 300.0384,
            "error": {"kind": "network_error"}, "accounted_cost_usd": self.reservation, "accounting_uncertain": True})
        self.base.events["E"] = events
        self.base.save_events("E")
        for arm in "ABEF":
            self.save_summary(arm)
        self.old_hashes = {name: subject.ev.digest((self.root / name).read_bytes()) for name in
            ("evals/revision.jsonl",)}

    def save_summary(self, arm, **changes):
        results = [e for e in self.base.events[arm] if e["event"] != "started"]
        summary = {"mode": "execute", "selected_cases": 30, "completed_cases": len(results),
            "pending_cases": 30 - len(results), "accounted_cost_usd": math.fsum(e["accounted_cost_usd"] for e in results),
            "per_request_reservation_usd": self.reservation,
            "remaining_worst_case_usd": self.reservation * (30 - len(results)),
            "stop_reason": "uncertain_billing_or_provider_limit_breach" if any(e["event"] == "error" for e in results)
                else "all_selected_cases_completed"}
        summary.update(changes)
        self.base.write(self.base.directory(arm) / "summary.json", summary)

    def collect(self):
        # Frozen validation runs on synthetic journals first. No real answers,
        # checkpoints, sidecars, service calls or credentials are involved.
        collected = self.base.collect()
        with patch.object(subject.frozen, "collect", return_value=collected):
            return subject.collect(self.root)

    def prepare(self, result, snapshots, dataset):
        with patch("bibleprep.native_diagnostics_v1.final_text_for_review", return_value={
            "partial_final_text": "PRIVATE PARTIAL CANARY", "native_turn_complete": False,
            "partial_final_status": "present", "final_text_withheld_due_to_malformed_structure": False}):
            return subject.prepare_review(result, snapshots, dataset, self.root)

    def test_closed_error_round_has_120_slots_and_94_real_candidates(self):
        result, _, _ = self.collect()
        self.assertTrue(result["collection_closed"])
        self.assertFalse(result["execution_complete"])
        self.assertEqual(result["availability"]["intended_slots"], 120)
        self.assertEqual({k: result["availability"][k] for k in subject.STATUSES},
                         {"returned": 94, "error": 1, "not_started": 25, "unresolved": 0})
        self.assertEqual(result["availability"]["by_arm"]["E"]["returned"], 4)
        self.assertEqual(result["english_evaluation"]["E"]["counts"]["received"], 5)
        self.assertEqual(result["terminal_summaries"]["E"]["terminal_receipts"], 5)
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("tinker://", json.dumps(result))

    def test_pairwise_denominators_are_joint_returns_not_missing_failures(self):
        result, _, _ = self.collect()
        denominators = result["comparison_validation"]["paired_returned_denominators"]
        self.assertEqual(denominators["B_vs_F"]["available_bible_cases"], 24)
        self.assertEqual(denominators["B_vs_E"]["available_bible_cases"], 4)
        self.assertEqual(denominators["E_vs_F"]["available_general_cases"], 0)
        self.assertTrue(all(item["fixture_checks_passed"] is None and item["answer_complete"] is None
                            for item in result["english_evaluation"]["E"]["general_english_retention"]["results"]))

    def test_packet_does_not_invent_unavailable_answers(self):
        result, snapshots, dataset = self.collect()
        outcome = self.prepare(result, snapshots, dataset)
        self.assertEqual(outcome["available_candidates"], 94)
        path = self.root / subject.REVIEW / "cases.jsonl"
        packets = [json.loads(line) for line in path.read_bytes().splitlines()]
        self.assertEqual(len(packets), 30)
        self.assertEqual(sum(len(p["answers"]) for p in packets), 94)
        self.assertEqual(sum(len(p["unavailable_candidates"]) for p in packets), 26)
        self.assertEqual([p["available_candidate_count"] for p in packets], [4] * 4 + [3] * 26)
        self.assertTrue(all("answer" not in a and "assessment" not in a and "answer_complete" not in a
                            for p in packets for a in p["unavailable_candidates"]))
        self.assertTrue(all(a["partial_final_text"] == "PRIVATE PARTIAL CANARY" for p in packets for a in p["answers"]))
        self.assertNotIn("thinking", json.dumps(packets))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.root / subject.frozen.REVIEW).exists())
        for name, expected in self.old_hashes.items():
            self.assertEqual(subject.ev.digest((self.root / name).read_bytes()), expected)

    def test_candidate_receipt_hashes_bind_actual_native_events(self):
        result, snapshots, dataset = self.collect()
        self.prepare(result, snapshots, dataset)
        packets = [json.loads(line) for line in (self.root / subject.REVIEW / "cases.jsonl").read_bytes().splitlines()]
        terminal_hashes = {subject.event_sha256(e) for rows in self.base.events.values() for e in rows if e["event"] == "completed"}
        for p in packets:
            for a in p["answers"]:
                self.assertIn(a["terminal_event_sha256"], terminal_hashes)
                self.assertEqual(a["diagnostic_artifact_sha256"], "d" * 64)

    def test_not_started_in_an_active_arm_does_not_close_collection(self):
        self.base.events["F"] = self.base.events["F"][:-2]
        self.base.save_events("F")
        self.save_summary("F", mode="dry_run", stop_reason="dry_run")
        result, snapshots, dataset = self.collect()
        self.assertFalse(result["collection_closed"])
        with self.assertRaises(subject.ev.EvaluationError):
            self.prepare(result, snapshots, dataset)

    def test_unresolved_request_is_visible_and_cannot_be_reviewed(self):
        self.base.events["F"] = self.base.events["F"][:-1]
        self.base.save_events("F")
        self.save_summary("F", mode="dry_run", stop_reason="dry_run")
        result, snapshots, dataset = self.collect()
        self.assertEqual(result["availability"]["unresolved"], 1)
        with self.assertRaises(subject.ev.EvaluationError):
            self.prepare(result, snapshots, dataset)

    def test_error_stop_requires_explicit_contingency_policy(self):
        self.contingency["stopped_arms"] = {}
        result, _, _ = self.collect()
        self.assertFalse(result["collection_closed"])

    def test_wrong_terminal_case_is_rejected(self):
        self.contingency["stopped_arms"]["E"]["terminal_error_case_id"] = self.base.cases[3]["id"]
        with self.assertRaises(subject.ev.EvaluationError):
            self.collect()

    def test_summary_counters_and_cost_tampering_rejected(self):
        self.save_summary("E", completed_cases=4)
        with self.assertRaises(subject.ev.EvaluationError):
            self.collect()
        self.save_summary("E", accounted_cost_usd=0.)
        with self.assertRaises(subject.ev.EvaluationError):
            self.collect()

    def test_summary_change_after_collection_stops_packet_write(self):
        result, snapshots, dataset = self.collect()
        path = self.base.directory("E") / "summary.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(subject.ev.EvaluationError):
            self.prepare(result, snapshots, dataset)
        self.assertFalse((self.root / subject.REVIEW).exists())

    def test_native_partial_is_a_returned_response_not_an_unavailable_slot(self):
        e = self.base.events["F"][-1]
        e.update(answer_complete=False, finish_reason="length", truncated=True)
        e["raw_response_redacted"]["choices"][0]["finish_reason"] = "length"
        self.base.save_events("F")
        self.save_summary("F")
        result, _, _ = self.collect()
        self.assertEqual(result["availability"]["returned"], 94)
        self.assertEqual(result["english_evaluation"]["F"]["counts"]["incomplete_answers"], 1)

    def test_further_requests_after_a_terminal_error_rejected(self):
        case = self.base.cases[5]
        self.base.events["E"].append({"event": "started", "case_id": case["id"], "reserved_cost_usd": self.reservation})
        self.base.save_events("E")
        self.save_summary("E")
        with self.assertRaises(subject.ev.EvaluationError):
            self.collect()

    def test_overlapping_starts_are_rejected(self):
        e = self.base.events["B"]
        e[1], e[2] = e[2], e[1]
        self.base.save_events("B")
        with self.assertRaises(subject.ev.EvaluationError):
            self.collect()

    def test_reservation_and_returned_charge_tampering_rejected(self):
        self.base.events["B"][0]["reserved_cost_usd"] = 0.1
        self.base.save_events("B")
        with self.assertRaises(subject.ev.EvaluationError):
            self.collect()
        self.base.events["B"][0]["reserved_cost_usd"] = self.reservation
        self.base.events["B"][1]["accounted_cost_usd"] *= 2
        self.base.save_events("B")
        self.save_summary("B")
        with self.assertRaises(subject.ev.EvaluationError):
            self.collect()

    def test_error_charge_cannot_be_rewritten_even_with_matching_summary(self):
        self.base.events["E"][-1]["accounted_cost_usd"] = 0.
        self.base.save_events("E")
        self.save_summary("E")
        with self.assertRaises(subject.ev.EvaluationError):
            self.collect()


if __name__ == "__main__":
    unittest.main()
