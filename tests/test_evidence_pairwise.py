"""Constructed tests for offline paired preferences and collection gating."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bibleprep.evidence_collection import canonical_sha256
from bibleprep.evidence_pairwise import (
    PairwiseReviewError,
    build_pair_artifacts,
    freeze_collection_gate,
    integrate_frozen_pair_review,
    validate_and_freeze_pair_review,
    write_pair_artifacts,
)
import bibleprep.evidence_blinded_review as blinded


ARMS = ("B-memory", "B-packet", "B-lookup")


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EvidencePairwiseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "runs").mkdir(mode=0o700)
        self.slots = []
        for case_id, question, general in (
            ("bible-case", "What is the constructed reading?", False),
            ("general-case", "Return the constructed value.", True),
        ):
            for arm in ARMS:
                self.slots.append({
                    "slot_id": case_id + "::" + arm,
                    "case_id": case_id,
                    "arm": arm,
                    "question": question,
                    "general_control": general,
                })
        self.criteria = {
            "schema_version": 1,
            "suite_id": "constructed-pair-suite-v1",
            "fixture_kind": "constructed",
            "cases": [
                {
                    "case_id": "bible-case",
                    "question": "What is the constructed reading?",
                    "general_control": False,
                    "scoring_criteria": ["Preserve the constructed qualification."],
                    "reviewer_instructions": [],
                },
                {
                    "case_id": "general-case",
                    "question": "Return the constructed value.",
                    "general_control": True,
                    "scoring_criteria": ["Return a semantically valid constructed value."],
                    "reviewer_instructions": [],
                },
            ],
        }
        self.gate = {
            "schema_version": 1,
            "artifact_kind": "constructed_collection_gate",
            "gate_id": "constructed-full-collection-v1",
            "fixture_kind": "constructed",
            "planned_slots_sha256": canonical_sha256(self.slots),
            "minimum_complete_slots_by_arm": {arm: 2 for arm in ARMS},
            "minimum_matched_complete_bible_pairs_by_contrast": {
                "packet_vs_memory": 1,
                "lookup_vs_packet": 1,
            },
            "limitations": ["Constructed collection sufficiency only."],
        }
        self.journal = []
        for index, slot in enumerate(self.slots):
            # Repeated wording ensures pair identities do not depend on unique text.
            answer = "Same constructed final." if index < 3 else f"General result {index}."
            self.journal.extend([
                {"event": "submission", "slot_id": slot["slot_id"]},
                {"event": "result", "slot_id": slot["slot_id"], "stop_reason": "stop",
                 "final_text": answer, "receipt_sha256": digest("receipt-" + str(index))},
            ])
        self.seed = bytes(range(32))

    def tearDown(self):
        self.temporary.cleanup()

    def freeze_gate(self, gate=None, name="gate.json"):
        path = self.root / "runs" / name
        receipt = freeze_collection_gate(
            self.slots, self.criteria, gate or self.gate, path, self.root
        )
        return path, receipt["gate_file_sha256"]

    def artifacts(self, journal=None, name="gate.json"):
        gate_path, gate_sha = self.freeze_gate(name=name)
        packet, pair_map = build_pair_artifacts(
            self.slots, self.journal if journal is None else journal, self.criteria,
            gate_path, expected_gate_file_sha256=gate_sha, seed=self.seed, root=self.root,
        )
        return gate_path, gate_sha, packet, pair_map

    def review(self, packet, preference="left"):
        return {
            "schema_version": 1,
            "artifact_kind": "frozen_constructed_pair_review",
            "review_id": "constructed-ai-pair-review-v1",
            "packet_sha256": canonical_sha256(packet),
            "reviewer_kind": "ai",
            "reviewer_role": "Synthetic pair fixture reviewer",
            "conflicts": ["Shared engineering fixture context."],
            "expert_certified": False,
            "assessments": [
                {
                    "pair_id": pair["pair_id"],
                    "left_answer_sha256": pair["left"]["answer_sha256"],
                    "left_receipt_sha256": pair["left"]["receipt_sha256"],
                    "right_answer_sha256": pair["right"]["answer_sha256"],
                    "right_receipt_sha256": pair["right"]["receipt_sha256"],
                    "preference": preference,
                    "rationale": "Constructed pair preference only.",
                }
                for pair in packet["reviewable_pairs"]
            ],
            "limitations": ["No real semantic judgment or expert review."],
        }

    def write_freeze(self, packet, pair_map, review=None, name="pair-run"):
        write_receipt = write_pair_artifacts(
            packet, pair_map, self.root / "runs" / name, self.root
        )
        review_path = self.root / "runs" / name / "frozen-pair-review.json"
        freeze_receipt = validate_and_freeze_pair_review(
            packet, review or self.review(packet), review_path, self.root
        )
        return (
            review_path, self.root / write_receipt["pair_map_path"],
            freeze_receipt["review_file_sha256"], write_receipt["pair_map_file_sha256"],
        )

    def integrate(self, journal, gate_path, gate_sha, packet, pair_map, name="pair-run"):
        review_path, map_path, review_sha, map_sha = self.write_freeze(
            packet, pair_map, name=name
        )
        return integrate_frozen_pair_review(
            self.slots, journal, self.criteria, packet, gate_path, review_path, map_path,
            expected_gate_file_sha256=gate_sha,
            expected_review_file_sha256=review_sha,
            expected_pair_map_file_sha256=map_sha,
            root=self.root,
        )

    def test_packet_has_every_case_contrast_but_no_arm_or_slot_labels(self):
        _, _, packet, pair_map = self.artifacts()
        self.assertEqual(len(packet["planned_pairs"]), 4)
        self.assertEqual(len(packet["reviewable_pairs"]), 4)
        serialized = json.dumps(packet, ensure_ascii=False)
        for slot in self.slots:
            self.assertNotIn(slot["slot_id"], serialized)
            self.assertNotIn(slot["arm"], serialized)
        self.assertNotIn("packet_vs_memory", serialized)
        self.assertNotIn("lookup_vs_packet", serialized)
        self.assertNotIn("mapping_seed_hex", serialized)
        self.assertEqual(pair_map["packet_sha256"], canonical_sha256(packet))
        self.assertEqual(len({row["pair_id"] for row in packet["planned_pairs"]}), 4)

    def test_secret_controls_repeatable_pair_ids_order_and_left_right(self):
        gate_path, gate_sha = self.freeze_gate(name="stable-gate.json")
        first, first_map = build_pair_artifacts(
            self.slots, self.journal, self.criteria, gate_path,
            expected_gate_file_sha256=gate_sha, seed=self.seed, root=self.root,
        )
        second, second_map = build_pair_artifacts(
            self.slots, self.journal, self.criteria, gate_path,
            expected_gate_file_sha256=gate_sha, seed=self.seed, root=self.root,
        )
        self.assertEqual((first, first_map), (second, second_map))
        random_packet, _ = build_pair_artifacts(
            self.slots, self.journal, self.criteria, gate_path,
            expected_gate_file_sha256=gate_sha, root=self.root,
        )
        self.assertNotEqual(first["packet_id"], random_packet["packet_id"])

    def test_gate_is_strict_bound_and_nonvacuous_then_frozen_private(self):
        gate_path, gate_sha = self.freeze_gate()
        self.assertEqual(os.stat(gate_path).st_mode & 0o777, 0o600)
        self.assertEqual(len(gate_sha), 64)
        with self.assertRaises(FileExistsError):
            freeze_collection_gate(self.slots, self.criteria, self.gate, gate_path, self.root)
        bad = copy.deepcopy(self.gate)
        bad["planned_slots_sha256"] = "f" * 64
        with self.assertRaisesRegex(PairwiseReviewError, "exact planned inventory"):
            self.freeze_gate(bad, "bad-binding.json")
        bad = copy.deepcopy(self.gate)
        bad["minimum_matched_complete_bible_pairs_by_contrast"]["packet_vs_memory"] = 0
        with self.assertRaisesRegex(PairwiseReviewError, "Invalid matched-complete"):
            self.freeze_gate(bad, "vacuous.json")
        bad = copy.deepcopy(self.gate)
        bad["minimum_complete_slots_by_arm"]["B-memory"] = True
        with self.assertRaisesRegex(PairwiseReviewError, "Invalid complete threshold"):
            self.freeze_gate(bad, "bool.json")

    def test_complete_collection_reports_bible_preferences_and_separate_controls(self):
        gate_path, gate_sha, packet, pair_map = self.artifacts(name="complete-gate.json")
        result = self.integrate(
            self.journal, gate_path, gate_sha, packet, pair_map, "complete"
        )
        self.assertEqual(result["collection_gate_status"], "collection_sufficient")
        self.assertTrue(all(row["complete"] == row["planned"] == 2
                            for row in result["arm_collection"].values()))
        for contrast in result["contrasts"].values():
            self.assertEqual(contrast["planned_bible_pairs"], 1)
            self.assertEqual(contrast["all_reviewable_bible_pairs"]["denominator"], 1)
            self.assertEqual(contrast["matched_complete_bible_pairs"]["denominator"], 1)
            self.assertEqual(contrast["general_controls"], {
                "planned": 1, "reviewable": 1, "matched_complete": 1, "unavailable": 0,
            })
        self.assertEqual(result["model_promotion"], "not_assessed_or_performed")
        self.assertFalse(result["expert_certified"])

    def test_partial_pair_is_judged_only_in_all_reviewable_denominator(self):
        first, second = self.slots[:2]
        journal = [
            {"event": "submission", "slot_id": first["slot_id"]},
            {"event": "result", "slot_id": first["slot_id"], "stop_reason": "stop",
             "final_text": "Complete final.", "receipt_sha256": digest("complete")},
            {"event": "submission", "slot_id": second["slot_id"]},
            {"event": "result", "slot_id": second["slot_id"], "stop_reason": "output_limit",
             "final_text": "Exact partial final.\n", "receipt_sha256": digest("partial")},
        ]
        gate_path, gate_sha, packet, pair_map = self.artifacts(journal, "partial-gate.json")
        self.assertEqual(len(packet["reviewable_pairs"]), 1)
        pair = packet["reviewable_pairs"][0]
        self.assertFalse(pair["matched_complete"])
        self.assertIn("Exact partial final.\n", {
            pair["left"]["answer_text"], pair["right"]["answer_text"]
        })
        result = self.integrate(journal, gate_path, gate_sha, packet, pair_map, "partial")
        packet_contrast = result["contrasts"]["packet_vs_memory"]
        self.assertEqual(packet_contrast["all_reviewable_bible_pairs"]["denominator"], 1)
        self.assertEqual(packet_contrast["matched_complete_bible_pairs"]["denominator"], 0)
        self.assertEqual(result["contrasts"]["lookup_vs_packet"]["unavailable_bible_pairs"], 1)
        self.assertEqual(result["collection_gate_status"], "inconclusive")

    def test_zero_reviewable_pairs_freeze_and_integrate_as_unavailable(self):
        journal = [
            {"event": "submission", "slot_id": self.slots[0]["slot_id"]},
            {"event": "failure", "slot_id": self.slots[0]["slot_id"],
             "disposition": "uncertain", "receipt_sha256": None},
        ]
        gate_path, gate_sha, packet, pair_map = self.artifacts(journal, "zero-gate.json")
        self.assertEqual(packet["reviewable_pairs"], [])
        self.assertTrue(all(row["availability"] == "unavailable"
                            for row in packet["planned_pairs"]))
        result = self.integrate(journal, gate_path, gate_sha, packet, pair_map, "zero")
        self.assertEqual(result["collection_gate_status"], "inconclusive")
        self.assertTrue(all(
            row["all_reviewable_bible_pairs"]["denominator"] == 0
            for row in result["contrasts"].values()
        ))

    def test_pair_review_requires_exact_coverage_and_answer_receipt_hashes(self):
        _, _, packet, _ = self.artifacts()
        review = self.review(packet)
        review["assessments"].pop()
        with self.assertRaisesRegex(PairwiseReviewError, "exactly cover"):
            validate_and_freeze_pair_review(
                packet, review, self.root / "runs/missing-review.json", self.root
            )
        review = self.review(packet)
        review["assessments"][0]["left_receipt_sha256"] = "0" * 64
        with self.assertRaisesRegex(PairwiseReviewError, "does not match packet"):
            validate_and_freeze_pair_review(
                packet, review, self.root / "runs/forged-review.json", self.root
            )
        review = self.review(packet)
        review["expert_certified"] = True
        with self.assertRaisesRegex(PairwiseReviewError, "cannot record expert"):
            validate_and_freeze_pair_review(
                packet, review, self.root / "runs/expert-review.json", self.root
            )

    def test_invalid_or_edited_freeze_fails_before_pair_map_read(self):
        gate_path, gate_sha, packet, pair_map = self.artifacts(name="order-gate.json")
        review_path, map_path, review_sha, _ = self.write_freeze(
            packet, pair_map, name="order"
        )
        changed = json.loads(review_path.read_text(encoding="utf-8"))
        changed["assessments"][0]["rationale"] = "Valid-looking post-freeze edit."
        review_path.write_text(json.dumps(changed), encoding="utf-8")
        labels = []
        original = blinded._load_private_json

        def observed(path, root, label):
            labels.append(label)
            return original(path, root, label)

        with patch.object(blinded, "_load_private_json", side_effect=observed):
            with self.assertRaisesRegex(PairwiseReviewError, "freeze receipt"):
                integrate_frozen_pair_review(
                    self.slots, self.journal, self.criteria, packet, gate_path,
                    review_path, map_path, expected_gate_file_sha256=gate_sha,
                    expected_review_file_sha256=review_sha, root=self.root,
                )
        self.assertEqual(labels, ["gate"])

    def test_private_map_seed_and_exact_contrast_bindings_are_verified(self):
        gate_path, gate_sha, packet, pair_map = self.artifacts(name="map-gate.json")
        review_path, _, review_sha, _ = self.write_freeze(packet, pair_map, name="map")
        changed = copy.deepcopy(pair_map)
        changed["mapping_seed_hex"] = "ab" * 32
        changed_path = self.root / "runs/map/changed-map.json"
        changed_path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(PairwiseReviewError, "secret deterministic mapping"):
            integrate_frozen_pair_review(
                self.slots, self.journal, self.criteria, packet, gate_path,
                review_path, changed_path, expected_gate_file_sha256=gate_sha,
                expected_review_file_sha256=review_sha, root=self.root,
            )

    def test_orientation_swap_with_rehashed_review_is_closed_by_secret_map(self):
        gate_path, gate_sha, packet, pair_map = self.artifacts(name="orient-gate.json")
        changed = copy.deepcopy(packet)
        changed["reviewable_pairs"][0]["left"], changed["reviewable_pairs"][0]["right"] = (
            changed["reviewable_pairs"][0]["right"], changed["reviewable_pairs"][0]["left"]
        )
        review_path = self.root / "runs/orient-review.json"
        review_receipt = validate_and_freeze_pair_review(
            changed, self.review(changed), review_path, self.root
        )
        changed_map = copy.deepcopy(pair_map)
        changed_map["packet_sha256"] = canonical_sha256(changed)
        map_path = self.root / "runs/orient-map.json"
        map_path.write_text(json.dumps(changed_map), encoding="utf-8")
        with self.assertRaisesRegex(PairwiseReviewError, "secret deterministic mapping"):
            integrate_frozen_pair_review(
                self.slots, self.journal, self.criteria, changed, gate_path,
                review_path, map_path, expected_gate_file_sha256=gate_sha,
                expected_review_file_sha256=review_receipt["review_file_sha256"],
                root=self.root,
            )

    def test_cross_case_answer_swap_is_rejected_before_unmasking(self):
        gate_path, gate_sha, packet, pair_map = self.artifacts(name="cross-gate.json")
        changed = copy.deepcopy(packet)
        first = changed["reviewable_pairs"][0]
        second = next(
            row for row in changed["reviewable_pairs"] if row["case_id"] != first["case_id"]
        )
        first["left"], second["left"] = second["left"], first["left"]
        review_path = self.root / "runs/cross-review.json"
        review_receipt = validate_and_freeze_pair_review(
            changed, self.review(changed), review_path, self.root
        )
        map_path = self.root / "runs/cross-map.json"
        map_path.write_text(json.dumps(pair_map), encoding="utf-8")
        labels = []
        original = blinded._load_private_json

        def observed(path, root, label):
            labels.append(label)
            return original(path, root, label)

        with patch.object(blinded, "_load_private_json", side_effect=observed):
            with self.assertRaisesRegex(PairwiseReviewError, "answers do not match"):
                integrate_frozen_pair_review(
                    self.slots, self.journal, self.criteria, changed, gate_path,
                    review_path, map_path, expected_gate_file_sha256=gate_sha,
                    expected_review_file_sha256=review_receipt["review_file_sha256"],
                    root=self.root,
                )
        self.assertEqual(labels, ["gate"])

    def test_private_writes_reject_escape_symlink_and_overwrite(self):
        _, _, packet, pair_map = self.artifacts(name="safe-gate.json")
        receipt = write_pair_artifacts(packet, pair_map, self.root / "runs/safe", self.root)
        for name in ("packet_path", "pair_map_path"):
            self.assertEqual(os.stat(self.root / receipt[name]).st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            write_pair_artifacts(packet, pair_map, self.root / "runs/safe", self.root)
        with self.assertRaises(ValueError):
            write_pair_artifacts(packet, pair_map, self.root / "outside", self.root)
        target = self.root / "runs/real"
        target.mkdir()
        (self.root / "runs/link").symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            write_pair_artifacts(packet, pair_map, self.root / "runs/link/new", self.root)


if __name__ == "__main__":
    unittest.main()
