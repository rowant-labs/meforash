"""Constructed offline tests for the evidence coordinator."""
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bibleprep import evidence_coordinator as coordinator
from bibleprep import evidence_requests as requests
from bibleprep.evidence import PLAN, sha256, strict_load
from bibleprep.evidence_collection import canonical_sha256
from bibleprep.evidence_delivery import rights_fact_sha256
from bibleprep.evidence_eligibility import build_projection, seed_pending_registry
from tests.test_evidence_delivery import record_fixture
from tests.test_evidence_native import diagnostic
from tests.test_evidence_requests import FakeRenderer


PRIVATE = "PRIVATE_EXPECTED_ANSWER_SENTINEL"


class EvidenceCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        for path in (
            "manifests", "data/evidence/drafts/v1", "data/evidence/reviews",
            "data/evidence/delivery", "data/raw", "licenses",
        ):
            (self.root / path).mkdir(parents=True, exist_ok=True)
        project_root = Path(__file__).resolve().parents[1]
        schema = strict_load(project_root / PLAN)["record_schema"]
        (self.root / PLAN).write_text(json.dumps({"record_schema": schema}), encoding="utf-8")

        self.source = self.root / "data/raw/source-one.txt"
        self.source.write_text("Ἀρχή ⸀λόγου. \n", encoding="utf-8")
        self.license = self.root / "licenses/fixture-license.txt"
        self.license.write_text("Constructed rights notice.\n", encoding="utf-8")
        self.record = record_fixture(sha256(self.source), sha256(self.license))
        self.record_path = self.root / "data/evidence/drafts/v1/SYNTHETIC01.json"
        self.record_path.write_text(
            json.dumps(self.record, ensure_ascii=False) + "\n", encoding="utf-8",
        )
        self.review_path = self.root / "data/evidence/reviews/review.txt"
        self.review_path.write_text("Constructed AI review.\n", encoding="utf-8")
        self.manifest_path = self.root / "data/evidence/delivery/notice-manifest.json"
        self.manifest = self.make_manifest()
        self.write_manifest()

        self.registry = seed_pending_registry(self.root, self.directory, "fixture-registry-v1")
        self.registry["status"] = "reviewed"
        for component in self.registry["records"][0]["components"]:
            component["scholarly_review"] = self.decision(scholarly=True)
            component["uses"]["app_display"] = self.decision(include_manifest=True)
        self.projection = build_projection(
            self.registry, "app_display", self.root, self.directory,
        )
        self.cases = self.make_cases()
        self.settings = {
            "schema_version": 1,
            "settings_id": "coordinator-settings-v1",
            "checkpoint_id": "logical-retained-B",
            "system_prompt": "Answer from supplied evidence when present.",
            "sampling": {
                "effort": 0.37, "temperature": 0, "seed": 7, "max_tokens": 10,
                "input_token_limit": 200, "deadline_seconds": 30,
            },
            "request_order": "case_then_arm",
            "stop_rule": "stop_after_uncertain_or_incomplete",
        }
        self.policy = {
            "schema_version": 1,
            "policy_id": "coordinator-policy-v1",
            "kind": "deterministic_exact_component_key_fixture",
            "mappings": [
                {"lookup_key": "hit", "component_keys": ["SYNTHETIC01/reading-R1"]},
                {"lookup_key": "miss", "component_keys": []},
            ],
        }

    def tearDown(self):
        self.temporary.cleanup()

    @property
    def directory(self):
        return self.root / "data/evidence/drafts/v1"

    def decision(self, *, scholarly=False, include_manifest=False):
        evidence = [{
            "evidence_id": "review-1", "path": "data/evidence/reviews/review.txt",
            "content_sha256": sha256(self.review_path),
        }]
        if include_manifest:
            evidence.append({
                "evidence_id": "delivery-notice-manifest",
                "path": "data/evidence/delivery/notice-manifest.json",
                "content_sha256": sha256(self.manifest_path),
            })
        result = {
            "decision": "approved", "reviewer_kind": "ai",
            "reviewer_role": "AI development source reviewer", "reviewed_on": "2026-09-08",
            "rationale": "Constructed approval.", "limitations": ["Fixture only."],
            "supporting_review_evidence": evidence,
        }
        if scholarly:
            result["expert_certification"] = False
        return result

    def make_manifest(self):
        applies = ["SYNTHETIC01/claim-Q1", "SYNTHETIC01/reading-R1"]
        notices = []
        for right in self.record["rights_by_component"]:
            notices.append({
                "notice_id": "notice-" + right["component"], "record_id": "SYNTHETIC01",
                "source_id": "source-one", "rights_component": right["component"],
                "rights_fact_sha256": rights_fact_sha256(right),
                "rights_snapshot_path": "licenses/fixture-license.txt",
                "applies_to_component_keys": copy.deepcopy(applies),
                "license_notice": "Fixture license notice with attribution.",
                "disclaimer": "No warranty or endorsement.",
            })
        return {
            "schema_version": 1, "notice_manifest_id": "fixture-notices-v1",
            "notices": notices,
            "limitations": ["Training hold metadata must not enter model input."],
        }

    def write_manifest(self):
        self.manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )

    def make_cases(self):
        def private():
            return {
                "expected_answer": PRIVATE,
                "scoring_criteria": ["Constructed criterion."],
                "reviewer_instructions": [], "provenance": ["Constructed fixture."],
            }
        return {
            "schema_version": 1, "suite_id": "coordinator-suite-v1",
            "fixture_kind": "constructed",
            "cases": [
                {
                    "case_id": "evidence-hit", "question": "What does the source show?",
                    "category": "constructed", "general_control": False,
                    "packet_component_keys": ["SYNTHETIC01/claim-Q1"],
                    "lookup_key": "hit", "private": private(),
                },
                {
                    "case_id": "lookup-miss", "question": "What if lookup misses?",
                    "category": "constructed", "general_control": False,
                    "packet_component_keys": ["SYNTHETIC01/claim-Q1"],
                    "lookup_key": "miss", "private": private(),
                },
                {
                    "case_id": "general-control", "question": "Write a short greeting.",
                    "category": "control", "general_control": True,
                    "packet_component_keys": [], "lookup_key": None, "private": private(),
                },
            ],
        }

    def kwargs(self, **changes):
        result = {
            "root": self.root, "cases": self.cases, "settings": self.settings,
            "policy": self.policy, "registry": self.registry,
            "saved_projection": self.projection, "notice_manifest": self.manifest,
            "record_directory": self.directory,
            "input_rate_usd_per_million": Decimal("1"),
            "output_rate_usd_per_million": Decimal("2"),
            "allowance_usd": Decimal("1"),
        }
        result.update(changes)
        return result

    def prepare(self, *, token_count=7, **changes):
        with patch.object(requests, "_load_renderer", return_value=FakeRenderer(token_count)):
            return coordinator.prepare_mock_coordination(**self.kwargs(**changes))

    def fixture(self, prepared, index, *, finish="stop", partial="", failure=None):
        request = prepared["prepared_requests"]["prepared_requests"][index]
        slot = prepared["coordinated_plan"]["planned_slots"][index]
        if failure is not None:
            payload = {"disposition": failure}
            outcome = "failure"
        else:
            payload = diagnostic(
                final="Constructed final." if finish == "stop" else "Closed part.",
                partial=partial, finish=finish,
            )
            payload["prompt_token_ids_sha256"] = request["prompt_token_ids_sha256"]
            payload["prompt_token_count"] = request["exact_input_tokens"]
            outcome = "diagnostic"
        return {
            "schema_version": 1, "fixture_kind": "constructed_native_outcome_v1",
            "slot_id": slot["slot_id"], "model_input_sha256": slot["model_input_sha256"],
            "outcome_kind": outcome, "payload": payload,
            "payload_sha256": canonical_sha256(payload),
        }

    def simulate(self, prepared, fixtures, **changes):
        with patch.object(requests, "_load_renderer", return_value=FakeRenderer(7)):
            return coordinator.simulate_mock_collection(prepared, fixtures, **self.kwargs(**changes))

    def test_notice_plan_preserves_empty_arms_and_exact_native_requests(self):
        prepared = self.prepare()
        plan = prepared["coordinated_plan"]
        self.assertEqual(plan["planned_slot_count"], 9)
        self.assertEqual(plan["execution_readiness"]["open_requirements"],
                         coordinator.CURRENT_OPEN_REQUIREMENTS)
        self.assertNotIn("human_verification", json.dumps(plan["execution_readiness"]))
        slots = plan["planned_slots"]
        for index in (0, 3, 5, 6, 7, 8):
            self.assertEqual(slots[index]["model_input"]["evidence"], "")
            self.assertIsNone(slots[index]["delivery_provenance"])
        self.assertEqual(slots[5]["retrieval_status"], "exact_fixture_miss")
        for index in (1, 2, 4):
            evidence = slots[index]["model_input"]["evidence"]
            self.assertIn("SUPPLIED_EVIDENCE_DATA", evidence)
            self.assertIn("Fixture license notice with attribution", evidence)
            self.assertNotIn(PRIVATE, evidence)
            self.assertNotIn("Training hold metadata", evidence)
            self.assertEqual(slots[index]["model_input_sha256"],
                             canonical_sha256(slots[index]["model_input"]))
            self.assertEqual(slots[index]["evidence_content_sha256"],
                             hashlib.sha256(evidence.encode()).hexdigest())
        request = prepared["prepared_requests"]["prepared_requests"][1]
        self.assertIn("SUPPLIED_EVIDENCE_DATA", request["payload"]["messages"][0]["content"])
        self.assertEqual(request["prompt_token_ids"], list(range(7)))
        self.assertEqual(request["exact_input_tokens"], 7)
        for name in ("coordinator_module_sha256", "delivery_module_sha256",
                     "collection_accounting_module_sha256", "native_diagnostics_module_sha256"):
            self.assertRegex(plan["bindings"][name], r"^[0-9a-f]{64}$")

    def test_complete_partial_and_uncertain_cost_inventory(self):
        prepared = self.prepare()
        complete_fixtures = [self.fixture(prepared, index) for index in range(9)]
        complete = self.simulate(prepared, complete_fixtures)
        self.assertEqual(complete["native_simulation"]["audit"]["totals"]["complete"], 9)
        self.assertEqual(complete["cost_accounting"]["submitted_maximum_reservation_usd"],
                         "0.00198")
        self.assertEqual(complete["cost_accounting"]["released_unsubmitted_reservation_usd"], "0")
        self.assertTrue(all(row["attempt_count"] == 1 for row in complete["cost_accounting"]["slots"]))
        self.assertFalse(complete["cost_accounting"]["invoice_cost_claimed"])

        partial_fixtures = [
            self.fixture(prepared, 0),
            self.fixture(prepared, 1, finish="length", partial="Visible tail."),
        ]
        partial = self.simulate(prepared, partial_fixtures)
        self.assertEqual(partial["native_simulation"]["audit"]["totals"]["partial"], 1)
        self.assertEqual(partial["native_simulation"]["audit"]["totals"]["unsubmitted"], 7)
        self.assertEqual(partial["cost_accounting"]["submitted_maximum_reservation_usd"],
                         "0.00044")
        self.assertEqual(partial["cost_accounting"]["released_unsubmitted_reservation_usd"],
                         "0.00154")

        uncertain = self.simulate(prepared, [self.fixture(prepared, 0, failure="uncertain")])
        self.assertEqual(uncertain["native_simulation"]["audit"]["totals"]["uncertain"], 1)
        self.assertEqual(uncertain["native_simulation"]["audit"]["totals"]["unsubmitted"], 8)
        self.assertEqual(uncertain["cost_accounting"]["submitted_maximum_reservation_usd"],
                         "0.00022")
        self.assertEqual(uncertain["cost_accounting"]["released_unsubmitted_reservation_usd"],
                         "0.00176")

    def test_current_approval_notice_and_source_are_rebuilt_before_simulation(self):
        prepared = self.prepare()
        fixtures = [self.fixture(prepared, index) for index in range(9)]
        stale_registry = copy.deepcopy(self.registry)
        component = stale_registry["records"][0]["components"][0]
        component["uses"]["app_display"] = {
            "decision": "pending", "reviewer_kind": None, "reviewer_role": None,
            "reviewed_on": None, "rationale": "Withdrawn.", "limitations": [],
            "supporting_review_evidence": [],
        }
        stale_projection = build_projection(stale_registry, "app_display", self.root, self.directory)
        with self.assertRaises(coordinator.EvidenceCoordinatorError):
            self.simulate(prepared, fixtures, registry=stale_registry,
                          saved_projection=stale_projection)

        changed_manifest = copy.deepcopy(self.manifest)
        changed_manifest["notices"][0]["license_notice"] = "Changed unreviewed notice."
        with self.assertRaises(coordinator.EvidenceCoordinatorError):
            self.simulate(prepared, fixtures, notice_manifest=changed_manifest)

        self.source.write_text("Changed source bytes.\n", encoding="utf-8")
        with self.assertRaises(coordinator.EvidenceCoordinatorError):
            self.simulate(prepared, fixtures)

    def test_fixture_prompt_hash_count_and_output_cap_are_required(self):
        prepared = self.prepare()
        valid = self.fixture(prepared, 0)
        wrong_hash = copy.deepcopy(valid)
        wrong_hash["payload"]["prompt_token_ids_sha256"] = "f" * 64
        wrong_hash["payload_sha256"] = canonical_sha256(wrong_hash["payload"])
        with self.assertRaisesRegex(coordinator.EvidenceCoordinatorError, "prompt hash"):
            self.simulate(prepared, [wrong_hash])
        wrong_count = copy.deepcopy(valid)
        wrong_count["payload"]["prompt_token_count"] = 8
        wrong_count["payload_sha256"] = canonical_sha256(wrong_count["payload"])
        with self.assertRaisesRegex(coordinator.EvidenceCoordinatorError, "prompt count"):
            self.simulate(prepared, [wrong_count])
        too_long = copy.deepcopy(valid)
        too_long["payload"]["raw_generated_token_ids"] = list(range(11))
        too_long["payload"]["raw_generated_token_ids_sha256"] = requests.native_diagnostics.token_ids_sha256(
            list(range(11))
        )
        too_long["payload"]["generated_token_count"] = 11
        too_long["payload"]["parsed_token_count"] = 11
        too_long["payload_sha256"] = canonical_sha256(too_long["payload"])
        with self.assertRaisesRegex(coordinator.EvidenceCoordinatorError, "maximum output"):
            self.simulate(prepared, [too_long])

    def test_prepared_and_simulation_tampering_fail_exact_regeneration(self):
        prepared = self.prepare()
        changed = copy.deepcopy(prepared)
        changed["coordinated_plan"]["planned_slots"][1]["model_input"]["evidence"] += "changed"
        with self.assertRaisesRegex(coordinator.EvidenceCoordinatorError, "exact regeneration"):
            self.simulate(changed, [])
        fixtures = [self.fixture(prepared, index) for index in range(9)]
        result = self.simulate(prepared, fixtures)
        with patch.object(requests, "_load_renderer", return_value=FakeRenderer(7)):
            self.assertEqual(coordinator.verify_mock_collection(
                prepared, fixtures, result,
                **self.kwargs(),
            )["audit"]["totals"]["planned"], 9)
        tampered = copy.deepcopy(result)
        tampered["cost_accounting"]["invoice_reconciled"] = 0
        with patch.object(requests, "_load_renderer", return_value=FakeRenderer(7)), \
             self.assertRaisesRegex(coordinator.EvidenceCoordinatorError, "exact regeneration"):
            coordinator.verify_mock_collection(prepared, fixtures, tampered, **self.kwargs())

    def test_exact_input_cap_and_allowance_fail_before_fixtures(self):
        with self.assertRaises(coordinator.EvidenceCoordinatorError):
            self.prepare(token_count=201)
        with self.assertRaises(coordinator.EvidenceCoordinatorError):
            self.prepare(allowance_usd=Decimal("0.001"))


if __name__ == "__main__":
    unittest.main()
