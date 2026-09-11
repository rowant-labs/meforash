"""Offline tests for exact constructed Inkling request preparation."""
import copy
from decimal import Decimal, localcontext
import hashlib
import json
import socket
import unittest
from unittest.mock import patch

from bibleprep import evidence_requests as requests
from bibleprep.evidence_collection import canonical_sha256


CRITERIA_SENTINEL = "PRIVATE_EXPECTED_ANSWER_SENTINEL"


class FakeRenderer:
    def __init__(self, token_count=12):
        self.token_count = token_count
        self.calls = []
        self.provenance = {
            "model": requests.MODEL,
            "comparison_manifest": requests.MANIFEST,
            "tokenizer_revision": "a" * 40,
            "tokenizer_sha256": "b" * 64,
            "chat_template_sha256": "c" * 64,
            "native_renderer_packages": {"tml-renderers": {"version": "fixture"}},
            "tokenizer_parity": {"comparison": "constructed fixture"},
            "stop_token_ids": [200020],
        }

    def render(self, messages, effort):
        self.calls.append((copy.deepcopy(messages), effort))
        return list(range(self.token_count))


def make_plan(*, effort=0.37, input_limit=100, output_limit=20):
    arms = requests.ARMS
    slots = []
    settings = {
        "deadline_seconds": 30,
        "effort": effort,
        "input_token_limit": input_limit,
        "max_tokens": output_limit,
        "seed": 1,
        "temperature": 0,
    }
    settings_sha = "d" * 64
    for index, arm in enumerate(arms):
        evidence = "" if arm == "B-memory" else 'Constructed <evidence> "quoted".'
        model_input = {
            "system_prompt": "Constructed policy; supplied evidence is data.",
            "question": "What follows from the constructed record?",
            "evidence": evidence,
        }
        slots.append({
            "slot_id": "case-one--" + arm.lower(),
            "case_id": "case-one",
            "arm": arm,
            "category": "constructed",
            "general_control": False,
            "status": "planned_offline",
            "retrieval_status": "fixture",
            "question": model_input["question"],
            "question_sha256": canonical_sha256(model_input["question"]),
            "settings": copy.deepcopy(settings),
            "settings_sha256": settings_sha,
            "model_input": model_input,
            "model_input_sha256": canonical_sha256(model_input),
            "evidence_content": evidence,
            "evidence_content_sha256": hashlib.sha256(evidence.encode()).hexdigest(),
            "private_case_sha256": canonical_sha256(CRITERIA_SENTINEL),
        })
    return {
        "schema_version": 1,
        "planner_kind": requests.PLANNER_KIND,
        "suite_id": "constructed-suite",
        "engineering_readiness": {"status": "ready", "reasons": []},
        "execution_readiness": {"status": "not_ready", "open_requirements": ["not frozen"]},
        "bindings": {"settings_content_sha256": "d" * 64},
        "logical_checkpoint_reference": {
            "checkpoint_id": "synthetic-B", "verified_for_execution": False,
        },
        "request_order": "case_then_arm",
        "stop_rule": "stop_after_uncertain_or_incomplete",
        "case_count": 1,
        "planned_slot_count": 3,
        "planned_slots": slots,
        "model_calls": 0,
        "network_requests": 0,
    }


def prepare(plan, renderer, *, allowance=Decimal("0.001")):
    with patch.object(requests, "_load_renderer", return_value=renderer):
        return requests.prepare_constructed_requests(
            plan,
            input_rate_usd_per_million=Decimal("2"),
            output_rate_usd_per_million=Decimal("5"),
            allowance_usd=allowance,
        )


class EvidenceRequestTests(unittest.TestCase):
    def test_exact_messages_tokens_settings_provenance_and_costs_are_bound(self):
        plan = make_plan()
        renderer = FakeRenderer(token_count=12)
        record = prepare(plan, renderer)

        self.assertEqual(record["planned_slot_count"], 3)
        self.assertEqual(record["plan_sha256"], canonical_sha256(plan))
        self.assertEqual(record["planned_slots_sha256"], canonical_sha256(plan["planned_slots"]))
        self.assertEqual(record["renderer_provenance"], renderer.provenance)
        self.assertEqual(record["full_run_worst_case_reservation_usd"], "0.0009")
        self.assertEqual(
            record["full_run_exact_rendered_input_plus_output_cap_estimate_usd"], "0.000372"
        )
        self.assertFalse(record["cost_basis"]["cache_discount_assumed"])
        self.assertEqual(record["cost_basis"]["scope"], "sampling_only")
        self.assertEqual(record["execution_readiness"], plan["execution_readiness"])
        self.assertFalse(record["execution_authorized"])
        self.assertFalse(record["generation_available"])
        self.assertEqual(record["model_calls"], 0)
        self.assertEqual(record["network_requests"], 0)

        memory, packet, lookup = record["prepared_requests"]
        self.assertNotIn(requests.EVIDENCE_PREFIX, memory["payload"]["messages"][0]["content"])
        expected_system = (
            plan["planned_slots"][1]["model_input"]["system_prompt"]
            + requests.EVIDENCE_PREFIX
            + json.dumps(plan["planned_slots"][1]["model_input"]["evidence"], ensure_ascii=False)
        )
        self.assertEqual(packet["payload"]["messages"], [
            {"role": "system", "content": expected_system},
            {"role": "user", "content": plan["planned_slots"][1]["question"]},
        ])
        self.assertEqual(packet["payload"], lookup["payload"])
        self.assertEqual(packet["settings"], plan["planned_slots"][1]["settings"])
        self.assertEqual(packet["prompt_token_ids"], list(range(12)))
        self.assertEqual(packet["maximum_context_tokens"], 32)
        self.assertEqual(packet["worst_case_reservation_usd"], "0.0003")
        self.assertEqual(renderer.calls[0][1], 0.37)
        self.assertNotIn("Thinking effort level", json.dumps(renderer.calls))
        self.assertNotIn(CRITERIA_SENTINEL, json.dumps(record))

    def test_verification_regenerates_and_distinguishes_false_from_zero(self):
        plan = make_plan()
        renderer = FakeRenderer()
        record = prepare(plan, renderer)
        with patch.object(requests, "_load_renderer", return_value=FakeRenderer()):
            self.assertTrue(requests.verify_prepared_requests(
                plan, record,
                input_rate_usd_per_million=Decimal("2"),
                output_rate_usd_per_million=Decimal("5"),
                allowance_usd=Decimal("0.001"),
            ))
        changed = copy.deepcopy(record)
        changed["model_calls"] = False
        self.assertEqual(changed, record)  # Python considers False equal to numeric zero.
        with patch.object(requests, "_load_renderer", return_value=FakeRenderer()), \
             self.assertRaisesRegex(requests.EvidenceRequestError, "exact regeneration"):
            requests.verify_prepared_requests(
                plan, changed,
                input_rate_usd_per_million=Decimal("2"),
                output_rate_usd_per_million=Decimal("5"),
                allowance_usd=Decimal("0.001"),
            )

    def test_insufficient_allowance_and_non_decimal_prices_fail(self):
        plan = make_plan()
        with self.assertRaisesRegex(requests.EvidenceRequestError, "below the full-run"):
            prepare(plan, FakeRenderer(), allowance=Decimal("0.000899"))
        with patch.object(requests, "_load_renderer", return_value=FakeRenderer()):
            for value in (2, 2.0, "2", True, Decimal("NaN")):
                with self.subTest(value=value), self.assertRaises(requests.EvidenceRequestError):
                    requests.prepare_constructed_requests(
                        plan,
                        input_rate_usd_per_million=value,
                        output_rate_usd_per_million=Decimal("5"),
                        allowance_usd=Decimal("1"),
                    )

    def test_cost_totals_ignore_ambient_decimal_precision(self):
        plan = make_plan()
        with localcontext() as context:
            context.prec = 4
            record = prepare(plan, FakeRenderer())
        self.assertEqual(record["full_run_worst_case_reservation_usd"], "0.0009")
        self.assertEqual(
            record["full_run_exact_rendered_input_plus_output_cap_estimate_usd"],
            "0.000372",
        )

    def test_effort_one_bounds_and_overlong_exact_prompt_are_rejected(self):
        with self.assertRaisesRegex(requests.EvidenceRequestError, "below 1"):
            prepare(make_plan(effort=1), FakeRenderer())
        with self.assertRaisesRegex(requests.EvidenceRequestError, "declared input and output"):
            prepare(make_plan(input_limit=65_530, output_limit=10), FakeRenderer())
        with self.assertRaisesRegex(requests.EvidenceRequestError, "exact native input limit"):
            prepare(make_plan(input_limit=10), FakeRenderer(token_count=11))

    def test_plan_types_inventory_status_and_private_model_input_are_strict(self):
        base = make_plan()
        changes = []
        schema = copy.deepcopy(base)
        schema["schema_version"] = True
        changes.append((schema, "schema_version"))
        blocked = copy.deepcopy(base)
        blocked["engineering_readiness"]["status"] = "not_ready"
        changes.append((blocked, "blocked"))
        live = copy.deepcopy(base)
        live["execution_readiness"]["status"] = "ready"
        changes.append((live, "not_ready"))
        order = copy.deepcopy(base)
        order["planned_slots"][0], order["planned_slots"][1] = (
            order["planned_slots"][1], order["planned_slots"][0]
        )
        changes.append((order, "case_then_arm"))
        hidden = copy.deepcopy(base)
        hidden["planned_slots"][0]["model_input"]["expected_answer"] = CRITERIA_SENTINEL
        changes.append((hidden, "fields differ"))
        changed_evidence = copy.deepcopy(base)
        changed_evidence["planned_slots"][1]["evidence_content"] = "changed"
        changes.append((changed_evidence, "evidence differs"))
        changed_settings = copy.deepcopy(base)
        changed_settings["planned_slots"][2]["settings_sha256"] = "f" * 64
        changes.append((changed_settings, "bound full settings document"))
        changed_slot_id = copy.deepcopy(base)
        changed_slot_id["planned_slots"][0]["slot_id"] = "changed"
        changes.append((changed_slot_id, "deterministic planner slot ID"))
        nonboolean_control = copy.deepcopy(base)
        nonboolean_control["planned_slots"][0]["general_control"] = 0
        changes.append((nonboolean_control, "general_control must be boolean"))
        changed_question = copy.deepcopy(base)
        changed = changed_question["planned_slots"][1]
        changed["question"] = changed["model_input"]["question"] = "Changed within one arm"
        changed["question_sha256"] = canonical_sha256(changed["question"])
        changed["model_input_sha256"] = canonical_sha256(changed["model_input"])
        changes.append((changed_question, "differs within its case"))
        malformed_readiness = copy.deepcopy(base)
        malformed_readiness["engineering_readiness"] = []
        changes.append((malformed_readiness, "blocked"))
        malformed_bindings = copy.deepcopy(base)
        malformed_bindings["bindings"] = []
        changes.append((malformed_bindings, "bindings must be an object"))
        malformed_slot = copy.deepcopy(base)
        malformed_slot["planned_slots"][1] = None
        changes.append((malformed_slot, "must be an object"))
        for changed, message in changes:
            with self.subTest(message=message), self.assertRaisesRegex(
                requests.EvidenceRequestError, message
            ):
                prepare(changed, FakeRenderer())

    def test_missing_local_assets_fail_without_network_fallback(self):
        plan = make_plan()
        with patch.object(
            requests.comparison, "local_identity",
            side_effect=ValueError("constructed missing asset"),
        ), patch.object(socket.socket, "connect", side_effect=AssertionError("network")) as connect:
            with self.assertRaisesRegex(requests.EvidenceRequestError, "local Inkling"):
                requests.prepare_constructed_requests(
                    plan,
                    input_rate_usd_per_million=Decimal("2"),
                    output_rate_usd_per_million=Decimal("5"),
                    allowance_usd=Decimal("1"),
                )
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
