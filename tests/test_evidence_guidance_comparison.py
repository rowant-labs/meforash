"""Constructed tests for the offline two-condition guidance input preparer."""
import copy
import hashlib
import unittest

from bibleprep.evidence_answer_context import EVIDENCE_GUIDANCE
from bibleprep.evidence_delivery import render_model_input
from bibleprep.evidence_guidance_comparison import (
    CONDITION_IDS,
    EvidenceGuidanceComparisonError,
    prepare_comparison_pair,
    verify_comparison_pair,
)
from tests import test_evidence_answer_context as answer_context_tests


class EvidenceGuidanceComparisonTests(unittest.TestCase):
    def setUp(self):
        self.fixture = answer_context_tests.EvidenceAnswerContextTests(
            "test_exact_three_field_shape_and_existing_evidence_are_preserved"
        )
        self.fixture.setUp()
        self.inputs = {
            "case_id": "comparison-case-1",
            "system_prompt": "Trusted base policy.",
            "question": "What does the supplied record say?",
            "selected_component_keys": [
                "SYNTHETIC01/reading-R1",
                "SYNTHETIC01/claim-Q1",
            ],
            "verified": self.fixture.verified,
            "registry": self.fixture.registry,
            "notice_manifest": self.fixture.manifest,
            "root": self.fixture.root,
            "record_directory": self.fixture.directory,
        }

    def tearDown(self):
        self.fixture.tearDown()

    def test_pair_preserves_question_and_evidence_with_only_guidance_difference(self):
        before = copy.deepcopy((
            self.inputs["verified"],
            self.inputs["registry"],
            self.inputs["notice_manifest"],
        ))
        first = prepare_comparison_pair(**self.inputs)
        second = prepare_comparison_pair(**self.inputs)
        original = first["conditions"]["B-original"]["model_input"]
        guided = first["conditions"]["B-guided"]["model_input"]
        expected_evidence = render_model_input(
            self.fixture.verified,
            self.fixture.registry,
            self.fixture.manifest,
            root=self.fixture.root,
            record_directory=self.fixture.directory,
        )

        self.assertEqual(first, second)
        self.assertEqual(tuple(first["condition_order"]), CONDITION_IDS)
        self.assertEqual(first["selected_component_keys"], [
            "SYNTHETIC01/claim-Q1", "SYNTHETIC01/reading-R1",
        ])
        self.assertEqual(original["question"].encode(), guided["question"].encode())
        self.assertEqual(original["evidence"].encode(), guided["evidence"].encode())
        self.assertEqual(original["evidence"], expected_evidence)
        self.assertEqual(guided["system_prompt"], original["system_prompt"] + "\n\n" + EVIDENCE_GUIDANCE)
        self.assertNotIn(EVIDENCE_GUIDANCE, original["system_prompt"])
        self.assertEqual(
            first["pair_bindings"]["evidence_text_sha256"],
            hashlib.sha256(expected_evidence.encode()).hexdigest(),
        )
        self.assertEqual(first["authorization"], {
            "artifact_frozen": False,
            "generation_authorized": False,
            "training_authorized": False,
        })
        self.assertEqual((first["model_calls"], first["network_requests"]), (0, 0))
        self.assertEqual((
            self.inputs["verified"],
            self.inputs["registry"],
            self.inputs["notice_manifest"],
        ), before)
        self.assertEqual(verify_comparison_pair(first, **self.inputs), first)

    def test_general_control_keeps_empty_evidence_and_applies_guidance(self):
        inputs = {
            **self.inputs,
            "case_id": "general-control-1",
            "question": "Write a short greeting.",
            "selected_component_keys": [],
            "verified": None,
            "general_control": True,
        }
        prepared = prepare_comparison_pair(**inputs)
        original = prepared["conditions"]["B-original"]["model_input"]
        guided = prepared["conditions"]["B-guided"]["model_input"]

        self.assertEqual(original["evidence"], "")
        self.assertEqual(guided["evidence"], "")
        self.assertEqual(original["question"], guided["question"])
        self.assertEqual(guided["system_prompt"], original["system_prompt"] + "\n\n" + EVIDENCE_GUIDANCE)
        self.assertIsNone(prepared["pair_bindings"]["verified_candidate_sha256"])
        self.assertIsNone(prepared["pair_bindings"]["verified_registry_sha256"])
        self.assertEqual(verify_comparison_pair(prepared, **inputs), prepared)

    def test_rejects_guidance_already_present_in_evidence_base_prompt(self):
        kwargs = dict(self.inputs)
        kwargs["system_prompt"] += "\n\n" + EVIDENCE_GUIDANCE
        with self.assertRaisesRegex(
            EvidenceGuidanceComparisonError, "already contains"
        ):
            prepare_comparison_pair(**kwargs)

    def test_rejects_guidance_already_present_in_control_base_prompt(self):
        kwargs = dict(self.inputs)
        kwargs.update(
            system_prompt=kwargs["system_prompt"] + "\n\n" + EVIDENCE_GUIDANCE,
            selected_component_keys=[],
            verified=None,
            general_control=True,
        )
        with self.assertRaisesRegex(
            EvidenceGuidanceComparisonError, "already contains"
        ):
            prepare_comparison_pair(**kwargs)

    def test_current_source_review_use_and_notices_are_reverified(self):
        prepare_comparison_pair(**self.inputs)

        stale_registry = copy.deepcopy(self.fixture.registry)
        stale_registry["records"][0]["components"][0]["uses"]["app_display"] = {
            "decision": "pending", "reviewer_kind": None, "reviewer_role": None,
            "reviewed_on": None, "rationale": "Pending again.", "limitations": [],
            "supporting_review_evidence": [],
        }
        with self.assertRaisesRegex(EvidenceGuidanceComparisonError, "verification failed"):
            prepare_comparison_pair(**{**self.inputs, "registry": stale_registry})

        changed_manifest = copy.deepcopy(self.fixture.manifest)
        changed_manifest["notices"][0]["license_notice"] = "Changed notice."
        with self.assertRaisesRegex(EvidenceGuidanceComparisonError, "verification failed"):
            prepare_comparison_pair(**{**self.inputs, "notice_manifest": changed_manifest})

        self.fixture.source.write_text("Tampered source bytes.\n", encoding="utf-8")
        with self.assertRaisesRegex(EvidenceGuidanceComparisonError, "verification failed"):
            prepare_comparison_pair(**self.inputs)

    def test_invalid_selection_input_mismatch_and_prepared_tamper_are_rejected(self):
        for selected in (
            ["SYNTHETIC01/claim-Q1", "SYNTHETIC01/claim-Q1"],
            ["not-a-component-key"],
            ["SYNTHETIC01/claim-Q1"],
            [],
        ):
            with self.subTest(selected=selected), self.assertRaises(EvidenceGuidanceComparisonError):
                prepare_comparison_pair(**{
                    **self.inputs,
                    "selected_component_keys": selected,
                })

        with self.assertRaises(EvidenceGuidanceComparisonError):
            prepare_comparison_pair(**{
                **self.inputs,
                "general_control": True,
                "selected_component_keys": ["SYNTHETIC01/claim-Q1"],
                "verified": None,
            })

        prepared = prepare_comparison_pair(**self.inputs)
        tampered = copy.deepcopy(prepared)
        tampered["conditions"]["B-guided"]["model_input"]["question"] = "Changed"
        with self.assertRaisesRegex(
            EvidenceGuidanceComparisonError, "deterministic regeneration"
        ):
            verify_comparison_pair(tampered, **self.inputs)


if __name__ == "__main__":
    unittest.main()
