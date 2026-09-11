"""Constructed tests for the offline evidence comparison planner."""
import copy
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bibleprep.evidence import PLAN, sha256, strict_load
from bibleprep.evidence_eligibility import build_projection, seed_pending_registry
from bibleprep.evaluate_evidence import (
    ARMS,
    build_offline_plan,
    main,
    render_markdown,
    write_plan,
)
from tests.test_evidence_eligibility import record_fixture


class OfflineEvidencePlannerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "manifests").mkdir()
        (self.root / "data/evidence/drafts/v1").mkdir(parents=True)
        (self.root / "data/evidence/reviews").mkdir(parents=True)
        (self.root / "data/raw").mkdir(parents=True)
        project_root = Path(__file__).resolve().parents[1]
        plan = strict_load(project_root / PLAN)
        (self.root / PLAN).write_text(
            json.dumps({"record_schema": plan["record_schema"]}), encoding="utf-8"
        )
        self.source_one = self.root / "data/raw/source-one.txt"
        self.source_two = self.root / "data/raw/source-two.txt"
        self.source_one.write_text("constructed source one\n", encoding="utf-8")
        self.source_two.write_text("constructed source two\n", encoding="utf-8")
        self.record = record_fixture(sha256(self.source_one), sha256(self.source_two))
        self.record_path = self.root / "data/evidence/drafts/v1/SYNTHETIC01.json"
        self.record_path.write_text(json.dumps(self.record, indent=2) + "\n", encoding="utf-8")
        self.review_path = self.root / "data/evidence/reviews/synthetic-review.txt"
        self.review_path.write_text("Synthetic review evidence.\n", encoding="utf-8")
        self.registry = seed_pending_registry(
            self.root, self.record_path.parent, "synthetic-eligibility-v1"
        )
        self._approve("claim-Q1", "app_display")
        self.projection = build_projection(
            self.registry, "app_display", self.root, self.record_path.parent
        )
        self.cases = {
            "schema_version": 1,
            "suite_id": "constructed-suite-v1",
            "fixture_kind": "constructed",
            "cases": [self._case()],
        }
        self.settings = {
            "schema_version": 1,
            "settings_id": "constructed-settings-v1",
            "checkpoint_id": "logical-retained-B",
            "system_prompt": "Answer the constructed question using supplied evidence when present.",
            "sampling": {
                "effort": 0.7,
                "temperature": 0,
                "seed": 20260908,
                "max_tokens": 256,
                "input_token_limit": 2048,
                "deadline_seconds": 30,
            },
            "request_order": "case_then_arm",
            "stop_rule": "stop_after_uncertain_or_incomplete",
        }
        self.policy = {
            "schema_version": 1,
            "policy_id": "exact-fixture-policy-v1",
            "kind": "deterministic_exact_component_key_fixture",
            "mappings": [{"lookup_key": "miss", "component_keys": []}],
        }

    def tearDown(self):
        self.temporary.cleanup()

    def _approve(self, component_id, use):
        self.registry["status"] = "reviewed"
        component = next(
            item for item in self.registry["records"][0]["components"]
            if item["component_id"] == component_id
        )
        evidence = [{
            "evidence_id": "review-1",
            "path": "data/evidence/reviews/synthetic-review.txt",
            "content_sha256": sha256(self.review_path),
        }]
        component["scholarly_review"] = {
            "decision": "approved",
            "reviewer_kind": "human",
            "reviewer_role": "Qualified synthetic reviewer",
            "reviewed_on": "2026-09-08",
            "rationale": "Synthetic approval for a constructed test.",
            "limitations": ["Not a real source review."],
            "supporting_review_evidence": copy.deepcopy(evidence),
            "expert_certification": True,
        }
        component["uses"][use] = {
            "decision": "approved",
            "reviewer_kind": "human",
            "reviewer_role": "Synthetic rights reviewer",
            "reviewed_on": "2026-09-08",
            "rationale": "Synthetic model-input permission for a constructed test.",
            "limitations": ["Not a real permission decision."],
            "supporting_review_evidence": copy.deepcopy(evidence),
        }

    def _case(self, *, case_id="case-one", general=False, packet=None, lookup="miss"):
        return {
            "case_id": case_id,
            "question": "What does the constructed evidence say?",
            "category": "greek",
            "general_control": general,
            "packet_component_keys": [] if general else (packet or ["SYNTHETIC01/claim-Q1"]),
            "lookup_key": None if general else lookup,
            "private": {
                "expected_answer": "PRIVATE_EXPECTED_SENTINEL",
                "scoring_criteria": ["PRIVATE_SCORE_SENTINEL"],
                "reviewer_instructions": ["PRIVATE_REVIEWER_SENTINEL"],
                "provenance": ["PRIVATE_PROVENANCE_SENTINEL"],
            },
        }

    def build(self, **changes):
        values = {
            "root": self.root,
            "cases": self.cases,
            "settings": self.settings,
            "policy": self.policy,
            "registry": self.registry,
            "saved_projection": self.projection,
            "record_directory": self.record_path.parent,
        }
        values.update(changes)
        return build_offline_plan(**values)

    def test_ready_plan_has_exact_three_arms_and_sanitized_distinct_inputs(self):
        plan = self.build()
        self.assertEqual(plan["engineering_readiness"]["status"], "ready")
        self.assertEqual(plan["execution_readiness"]["status"], "not_ready")
        self.assertEqual(plan["planned_slot_count"], 3)
        self.assertEqual([slot["arm"] for slot in plan["planned_slots"]], list(ARMS))
        self.assertEqual({slot["question"] for slot in plan["planned_slots"]}, {
            "What does the constructed evidence say?"
        })
        self.assertEqual(len({slot["settings_sha256"] for slot in plan["planned_slots"]}), 1)
        memory, packet, lookup = plan["planned_slots"]
        self.assertEqual(memory["evidence_content"], "")
        self.assertIn("A constructed disputed claim", packet["evidence_content"])
        self.assertIn("A constructed alternative", packet["evidence_content"])
        self.assertIn("Contrary fixture", packet["evidence_content"])
        self.assertEqual(lookup["evidence_content"], "")
        self.assertEqual(lookup["retrieval_status"], "exact_fixture_miss")
        self.assertEqual(lookup["status"], "planned_offline")
        self.assertNotEqual(packet["model_input_sha256"], lookup["model_input_sha256"])
        serialized_inputs = json.dumps([slot["model_input"] for slot in plan["planned_slots"]])
        for sentinel in ("PRIVATE_EXPECTED", "PRIVATE_SCORE", "PRIVATE_REVIEWER", "PRIVATE_PROVENANCE"):
            self.assertNotIn(sentinel, serialized_inputs)
        for forbidden in (
            "reviewer_role", "scholarly_review", "use_decision", "snapshot_path",
            "content_sha256", "record_unresolved_issues", "component_key",
        ):
            self.assertNotIn(forbidden, packet["evidence_content"])
        self.assertTrue(packet["evidence_provenance"])
        self.assertIn("component_sha256", packet["evidence_provenance"][0])
        self.assertEqual(plan["model_calls"], 0)
        self.assertEqual(plan["network_requests"], 0)

    def test_empty_projection_reports_not_ready_and_retains_blocked_slots(self):
        pending = seed_pending_registry(
            self.root, self.record_path.parent, "empty-synthetic-eligibility-v1"
        )
        empty = build_projection(pending, "app_display", self.root, self.record_path.parent)
        plan = self.build(registry=pending, saved_projection=empty)
        self.assertEqual(plan["engineering_readiness"]["status"], "not_ready")
        self.assertIn(
            "eligible_app_display_projection_is_empty", plan["engineering_readiness"]["reasons"]
        )
        self.assertEqual(len(plan["planned_slots"]), 3)
        self.assertTrue(all(
            slot["status"] == "blocked_evidence_not_ready" for slot in plan["planned_slots"]
        ))
        self.assertTrue(all(slot["evidence_content"] == "" for slot in plan["planned_slots"]))

    def test_training_approval_does_not_substitute_for_model_input_use(self):
        registry = copy.deepcopy(self.registry)
        component = next(
            item for item in registry["records"][0]["components"]
            if item["component_id"] == "claim-Q1"
        )
        component["uses"]["training"] = copy.deepcopy(component["uses"]["app_display"])
        component["uses"]["app_display"] = {
            "decision": "pending",
            "reviewer_kind": None,
            "reviewer_role": None,
            "reviewed_on": None,
            "rationale": "Model-input use remains pending.",
            "limitations": ["No model-input use decision."],
            "supporting_review_evidence": [],
        }
        empty = build_projection(registry, "app_display", self.root, self.record_path.parent)
        plan = self.build(registry=registry, saved_projection=empty)
        self.assertEqual(empty["component_count"], 0)
        self.assertEqual(plan["engineering_readiness"]["status"], "not_ready")
        self.assertTrue(all(
            slot["status"] == "blocked_evidence_not_ready" for slot in plan["planned_slots"]
        ))

    def test_missing_packet_component_blocks_whole_case_but_empty_lookup_does_not(self):
        self.cases["cases"].append(self._case(
            case_id="case-missing", packet=["SYNTHETIC01/claim-unavailable"]
        ))
        plan = self.build()
        by_case = {}
        for slot in plan["planned_slots"]:
            by_case.setdefault(slot["case_id"], []).append(slot)
        self.assertTrue(all(slot["status"] == "planned_offline" for slot in by_case["case-one"]))
        self.assertEqual(by_case["case-one"][2]["retrieval_status"], "exact_fixture_miss")
        self.assertTrue(all(
            slot["status"] == "blocked_evidence_not_ready" for slot in by_case["case-missing"]
        ))
        self.assertTrue(any(
            "packet_components_unavailable" in reason
            for reason in plan["engineering_readiness"]["reasons"]
        ))

    def test_general_control_is_three_explicit_repeat_controls_even_with_no_evidence(self):
        self.cases["cases"] = [self._case(case_id="general-one", general=True)]
        ready = self.build()
        self.assertEqual(
            [slot["status"] for slot in ready["planned_slots"]],
            ["repeat_control_planned"] * 3,
        )
        self.assertTrue(all(slot["evidence_content"] == "" for slot in ready["planned_slots"]))
        pending = seed_pending_registry(
            self.root, self.record_path.parent, "empty-general-eligibility-v1"
        )
        empty = build_projection(pending, "app_display", self.root, self.record_path.parent)
        blocked = self.build(registry=pending, saved_projection=empty)
        self.assertEqual(blocked["engineering_readiness"]["status"], "not_ready")
        self.assertTrue(all(
            slot["status"] == "blocked_evidence_not_ready" for slot in blocked["planned_slots"]
        ))

    def test_stale_projection_registry_and_source_dependencies_fail_closed(self):
        changed = copy.deepcopy(self.projection)
        changed["limitations"].append("altered")
        with self.assertRaisesRegex(ValueError, "Saved app_display projection is stale"):
            self.build(saved_projection=changed)
        changed_registry = copy.deepcopy(self.registry)
        changed_registry["limitations"].append("altered registry")
        with self.assertRaisesRegex(ValueError, "Saved app_display projection is stale"):
            self.build(registry=changed_registry)
        self.source_one.write_text("changed source bytes\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source snapshot hash mismatch"):
            self.build()

    def test_strict_ids_duplicate_keys_types_and_policy_are_rejected(self):
        duplicate = copy.deepcopy(self.cases)
        duplicate["cases"].append(copy.deepcopy(duplicate["cases"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate case_id"):
            self.build(cases=duplicate)
        extra = copy.deepcopy(self.settings)
        extra["execute"] = True
        with self.assertRaisesRegex(ValueError, r"extra=\['execute'\]"):
            self.build(settings=extra)
        nonfinite = copy.deepcopy(self.settings)
        nonfinite["sampling"]["temperature"] = math.inf
        with self.assertRaisesRegex(ValueError, "finite number"):
            self.build(settings=nonfinite)
        policy = copy.deepcopy(self.policy)
        policy["kind"] = "production_retriever"
        with self.assertRaisesRegex(ValueError, "exact component-key fixture policy"):
            self.build(policy=policy)
        missing_mapping = copy.deepcopy(self.policy)
        missing_mapping["mappings"] = []
        with self.assertRaisesRegex(ValueError, "No exact fixture lookup mapping"):
            self.build(policy=missing_mapping)

    def test_case_and_arm_order_are_stable_and_bindings_are_deterministic(self):
        self.cases["cases"].append(self._case(case_id="case-two"))
        first = self.build()
        second = self.build()
        self.assertEqual(first, second)
        self.assertEqual(
            [(slot["case_id"], slot["arm"]) for slot in first["planned_slots"]],
            [(case_id, arm) for case_id in ("case-one", "case-two") for arm in ARMS],
        )
        self.assertEqual(
            first["bindings"]["saved_projection_content_sha256"],
            first["bindings"]["rebuilt_projection_content_sha256"],
        )
        self.assertRegex(first["bindings"]["module_sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(first["bindings"]["evidence_module_sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(first["bindings"]["eligibility_module_sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(first["bindings"]["record_schema_plan_sha256"], sha256(self.root / PLAN))

    def test_json_type_changes_and_boolean_schema_versions_are_rejected(self):
        changed = copy.deepcopy(self.projection)
        changed["record_count"] = True
        with self.assertRaisesRegex(ValueError, "Saved app_display projection is stale"):
            self.build(saved_projection=changed)
        for name, value in (
            ("cases", copy.deepcopy(self.cases)),
            ("settings", copy.deepcopy(self.settings)),
            ("policy", copy.deepcopy(self.policy)),
            ("registry", copy.deepcopy(self.registry)),
            ("saved_projection", copy.deepcopy(self.projection)),
        ):
            with self.subTest(name=name):
                value["schema_version"] = True
                with self.assertRaisesRegex(ValueError, "schema_version"):
                    self.build(**{name: value})

    def test_cli_binds_projection_file_and_writes_offline_plan(self):
        input_directory = self.root / "runs/inputs"
        input_directory.mkdir(parents=True)
        values = {
            "cases": self.cases,
            "settings": self.settings,
            "policy": self.policy,
            "registry": self.registry,
            "projection": self.projection,
        }
        for name, value in values.items():
            (input_directory / f"{name}.json").write_text(
                json.dumps(value, allow_nan=False), encoding="utf-8"
            )
        argv = []
        for name in ("cases", "settings", "policy", "registry", "projection"):
            argv.extend([f"--{name}", f"runs/inputs/{name}.json"])
        argv.extend(["--directory", "data/evidence/drafts/v1", "--out", "runs/cli-plan"])
        output = io.StringIO()
        with patch("bibleprep.evaluate_evidence.ROOT", self.root), redirect_stdout(output):
            self.assertEqual(main(argv), 0)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["status"], "offline_plan_written")
        plan = strict_load(self.root / "runs/cli-plan/plan.json")
        self.assertEqual(
            set(plan["bindings"]["input_file_sha256"]),
            {"cases", "settings", "policy", "registry", "projection"},
        )
        self.assertEqual(plan["bindings"]["input_file_sha256"]["projection"],
                         sha256(input_directory / "projection.json"))

    def test_private_writer_rejects_escape_symlink_and_overwrite(self):
        plan = self.build()
        with self.assertRaises(ValueError):
            write_plan(plan, self.root.parent / "outside", self.root)
        receipt = write_plan(plan, self.root / "runs/evidence-plan", self.root)
        self.assertEqual(receipt["output_directory"], "runs/evidence-plan")
        self.assertEqual((self.root / "runs").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / "runs/evidence-plan").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / "runs/evidence-plan/plan.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "runs/evidence-plan/plan.md").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            write_plan(plan, self.root / "runs/evidence-plan", self.root)
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        self.addCleanup(lambda: outside.rmdir())
        (self.root / "runs-link").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            write_plan(plan, self.root / "runs-link/evidence-plan", self.root)
        markdown = render_markdown(plan)
        self.assertIn("Execution readiness: `not_ready`", markdown)
        self.assertNotIn("PRIVATE_EXPECTED_SENTINEL", markdown)


if __name__ == "__main__":
    unittest.main()
