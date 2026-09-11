"""Constructed tests for the offline evidence blinded-review workflow."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bibleprep.evidence_collection import canonical_sha256
from bibleprep.evidence_blinded_review import (
    BlindedReviewError,
    build_review_artifacts,
    integrate_frozen_review,
    validate_and_freeze_review,
    write_review_artifacts,
)
import bibleprep.evidence_blinded_review as blinded


ARMS = ("B-memory", "B-packet", "B-lookup")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class EvidenceBlindedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "runs").mkdir(mode=0o700)
        self.slots = []
        for case_id, question in (
            ("case-text", "What does the constructed text mean?"),
            ("case-general", "Return the constructed general result."),
        ):
            for arm in ARMS:
                self.slots.append({
                    "slot_id": f"{case_id}::{arm}",
                    "case_id": case_id,
                    "arm": arm,
                    "question": question,
                    "category": "general" if case_id == "case-general" else "greek",
                    "general_control": case_id == "case-general",
                })
        self.criteria = {
            "schema_version": 1,
            "suite_id": "constructed-review-suite-v1",
            "fixture_kind": "constructed",
            "cases": [
                {
                    "case_id": "case-text",
                    "question": "What does the constructed text mean?",
                    "general_control": False,
                    "scoring_criteria": ["Preserve the constructed qualification."],
                    "reviewer_instructions": ["Treat alternate clear wording as acceptable."],
                },
                {
                    "case_id": "case-general",
                    "question": "Return the constructed general result.",
                    "general_control": True,
                    "scoring_criteria": ["The general result is semantically correct."],
                    "reviewer_instructions": [],
                },
            ],
        }
        self.journal = []
        for index, slot in enumerate(self.slots):
            # Deliberately repeat wording to prove candidates are not deduplicated.
            answer = "Identical constructed final.\n" if index < 3 else f"General final {index}."
            self.journal.extend([
                {"event": "submission", "slot_id": slot["slot_id"]},
                {
                    "event": "result",
                    "slot_id": slot["slot_id"],
                    "stop_reason": "stop",
                    "final_text": answer,
                    "receipt_sha256": digest("receipt-" + str(index)),
                },
            ])
        self.seed = bytes(range(32))

    def tearDown(self):
        self.temporary.cleanup()

    def artifacts(self, journal=None):
        return build_review_artifacts(
            self.slots, self.journal if journal is None else journal,
            self.criteria, seed=self.seed,
        )

    def review(self, packet):
        return {
            "schema_version": 1,
            "artifact_kind": "frozen_blinded_review",
            "review_id": "synthetic-ai-review-v1",
            "packet_sha256": canonical_sha256(packet),
            "reviewer_kind": "ai",
            "reviewer_role": "Synthetic engineering fixture reviewer",
            "conflicts": ["Constructed by the same engineering test author."],
            "expert_certified": False,
            "assessments": [
                {
                    "candidate_id": row["candidate_id"],
                    "answer_sha256": row["answer_sha256"],
                    "receipt_sha256": row["receipt_sha256"],
                    "critical_errors": [],
                    "requested_content_omissions": [],
                    "general_semantic_pass": True if row["general_control"] else None,
                    "rationale": "Synthetic structured assessment only.",
                }
                for row in packet["candidates"]
            ],
            "limitations": ["No real semantic judgment or expertise is represented."],
        }

    def write_and_freeze(self, packet, label_map, review=None, name="review-run"):
        receipt = write_review_artifacts(packet, label_map, self.root / "runs" / name, self.root)
        review = review or self.review(packet)
        frozen = self.root / "runs" / name / "frozen-review.json"
        frozen_receipt = validate_and_freeze_review(packet, review, frozen, self.root)
        return (
            frozen, self.root / receipt["label_map_path"],
            frozen_receipt["review_file_sha256"], receipt["label_map_file_sha256"],
        )

    def test_packet_masks_plan_identity_and_preserves_every_exact_answer(self):
        packet, label_map = self.artifacts()
        self.assertEqual(len(packet["candidates"]), 6)
        self.assertEqual(packet["paired_preference"], "not_implemented")
        self.assertEqual(len({row["candidate_id"] for row in packet["candidates"]}), 6)
        self.assertEqual(
            sum(row["answer_text"] == "Identical constructed final.\n" for row in packet["candidates"]),
            3,
        )
        serialized = json.dumps(packet, ensure_ascii=False)
        for slot in self.slots:
            self.assertNotIn(slot["slot_id"], serialized)
            self.assertNotIn(slot["arm"], serialized)
        self.assertNotIn("mapping_seed_hex", serialized)
        self.assertNotIn("private_blinded_review_label_map", serialized)
        self.assertEqual(label_map["packet_sha256"], canonical_sha256(packet))
        self.assertEqual(len(label_map["mapping_seed_hex"]), 64)

    def test_secret_mapping_is_repeatable_only_with_same_explicit_seed(self):
        first, first_map = self.artifacts()
        second, second_map = self.artifacts()
        self.assertEqual(first, second)
        self.assertEqual(first_map, second_map)
        random_one, _ = build_review_artifacts(self.slots, self.journal, self.criteria)
        random_two, _ = build_review_artifacts(self.slots, self.journal, self.criteria)
        self.assertNotEqual(
            {row["candidate_id"] for row in random_one["candidates"]},
            {row["candidate_id"] for row in random_two["candidates"]},
        )

    def test_partial_final_is_kept_and_later_unsubmitted_slots_stay_in_denominator(self):
        first, second = self.slots[:2]
        journal = [
            {"event": "submission", "slot_id": first["slot_id"]},
            {"event": "result", "slot_id": first["slot_id"], "stop_reason": "stop",
             "final_text": "Complete.", "receipt_sha256": digest("complete")},
            {"event": "submission", "slot_id": second["slot_id"]},
            {"event": "result", "slot_id": second["slot_id"], "stop_reason": "output_limit",
             "final_text": "Exact partial final.\n", "receipt_sha256": digest("partial")},
        ]
        packet, label_map = self.artifacts(journal)
        partial = next(row for row in packet["candidates"] if row["answer_status"] == "partial")
        self.assertEqual(partial["answer_text"], "Exact partial final.\n")
        frozen, map_path, frozen_sha, map_sha = self.write_and_freeze(
            packet, label_map, name="partial"
        )
        result = integrate_frozen_review(
            self.slots, journal, packet, frozen, map_path,
            expected_frozen_review_file_sha256=frozen_sha, root=self.root,
            expected_label_map_file_sha256=map_sha,
        )
        self.assertEqual(result["totals"]["planned"], 6)
        self.assertEqual(result["totals"]["reviewed"], 2)
        self.assertEqual(result["totals"]["partial"], 1)
        self.assertEqual(result["totals"]["unsubmitted"], 4)
        self.assertEqual(result["decision"], "not_assessed_or_authorized")

    def test_criteria_must_be_constructed_and_exactly_match_every_planned_case(self):
        bad = copy.deepcopy(self.criteria)
        bad["fixture_kind"] = "real"
        with self.assertRaisesRegex(BlindedReviewError, "Only constructed"):
            build_review_artifacts(self.slots, self.journal, bad, seed=self.seed)
        bad = copy.deepcopy(self.criteria)
        bad["cases"][0]["question"] += " changed"
        with self.assertRaisesRegex(BlindedReviewError, "does not match"):
            build_review_artifacts(self.slots, self.journal, bad, seed=self.seed)
        bad = copy.deepcopy(self.criteria)
        bad["cases"].pop()
        with self.assertRaisesRegex(BlindedReviewError, "exactly cover"):
            build_review_artifacts(self.slots, self.journal, bad, seed=self.seed)
        bad = copy.deepcopy(self.criteria)
        bad["cases"][1]["general_control"] = False
        with self.assertRaisesRegex(BlindedReviewError, "metadata does not match"):
            build_review_artifacts(self.slots, self.journal, bad, seed=self.seed)
        bad = copy.deepcopy(self.criteria)
        bad["schema_version"] = True
        with self.assertRaisesRegex(BlindedReviewError, "schema_version"):
            build_review_artifacts(self.slots, self.journal, bad, seed=self.seed)

    def test_review_requires_exact_coverage_hashes_and_semantic_field_types(self):
        packet, _ = self.artifacts()
        review = self.review(packet)
        review["assessments"].pop()
        with self.assertRaisesRegex(BlindedReviewError, "exactly cover"):
            validate_and_freeze_review(packet, review, self.root / "runs/missing.json", self.root)
        review = self.review(packet)
        review["assessments"][0]["answer_sha256"] = "0" * 64
        with self.assertRaisesRegex(BlindedReviewError, "does not match packet"):
            validate_and_freeze_review(packet, review, self.root / "runs/hash.json", self.root)
        review = self.review(packet)
        general_id = next(row["candidate_id"] for row in packet["candidates"] if row["general_control"])
        next(row for row in review["assessments"] if row["candidate_id"] == general_id)[
            "general_semantic_pass"
        ] = None
        with self.assertRaisesRegex(BlindedReviewError, "must be boolean"):
            validate_and_freeze_review(packet, review, self.root / "runs/general.json", self.root)
        invalid_packet = copy.deepcopy(packet)
        invalid_packet["schema_version"] = True
        with self.assertRaisesRegex(BlindedReviewError, "Unsupported review packet"):
            validate_and_freeze_review(
                invalid_packet, self.review(invalid_packet), self.root / "runs/schema.json", self.root
            )
        review = self.review(packet)
        review["schema_version"] = True
        with self.assertRaisesRegex(BlindedReviewError, "Unsupported review artifact"):
            validate_and_freeze_review(packet, review, self.root / "runs/review-schema.json", self.root)

    def test_packet_criteria_document_is_hash_bound_and_controls_candidate_rows(self):
        packet, _ = self.artifacts()
        changed = copy.deepcopy(packet)
        changed["criteria"]["cases"][0]["scoring_criteria"][0] = "Altered criterion."
        with self.assertRaisesRegex(BlindedReviewError, "criteria document hash"):
            validate_and_freeze_review(
                changed, self.review(changed), self.root / "runs/criteria-hash.json", self.root
            )
        changed["criteria_document_sha256"] = canonical_sha256(changed["criteria"])
        with self.assertRaisesRegex(BlindedReviewError, "bound criteria document"):
            validate_and_freeze_review(
                changed, self.review(changed), self.root / "runs/criteria-row.json", self.root
            )

    def test_freeze_and_packet_writes_are_private_exclusive_and_confined(self):
        packet, label_map = self.artifacts()
        frozen, _, _, _ = self.write_and_freeze(packet, label_map)
        self.assertEqual(os.stat(frozen.parent).st_mode & 0o777, 0o700)
        for path in frozen.parent.iterdir():
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            validate_and_freeze_review(packet, self.review(packet), frozen, self.root)
        with self.assertRaises(ValueError):
            validate_and_freeze_review(
                packet, self.review(packet), self.root / "outside.json", self.root
            )
        target = self.root / "runs/real"
        target.mkdir()
        (self.root / "runs/link").symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            validate_and_freeze_review(
                packet, self.review(packet), self.root / "runs/link/review.json", self.root
            )

    def test_invalid_frozen_review_fails_before_label_map_is_opened(self):
        packet, label_map = self.artifacts()
        receipt = write_review_artifacts(packet, label_map, self.root / "runs/order", self.root)
        invalid_path = self.root / "runs/order/invalid-review.json"
        invalid = self.review(packet)
        invalid["assessments"].pop()
        invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
        labels = []
        original = blinded._load_private_json

        def observed(path, root, label):
            labels.append(label)
            return original(path, root, label)

        with patch.object(blinded, "_load_private_json", side_effect=observed):
            with self.assertRaisesRegex(BlindedReviewError, "exactly cover"):
                integrate_frozen_review(
                    self.slots, self.journal, packet, invalid_path,
                    self.root / receipt["label_map_path"],
                    expected_frozen_review_file_sha256=digest(
                        invalid_path.read_text(encoding="utf-8")
                    ),
                    root=self.root,
                )
        self.assertEqual(labels, ["frozen review"])

    def test_post_freeze_valid_edit_is_rejected_by_receipt_before_any_json_load(self):
        packet, label_map = self.artifacts()
        frozen, map_path, frozen_sha, _ = self.write_and_freeze(
            packet, label_map, name="tampered-freeze"
        )
        changed = json.loads(frozen.read_text(encoding="utf-8"))
        changed["assessments"][0]["rationale"] = "A different but still valid rationale."
        frozen.write_text(json.dumps(changed), encoding="utf-8")
        labels = []
        original = blinded._load_private_json

        def observed(path, root, label):
            labels.append(label)
            return original(path, root, label)

        with patch.object(blinded, "_load_private_json", side_effect=observed):
            with self.assertRaisesRegex(BlindedReviewError, "freeze receipt"):
                integrate_frozen_review(
                    self.slots, self.journal, packet, frozen, map_path,
                    expected_frozen_review_file_sha256=frozen_sha, root=self.root,
                )
        self.assertEqual(labels, [])

    def test_integration_verifies_map_and_reports_explicit_arm_denominators(self):
        packet, label_map = self.artifacts()
        review = self.review(packet)
        text_candidate = next(row for row in packet["candidates"] if not row["general_control"])
        judgment = next(
            row for row in review["assessments"]
            if row["candidate_id"] == text_candidate["candidate_id"]
        )
        judgment["critical_errors"] = ["Synthetic critical error."]
        judgment["requested_content_omissions"] = ["Synthetic omission."]
        general_candidate = next(row for row in packet["candidates"] if row["general_control"])
        next(
            row for row in review["assessments"]
            if row["candidate_id"] == general_candidate["candidate_id"]
        )["general_semantic_pass"] = False
        frozen, map_path, frozen_sha, map_sha = self.write_and_freeze(
            packet, label_map, review, "integrate"
        )
        result = integrate_frozen_review(
            self.slots, self.journal, packet, frozen, map_path,
            expected_frozen_review_file_sha256=frozen_sha, root=self.root,
            expected_label_map_file_sha256=map_sha,
        )
        self.assertEqual(result["totals"]["planned"], 6)
        self.assertEqual(result["totals"]["reviewed"], 6)
        self.assertEqual(result["totals"]["critical_error_answers"], 1)
        self.assertEqual(result["totals"]["requested_content_omission_answers"], 1)
        self.assertEqual(set(result["arms"]), set(ARMS))
        self.assertTrue(all(values["planned"] == 2 for values in result["arms"].values()))
        self.assertEqual(sum(row["general_semantic_fail"] for row in result["arms"].values()), 1)
        self.assertFalse(result["expert_certified"])

    def test_integration_recomputes_audit_and_rejects_forged_label_binding(self):
        packet, label_map = self.artifacts()
        receipt = write_review_artifacts(packet, label_map, self.root / "runs/forged", self.root)
        frozen = self.root / "runs/forged/frozen-review.json"
        frozen_receipt = validate_and_freeze_review(packet, self.review(packet), frozen, self.root)
        map_path = self.root / receipt["label_map_path"]
        changed = json.loads(map_path.read_text(encoding="utf-8"))
        changed["planned_slots_sha256"] = "f" * 64
        forged_path = self.root / "runs/forged/forged-map.json"
        forged_path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(BlindedReviewError, "inventory hash"):
            integrate_frozen_review(
                self.slots, self.journal, packet, frozen, forged_path,
                expected_frozen_review_file_sha256=frozen_receipt["review_file_sha256"],
                root=self.root,
            )

    def test_private_seed_is_verified_against_candidate_identity_and_order(self):
        packet, label_map = self.artifacts()
        receipt = write_review_artifacts(packet, label_map, self.root / "runs/seed", self.root)
        frozen = self.root / "runs/seed/frozen-review.json"
        frozen_receipt = validate_and_freeze_review(
            packet, self.review(packet), frozen, self.root
        )
        changed = copy.deepcopy(label_map)
        changed["mapping_seed_hex"] = "ab" * 32
        changed_path = self.root / "runs/seed/changed-seed.json"
        changed_path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(BlindedReviewError, "candidate ID"):
            integrate_frozen_review(
                self.slots, self.journal, packet, frozen, changed_path,
                expected_frozen_review_file_sha256=frozen_receipt["review_file_sha256"],
                root=self.root,
            )


if __name__ == "__main__":
    unittest.main()
