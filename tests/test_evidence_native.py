"""Offline checks for the constructed native-result bridge."""
import copy
import json
import unittest
from unittest.mock import patch

from bibleprep import evidence_native as bridge
from bibleprep import native_diagnostics_v1 as native
from bibleprep.evidence_collection import canonical_sha256


PRIVATE = "PRIVATE_NATIVE_THINKING_SENTINEL"


def diagnostic(final="Constructed final.", *, partial="", finish="stop", malformed=False):
    raw_ids = [11, 12, 13]
    complete = finish == "stop"
    provider = "stop" if finish == "stop" else "length" if finish == "length" else "unknown"
    issues = ["native_tml_parse_error"] if malformed else []
    partial_status = (
        "present_before_parse_error" if malformed and partial else
        "present" if partial else
        "unknown_due_to_parse_error" if malformed else "absent"
    )
    state = (
        "unknown_due_to_parse_error" if malformed else
        "completed_and_partial" if final and partial else
        "completed_messages_only" if final else "partial_only" if partial else "absent"
    )
    return {
        "schema_version": 1,
        "parser_profile": "official_tml_streaming_v1",
        "raw_generated_token_ids": raw_ids,
        "raw_generated_token_ids_sha256": native.token_ids_sha256(raw_ids),
        "generated_token_count": len(raw_ids),
        "parsed_token_count": 2 if malformed else len(raw_ids),
        "completed_final_text": final,
        "partial_final_text": partial,
        "completed_thinking_text": PRIVATE,
        "partial_thinking_text": "",
        "completed_final_message_count": 1 if final else 0,
        "completed_thinking_message_count": 1,
        "completed_final_characters": len(final),
        "partial_final_characters": len(partial),
        "completed_thinking_characters": len(PRIVATE),
        "partial_thinking_characters": 0,
        "partial_final_status": partial_status,
        "partial_thinking_status": "absent",
        "final_content_state": state,
        "header_open": bool(partial),
        "parser_at_message_boundary": complete,
        "stream_extraction_finished_without_error": not malformed,
        "turn_end_token_present": complete,
        "turn_end_observed": complete,
        "native_turn_complete": complete and not malformed,
        "provider_stop_reason": provider,
        "finish_reason": finish,
        "parse_issues": issues,
        "diagnostic_warnings": [],
        "semantic_answer_completeness": "not_assessed",
        "analysis_content_tokens": None,
        "prompt_token_ids_sha256": "d" * 64,
        "prompt_token_count": 7,
    }


def plan(count=3):
    arms = ("B-memory", "B-packet", "B-lookup")
    slots = []
    for index, arm in enumerate(arms[:count]):
        model_input = {
            "system_prompt": "Constructed policy.",
            "question": "Constructed question.",
            "evidence": "" if arm == "B-memory" else "Constructed evidence.",
        }
        slots.append({
            "slot_id": f"case-one--{arm.lower()}",
            "case_id": "case-one",
            "arm": arm,
            "status": "planned_offline",
            "model_input": model_input,
            "model_input_sha256": canonical_sha256(model_input),
        })
    return {
        "schema_version": 1,
        "planner_kind": "constructed_offline_evidence_inventory",
        "engineering_readiness": {"status": "ready", "reasons": []},
        "execution_readiness": {
            "status": "not_ready",
            "open_requirements": ["constructed_fixture_is_not_execution_authority"],
        },
        "planned_slot_count": len(slots),
        "planned_slots": slots,
        "model_calls": 0,
        "network_requests": 0,
    }


def fixture(slot, payload=None, *, outcome="diagnostic", disposition="uncertain"):
    payload = payload if payload is not None else (
        {"disposition": disposition} if outcome == "failure" else diagnostic()
    )
    return {
        "schema_version": 1,
        "fixture_kind": "constructed_native_outcome_v1",
        "slot_id": slot["slot_id"],
        "model_input_sha256": slot["model_input_sha256"],
        "outcome_kind": outcome,
        "payload": payload,
        "payload_sha256": canonical_sha256(payload),
    }


class EvidenceNativeTests(unittest.TestCase):
    def test_complete_simulation_emits_strict_bound_journal_without_thinking(self):
        prepared = plan()
        fixtures = [fixture(slot) for slot in prepared["planned_slots"]]
        record = bridge.simulate_sequential_collection(prepared, fixtures)

        self.assertEqual(record["audit"]["totals"]["complete"], 3)
        self.assertEqual(record["audit"]["totals"]["unsubmitted"], 0)
        self.assertEqual(record["execution_readiness"], prepared["execution_readiness"])
        self.assertEqual(record["model_calls"], 0)
        self.assertEqual(record["network_requests"], 0)
        for index in range(0, len(record["journal"]), 2):
            self.assertEqual(record["journal"][index], {
                "event": "submission",
                "slot_id": prepared["planned_slots"][index // 2]["slot_id"],
            })
            self.assertEqual(set(record["journal"][index + 1]), {
                "event", "slot_id", "stop_reason", "final_text", "receipt_sha256",
            })
        self.assertNotIn(PRIVATE, json.dumps(record))
        self.assertEqual(bridge.verify_simulated_collection(prepared, fixtures, record), record["audit"])

    def test_output_limit_keeps_partial_final_and_all_later_slots_unsubmitted(self):
        prepared = plan()
        first = fixture(prepared["planned_slots"][0])
        partial = diagnostic(final="First closed", partial="Visible tail", finish="length")
        second = fixture(prepared["planned_slots"][1], partial)
        record = bridge.simulate_sequential_collection(prepared, [first, second])

        self.assertEqual(record["journal"][-1]["stop_reason"], "output_limit")
        self.assertEqual(record["journal"][-1]["final_text"], "First closed\nVisible tail")
        self.assertEqual(record["audit"]["totals"], {
            "planned": 3, "complete": 1, "partial": 1, "failed": 0,
            "uncertain": 0, "outstanding": 0, "unsubmitted": 1,
        })
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "after the fixed stop-all"):
            bridge.simulate_sequential_collection(
                prepared, [first, second, fixture(prepared["planned_slots"][2])]
            )

    def test_uncertain_failure_stops_without_retry(self):
        prepared = plan()
        failed = fixture(prepared["planned_slots"][0], outcome="failure")
        record = bridge.simulate_sequential_collection(prepared, [failed])

        self.assertEqual([event["event"] for event in record["journal"]], ["submission", "failure"])
        self.assertEqual(record["audit"]["totals"]["uncertain"], 1)
        self.assertEqual(record["audit"]["totals"]["unsubmitted"], 2)
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "after the fixed stop-all"):
            bridge.simulate_sequential_collection(
                prepared, [failed, fixture(prepared["planned_slots"][1])]
            )

    def test_malformed_and_ambiguous_diagnostics_fail_closed(self):
        malformed = diagnostic(final="Withheld", finish="incomplete_tml", malformed=True)
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "malformed native parser"):
            bridge.normalize_diagnostic_artifact(malformed, canonical_sha256(malformed))

        inconsistent = diagnostic()
        inconsistent["native_turn_complete"] = False
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "native stop evidence"):
            bridge.normalize_diagnostic_artifact(inconsistent, canonical_sha256(inconsistent))

        status = diagnostic(final="", partial="Visible", finish="length")
        status["partial_final_status"] = "absent"
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "partial final status"):
            bridge.normalize_diagnostic_artifact(status, canonical_sha256(status))

    def test_tampered_plan_input_diagnostic_and_binding_are_rejected(self):
        prepared = plan(1)
        fixtures = [fixture(prepared["planned_slots"][0])]
        record = bridge.simulate_sequential_collection(prepared, fixtures)

        changed_slot = copy.deepcopy(prepared)
        changed_slot["planned_slots"][0]["arm"] = "tampered"
        with self.assertRaises(bridge.EvidenceNativeError):
            bridge.verify_simulated_collection(changed_slot, fixtures, record)

        changed_input = copy.deepcopy(prepared)
        changed_input["planned_slots"][0]["model_input"]["question"] = "Changed"
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "model_input_sha256"):
            bridge.simulate_sequential_collection(changed_input, fixtures)

        changed_diagnostic = copy.deepcopy(fixtures)
        changed_diagnostic[0]["payload"]["completed_final_text"] = "Changed"
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "payload hash"):
            bridge.simulate_sequential_collection(prepared, changed_diagnostic)

        missing_binding = copy.deepcopy(record)
        missing_binding["receipt_bindings"] = []
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "exact verification"):
            bridge.verify_simulated_collection(prepared, fixtures, missing_binding)

    def test_rejects_blocked_live_or_unlabeled_plans_and_incomplete_fixture_lists(self):
        blocked = plan()
        blocked["engineering_readiness"] = {"status": "not_ready", "reasons": ["gap"]}
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "blocked"):
            bridge.simulate_sequential_collection(blocked, [])

        live = plan()
        live["execution_readiness"]["status"] = "ready"
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "retain"):
            bridge.simulate_sequential_collection(live, [])

        prepared = plan()
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "fixtures ended"):
            bridge.simulate_sequential_collection(
                prepared, [fixture(prepared["planned_slots"][0])]
            )

    def test_schema_counts_arm_and_status_are_strict(self):
        prepared = plan(1)
        valid_fixture = fixture(prepared["planned_slots"][0])
        for value in (True, 1.0, "1"):
            with self.subTest(plan_schema=value):
                changed = copy.deepcopy(prepared)
                changed["schema_version"] = value
                with self.assertRaisesRegex(bridge.EvidenceNativeError, "schema_version"):
                    bridge.simulate_sequential_collection(changed, [valid_fixture])
            with self.subTest(fixture_schema=value):
                changed_fixture = copy.deepcopy(valid_fixture)
                changed_fixture["schema_version"] = value
                with self.assertRaisesRegex(bridge.EvidenceNativeError, "labeled constructed"):
                    bridge.simulate_sequential_collection(prepared, [changed_fixture])
            with self.subTest(diagnostic_schema=value):
                changed_diagnostic = diagnostic()
                changed_diagnostic["schema_version"] = value
                with self.assertRaisesRegex(bridge.EvidenceNativeError, "diagnostic must use"):
                    bridge.normalize_diagnostic_artifact(
                        changed_diagnostic, canonical_sha256(changed_diagnostic)
                    )

        for value in (True, 0, 1.0):
            with self.subTest(slot_count=value):
                changed = copy.deepcopy(prepared)
                changed["planned_slot_count"] = value
                with self.assertRaisesRegex(bridge.EvidenceNativeError, "slot inventory"):
                    bridge.simulate_sequential_collection(changed, [valid_fixture])

        for field, value in (("arm", "unknown"), ("status", "blocked_evidence_not_ready")):
            with self.subTest(field=field):
                changed = copy.deepcopy(prepared)
                changed["planned_slots"][0][field] = value
                with self.assertRaisesRegex(bridge.EvidenceNativeError, field):
                    bridge.simulate_sequential_collection(changed, [valid_fixture])

    def test_verifier_distinguishes_boolean_from_numeric_json(self):
        prepared = plan(1)
        fixtures = [fixture(prepared["planned_slots"][0])]
        record = bridge.simulate_sequential_collection(prepared, fixtures)
        changed = copy.deepcopy(record)
        changed["model_calls"] = False  # Equal to 0 under Python object equality.
        self.assertEqual(changed, record)
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "exact verification"):
            bridge.verify_simulated_collection(prepared, fixtures, changed)

    def test_native_completion_requires_explicit_turn_end_token(self):
        changed = diagnostic()
        changed["turn_end_token_present"] = False
        with self.assertRaisesRegex(bridge.EvidenceNativeError, "completion flags"):
            bridge.normalize_diagnostic_artifact(changed, canonical_sha256(changed))

    def test_future_response_adapter_uses_existing_receipt_verification_helpers(self):
        projection = {
            "completed_final_text": "Closed",
            "partial_final_text": "Tail",
            "native_turn_complete": False,
            "finish_reason": "length",
            "partial_final_status": "present",
            "final_text_withheld_due_to_malformed_structure": False,
            "semantic_answer_completeness": "not_assessed",
        }
        summary = {
            "private_artifact_sha256": "a" * 64,
            "raw_generated_token_ids_sha256": "b" * 64,
        }
        response = {"native_tinker": {"prompt_sha256": "c" * 64}}
        with patch.object(native, "final_text_for_review", return_value=projection) as final, \
             patch.object(native, "verify_private_artifact", return_value=summary) as verify:
            result = bridge.normalize_native_response(response, "/private/run")
        final.assert_called_once_with(response, "/private/run")
        verify.assert_called_once_with(response, "/private/run")
        self.assertEqual(result["stop_reason"], "output_limit")
        self.assertEqual(result["final_text"], "Closed\nTail")
        self.assertEqual(result["native_prompt_sha256"], "c" * 64)


if __name__ == "__main__":
    unittest.main()
