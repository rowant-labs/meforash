import copy
import json
import unittest
from unittest.mock import patch

from bibleprep import summarize_instruction_calibration as subject
from tests import test_summarize_instruction as fixtures


class CalibrationSummaryTests(unittest.TestCase):
    def setUp(self):
        old = fixtures.InstructionSummaryTests()
        old.setUp()
        self.addCleanup(old.doCleanups)
        self.old, self.root, self.write = old, old.root, old.write
        self.cases = copy.deepcopy(old.cases)
        for i in range(6):
            self.cases.append({"id": f"R{i}", "language": "english", "category": "general_retention",
                "prompt": "PRIVATE PROMPT CANARY", "provided_evidence": "", "source_refs": [],
                "expected_behavior": "PRIVATE CRITERION CANARY", "review_status": "fixture",
                "automatic_checks": [{"id": "fixture", "kind": "json_field_equals",
                    "scope": "provided_fixture_only", "expected_fields": {"result": "yes"}}]})
        path = "evals/calibration.jsonl"
        self.write(path, b"".join(fixtures.canonical(c) + b"\n" for c in self.cases))
        self.dataset_path = self.root / path
        self.dataset_hash = subject.ev.digest(self.dataset_path.read_bytes())
        self.protocol_hash = "c" * 64
        self.protocol = {"evaluation": {"path": path, "sha256": self.dataset_hash, "cases": 30,
                "case_ids": [c["id"] for c in self.cases]},
            "matched_settings": old.protocol["matched_settings"],
            "system_prompt_sha256": subject.ev.digest(subject.ev.SYSTEM_PROMPT.encode()),
            "reference_checkpoints": {a: {"checkpoint_file": "runs/synthetic/checkpoints.json"} for a in "BD"},
            "budget": {"per_arm_sampling_cap_usd": 1.5}}
        self.identities = {a: ("tinker://PRIVATE-" + a, a.lower() * 64) for a in "BDE"}
        self.events = {}
        for arm in subject.experiment.STATES:
            settings = {**old.settings, "experiment_arm": arm, "model_state": subject.experiment.STATES[arm],
                "calibration_protocol_sha256": self.protocol_hash, "diagnostic_version": "native-diagnostics-v1",
                "budget_usd": 1.5, "transport": "native_tinker_inkling_base_diagnostics_v1" if arm == "A"
                    else "native_tinker_inkling_adapter_diagnostics_v1"}
            if arm != "A":
                settings.update(adapter_sampler_path=self.identities[arm][0], checkpoint_reference_sha256=self.identities[arm][1])
            manifest = {"dataset_sha256": self.dataset_hash,
                "system_prompt_sha256": self.protocol["system_prompt_sha256"], "settings": settings,
                "case_ids": [c["id"] for c in self.cases], "schema_version": 1, "dry_run_at_creation": False}
            self.save_manifest(arm, manifest)
            events = []
            for case in self.cases:
                answer = '{"result":"yes"}' if case["language"] == "english" else "PRIVATE ANSWER CANARY"
                usage = {"input_tokens": 100, "output_tokens": 200}
                events.extend([{"event": "started", "case_id": case["id"], "reserved_cost_usd": .05},
                    {"event": "completed", "case_id": case["id"], "accounted_cost_usd": .001123,
                     "elapsed_seconds": 4., "answer_complete": True, "finish_reason": "stop", "truncated": False,
                     "usage": usage, "accounting_uncertain": False, "limit_breach": False,
                     "format_checks": subject.ev.check_format(case, answer),
                     "raw_response_redacted": {"private_id": "PRIVATE PROVIDER CANARY",
                        "choices": [{"message": {"content": answer}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 100, "completion_tokens": 200},
                        "native_tinker": {"prompt_sha256": subject.ev.digest(case["id"].encode()), "parse_issues": []}}}])
            self.events[arm] = events
            self.save_events(arm)
        self.training = {"status": "complete", "compute_estimate_usd": .48149508,
            "checkpoint_contingency_usd": 3., "planned_estimated_or_reserved_usd": 3.48149508}

    def directory(self, arm):
        return self.root / f"runs/instruction-calibration-eval-{arm.lower()}-v2"

    def save_manifest(self, arm, manifest):
        identity = {k: manifest[k] for k in ("dataset_sha256", "system_prompt_sha256", "settings", "case_ids", "schema_version")}
        manifest["fingerprint"] = subject.ev.digest(subject.ev.json_bytes(identity))
        self.write(self.directory(arm) / "manifest.json", manifest)

    def save_events(self, arm):
        self.write(self.directory(arm) / "events.jsonl", b"".join(fixtures.canonical(e) + b"\n" for e in self.events[arm]))

    def collect(self, diagnostic=None):
        with patch.object(subject.experiment, "load_protocol", return_value=(self.protocol, self.protocol_hash)), \
             patch.object(subject.experiment, "verified_dataset", return_value=(self.dataset_path, self.cases)), \
             patch.object(subject.experiment, "verified_checkpoint", side_effect=lambda arm, *a, **k: self.identities[arm]), \
             patch.object(subject, "training_record", return_value=(self.training, self.identities["E"])), \
             patch("bibleprep.native_diagnostics_v1.verify_private_artifact", create=True,
                side_effect=diagnostic or (lambda *a: {"raw_token_ids_verified": True})):
            return subject.collect(self.root)

    def test_complete_counts_cost_and_no_private_content(self):
        result, _, _ = self.collect()
        self.assertTrue(result["execution_complete"])
        self.assertEqual(result["comparison_validation"]["returned_four_arm_prompt_groups_verified"], 30)
        self.assertAlmostEqual(result["cost"]["incremental_total_estimated_or_reserved_usd"], 3.48149508 + 120 * .001123)
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("tinker://", json.dumps(result))
        for arm in "ABDE":
            self.assertEqual(result["english_evaluation"][arm]["general_english_retention"]["completed_and_passed"], 6)
            self.assertEqual(result["english_evaluation"][arm]["by_language"]["english"]["selected"], 6)

    def test_native_failure_is_retained_and_not_counted_as_fixture_success(self):
        event = self.events["E"][-1]
        event.update(answer_complete=False, finish_reason="length", truncated=True)
        event["raw_response_redacted"]["choices"][0]["finish_reason"] = "length"
        self.save_events("E")
        result, _, _ = self.collect()
        self.assertEqual(result["status"], "complete_with_incomplete_answers")
        self.assertEqual(result["english_evaluation"]["E"]["general_english_retention"]["completed_and_passed"], 5)
        self.assertEqual(result["english_evaluation"]["E"]["counts"]["incomplete_answers"], 1)

    def test_missing_request_stays_missing(self):
        self.events["D"] = self.events["D"][:-2]
        self.save_events("D")
        result, _, _ = self.collect()
        self.assertFalse(result["execution_complete"])
        self.assertEqual(result["comparison_validation"]["returned_four_arm_prompt_groups_verified"], 29)

    def test_prompt_mismatch_rejected(self):
        self.events["B"][1]["raw_response_redacted"]["native_tinker"]["prompt_sha256"] = "0" * 64
        self.save_events("B")
        with self.assertRaises(subject.ev.EvaluationError): self.collect()

    def test_diagnostic_integrity_failure_rejected(self):
        def invalid(*args):
            raise subject.ev.EvaluationError("Synthetic sidecar mismatch")
        with self.assertRaises(subject.ev.EvaluationError): self.collect(invalid)

    def test_saved_fixture_result_cannot_override_actual_answer(self):
        self.events["A"][-1]["format_checks"][0]["status"] = "fail"
        self.save_events("A")
        with self.assertRaises(subject.ev.EvaluationError): self.collect()

    def test_wrong_adapter_in_manifest_rejected(self):
        path = self.directory("D") / "manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest["settings"]["adapter_sampler_path"] = "tinker://WRONG"
        self.save_manifest("D", manifest)
        with self.assertRaises(subject.ev.EvaluationError): self.collect()

    def test_review_includes_all_candidates_and_partial_final_without_thinking(self):
        result, snapshots, dataset = self.collect()
        with patch("bibleprep.native_diagnostics_v1.final_text_for_review", create=True,
                   return_value={"partial_final_text": "PRIVATE PARTIAL FINAL", "native_turn_complete": False,
                       "partial_final_status": "present", "final_text_withheld_due_to_malformed_structure": False}):
            outcome = subject.prepare_review(result, snapshots, dataset, self.root)
        self.assertEqual(outcome["candidates"], 120)
        packets = [json.loads(line) for line in (self.root / subject.REVIEW / "cases.jsonl").read_bytes().splitlines()]
        self.assertEqual(len(packets), 30)
        self.assertEqual(sum(len(p["answers"]) for p in packets), 120)
        self.assertTrue(all(a["partial_final_text"] == "PRIVATE PARTIAL FINAL" for p in packets for a in p["answers"]))
        self.assertNotIn("thinking", json.dumps(packets))
        self.assertEqual((self.root / subject.REVIEW / "cases.jsonl").stat().st_mode & 0o777, 0o600)

    def test_review_does_not_hide_why_final_text_was_withheld(self):
        result, snapshots, dataset = self.collect()
        with patch("bibleprep.native_diagnostics_v1.final_text_for_review", create=True,
                   return_value={"partial_final_text": "", "native_turn_complete": False,
                       "partial_final_status": "unknown_due_to_format_error",
                       "final_text_withheld_due_to_malformed_structure": True}):
            subject.prepare_review(result, snapshots, dataset, self.root)
        packet = json.loads((self.root / subject.REVIEW / "cases.jsonl").read_bytes().splitlines()[0])
        self.assertTrue(all(a["final_text_withheld_due_to_malformed_structure"] for a in packet["answers"]))
        self.assertTrue(all(a["partial_final_status"] == "unknown_due_to_format_error" for a in packet["answers"]))


if __name__ == "__main__":
    unittest.main()
