"""Constructed tests for the pure two-condition guidance review layer."""
import copy
import hashlib
import json
import unittest

from bibleprep.guidance_review import (
    GuidanceReviewError,
    build_masked_packets,
    canonical_sha256,
    freeze_review,
    integrate_reviews,
)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GuidanceReviewTests(unittest.TestCase):
    def setUp(self):
        self.seed = bytes(range(32))
        self.slots = []
        for case_id, general in (("bible-one", False), ("bible-two", False),
                                 ("general-one", True)):
            question = "General instruction." if general else f"Question for {case_id}."
            for condition in ("B-original", "B-guided"):
                self.slots.append({
                    "slot_id": f"{case_id}::{condition}",
                    "case_id": case_id,
                    "condition_id": condition,
                    "general_control": general,
                    "question": question,
                    "extra_collection_field": "allowed",
                })
        self.results = []
        for index, slot in enumerate(self.slots):
            text = f"Constructed answer {index}."
            self.results.append({
                "slot_id": slot["slot_id"],
                "status": "complete",
                "final_text": text,
                "final_text_sha256": digest(text),
                "receipt_sha256": digest("receipt-" + str(index)),
                "extra_transport_field": index,
            })
        self.criteria = {}
        for case_id, general in (("bible-one", False), ("bible-two", False),
                                 ("general-one", True)):
            question = "General instruction." if general else f"Question for {case_id}."
            self.criteria[case_id] = {
                "question": question,
                "general_control": general,
                "expected_coverage": ["Answer the constructed request."],
                "factual_criteria": [] if general else [{
                    "criterion_id": "fact-one",
                    "statement": "Preserve the constructed source qualification.",
                    "source_refs": ["source:constructed"],
                }],
                "generic_evaluation_rules": [
                    "Review all material assertions and requested coverage."
                ],
            }
        self.expected = {
            "protocol_kind": "constructed_fixture",
            "planned_answers": 6,
            "bible_cases": 2,
            "general_control_cases": 1,
        }

    def packets(self, results=None):
        return build_masked_packets(
            self.slots, self.results if results is None else results,
            self.criteria, self.seed,
        )

    @staticmethod
    def issue(label="Constructed issue"):
        return {
            "finding": label,
            "reason": "Constructed reason.",
            "evidence_refs": ["criterion:fact-one"],
        }

    def individual_review(self, packet):
        return {
            "schema_version": 1,
            "artifact_kind": "frozen_guidance_individual_review_v1",
            "review_id": "constructed-individual-review",
            "packet_sha256": canonical_sha256(packet),
            "reviewer_kind": "ai",
            "reviewer_role": "Constructed fixture reviewer",
            "conflicts": ["Same-project test fixture."],
            "expert_certified": False,
            "assessments": [{
                "candidate_id": row["candidate_id"],
                "answer_sha256": row["answer_sha256"],
                "receipt_sha256": row["receipt_sha256"],
                "material_errors": [],
                "unsupported_or_unverified_assertions": [],
                "attribution_scope_errors": [],
                "omissions": [],
                "general_correctness": {
                    "correct": True,
                    "reason": "The constructed control is semantically correct.",
                    "evidence_refs": ["answer:text"],
                } if row["general_control"] else None,
                "rationale": "Constructed assessment only.",
            } for row in packet["candidates"]],
            "limitations": ["No real source or semantic judgment."],
        }

    def pair_review(self, packet, private_map):
        mapped = {row["pair_id"]: row for row in private_map["pairs"]}
        assessments = []
        first_bible = True
        for pair in packet["pairs"]:
            preference = "unavailable"
            if not pair["general_control"] and pair["pair_complete"]:
                if first_bible:
                    mapping = mapped[pair["pair_id"]]
                    preference = next(
                        side for side in ("left", "right")
                        if mapping[side]["condition_id"] == "B-guided"
                    )
                    first_bible = False
                else:
                    preference = "tie"
            assessments.append({
                "pair_id": pair["pair_id"],
                "left_answer_sha256": pair["left"]["answer_sha256"],
                "right_answer_sha256": pair["right"]["answer_sha256"],
                "preference": preference,
                "rationale": "Constructed pair judgment.",
                "evidence_refs": ["left", "right"],
            })
        return {
            "schema_version": 1,
            "artifact_kind": "frozen_guidance_pair_review_v1",
            "review_id": "constructed-pair-review",
            "packet_sha256": canonical_sha256(packet),
            "reviewer_kind": "ai",
            "reviewer_role": "Constructed fixture reviewer",
            "conflicts": ["Same-project test fixture."],
            "expert_certified": False,
            "assessments": assessments,
            "limitations": ["No real pair judgment."],
        }

    def integrate(self, results=None, mutate_individual=None, mutate_pair=None,
                  private_map_mutator=None, individual_hash=None, pair_hash=None):
        results = self.results if results is None else results
        individual, pairs, private_map = build_masked_packets(
            self.slots, results, self.criteria, self.seed
        )
        individual_review = self.individual_review(individual)
        pair_review = self.pair_review(pairs, private_map)
        if mutate_individual:
            mutate_individual(individual_review, individual, private_map)
        if mutate_pair:
            mutate_pair(pair_review, pairs, private_map)
        if private_map_mutator:
            private_map_mutator(private_map)
        return integrate_reviews(
            self.slots, results, self.criteria, individual, individual_review,
            pairs, pair_review, private_map, self.seed,
            individual_review_sha256=(
                canonical_sha256(individual_review) if individual_hash is None else individual_hash
            ),
            pair_review_sha256=(
                canonical_sha256(pair_review) if pair_hash is None else pair_hash
            ),
            expected_counts=self.expected,
        )

    def assessment(self, review, private_map, case_id, condition_id):
        candidate_id = next(
            row["candidate_id"] for row in private_map["candidates"]
            if row["case_id"] == case_id and row["condition_id"] == condition_id
        )
        return next(
            row for row in review["assessments"] if row["candidate_id"] == candidate_id
        )

    def test_complete_pair_masks_conditions_and_fixture_cannot_pass_gate(self):
        individual, pairs, private_map = self.packets()
        public = json.dumps([individual, pairs], ensure_ascii=False)
        for condition in ("B-original", "B-guided"):
            self.assertNotIn(condition, public)
        for slot in self.slots:
            self.assertNotIn(slot["slot_id"], public)
        self.assertNotIn(self.seed.hex(), public)
        self.assertEqual(len(individual["candidates"]), 6)
        self.assertEqual(len(pairs["pairs"]), 3)
        self.assertTrue(all(
            side["side_code"].startswith("side-")
            for pair in pairs["pairs"] for side in (pair["left"], pair["right"])
        ))
        result = self.integrate()
        self.assertFalse(result["promotion_gate"]["passed"])
        self.assertFalse(
            result["promotion_gate"]["thresholds"]["actual_protocol_counts_required"]
        )
        self.assertEqual(
            result["promotion_gate"]["recommendation"],
            "constructed_fixture_descriptive_only",
        )
        self.assertEqual(result["bible_pairs"]["preferences"], {
            "B-original": 0, "B-guided": 1, "tie": 1, "unavailable": 0,
        })
        with self.assertRaisesRegex(GuidanceReviewError, "declared expected counts"):
            individual_review = self.individual_review(individual)
            pair_review = self.pair_review(pairs, private_map)
            integrate_reviews(
                self.slots, self.results, self.criteria, individual, individual_review,
                pairs, pair_review, private_map, self.seed,
                individual_review_sha256=canonical_sha256(individual_review),
                pair_review_sha256=canonical_sha256(pair_review),
            )

    def test_only_full_actual_inventory_can_pass_proposed_gate(self):
        slots = copy.deepcopy(self.slots)
        results = copy.deepcopy(self.results)
        criteria = copy.deepcopy(self.criteria)
        additions = [
            ("bible-three", False), ("bible-four", False),
            ("bible-five", False), ("bible-six", False),
            ("general-two", True),
        ]
        for case_id, general in additions:
            question = "General instruction." if general else f"Question for {case_id}."
            criteria[case_id] = {
                "question": question,
                "general_control": general,
                "expected_coverage": ["Answer the constructed request."],
                "factual_criteria": [] if general else [{
                    "criterion_id": "fact-one",
                    "statement": "Preserve the constructed source qualification.",
                    "source_refs": ["source:constructed"],
                }],
                "generic_evaluation_rules": [
                    "Review all material assertions and requested coverage."
                ],
            }
            for condition in ("B-original", "B-guided"):
                slot_id = f"{case_id}::{condition}"
                slots.append({
                    "slot_id": slot_id,
                    "case_id": case_id,
                    "condition_id": condition,
                    "general_control": general,
                    "question": question,
                })
                answer = f"Constructed answer for {slot_id}."
                results.append({
                    "slot_id": slot_id,
                    "status": "complete",
                    "final_text": answer,
                    "final_text_sha256": digest(answer),
                    "receipt_sha256": digest("receipt-" + slot_id),
                })
        individual, pairs, private_map = build_masked_packets(
            slots, results, criteria, self.seed
        )
        individual_review = self.individual_review(individual)
        pair_review = self.pair_review(pairs, private_map)
        integrated = integrate_reviews(
            slots, results, criteria, individual, individual_review,
            pairs, pair_review, private_map, self.seed,
            individual_review_sha256=canonical_sha256(individual_review),
            pair_review_sha256=canonical_sha256(pair_review),
        )
        self.assertTrue(
            integrated["promotion_gate"]["thresholds"]["actual_protocol_counts_required"]
        )
        self.assertTrue(integrated["promotion_gate"]["passed"])
        self.assertEqual(
            integrated["promotion_gate"]["recommendation"],
            "proposed_limited_private_trial_gate_passed",
        )

    def test_missing_corrupt_hash_and_duplicate_collection_rows_are_rejected(self):
        missing = self.results[:-1]
        with self.assertRaisesRegex(GuidanceReviewError, "exactly cover"):
            self.packets(missing)
        duplicate = self.results + [copy.deepcopy(self.results[0])]
        with self.assertRaisesRegex(GuidanceReviewError, "Duplicate result"):
            self.packets(duplicate)
        corrupt = copy.deepcopy(self.results)
        corrupt[0]["final_text_sha256"] = "0" * 64
        with self.assertRaisesRegex(GuidanceReviewError, "does not match exact text"):
            self.packets(corrupt)
        duplicate_slots = self.slots + [copy.deepcopy(self.slots[0])]
        with self.assertRaisesRegex(GuidanceReviewError, "Duplicate planned slot"):
            build_masked_packets(duplicate_slots, self.results, self.criteria, self.seed)

    def test_partials_and_uncertain_text_are_reviewed_while_missing_is_not_semantic_failure(self):
        results = copy.deepcopy(self.results)
        results[1]["status"] = "partial"
        results[2]["status"] = "uncertain"
        results[3].update(
            status="uncertain", final_text=None, final_text_sha256=None, receipt_sha256=None
        )
        results[4].update(
            status="unsubmitted", final_text=None, final_text_sha256=None, receipt_sha256=None
        )
        result = self.integrate(results)
        self.assertEqual(result["totals"], {
            "planned": 6, "complete": 2, "partial": 1, "uncertain": 2,
            "unsubmitted": 1, "reviewable": 4, "reviewed": 4,
        })
        self.assertEqual(result["general_controls"]["incorrect_answers"], 0)
        self.assertEqual(result["general_controls"]["missing_or_unreviewable_answers"], 1)
        self.assertEqual(
            result["promotion_gate"]["recommendation"],
            "constructed_fixture_descriptive_only",
        )

    def test_strict_issue_reasons_evidence_and_review_closure(self):
        individual, _, _ = self.packets()
        review = self.individual_review(individual)
        review["assessments"].pop()
        with self.assertRaisesRegex(GuidanceReviewError, "exactly cover"):
            freeze_review(individual, review)
        review = self.individual_review(individual)
        review["assessments"][0]["material_errors"] = [{
            "finding": "Missing evidence fields.", "reason": "Constructed.",
            "evidence_refs": [],
        }]
        with self.assertRaisesRegex(GuidanceReviewError, "nonempty list"):
            freeze_review(individual, review)

    def test_packet_map_and_review_freeze_mismatches_fail(self):
        individual, pairs, private_map = self.packets()
        individual_review = self.individual_review(individual)
        pair_review = self.pair_review(pairs, private_map)
        changed_packet = copy.deepcopy(individual)
        changed_packet["limitations"][0] += " Changed."
        with self.assertRaisesRegex(GuidanceReviewError, "regeneration"):
            integrate_reviews(
                self.slots, self.results, self.criteria, changed_packet, individual_review,
                pairs, pair_review, private_map, self.seed,
                individual_review_sha256=canonical_sha256(individual_review),
                pair_review_sha256=canonical_sha256(pair_review),
                expected_counts=self.expected,
            )
        changed_map = copy.deepcopy(private_map)
        changed_map["pairs"][0]["left"]["condition_id"] = "B-guided" if (
            changed_map["pairs"][0]["left"]["condition_id"] == "B-original"
        ) else "B-original"
        with self.assertRaisesRegex(GuidanceReviewError, "Private map"):
            integrate_reviews(
                self.slots, self.results, self.criteria, individual, individual_review,
                pairs, pair_review, changed_map, self.seed,
                individual_review_sha256=canonical_sha256(individual_review),
                pair_review_sha256=canonical_sha256(pair_review),
                expected_counts=self.expected,
            )
        with self.assertRaisesRegex(GuidanceReviewError, "canonical freeze"):
            integrate_reviews(
                self.slots, self.results, self.criteria, individual, individual_review,
                pairs, pair_review, private_map, self.seed,
                individual_review_sha256="0" * 64,
                pair_review_sha256=canonical_sha256(pair_review),
                expected_counts=self.expected,
            )

    def test_stricter_gate_blocks_cross_case_omission_offset_and_different_attribution_errors(self):
        def mutate(review, _packet, private_map):
            self.assessment(review, private_map, "bible-one", "B-original")[
                "omissions"
            ] = [self.issue("Original omission in case one")]
            self.assessment(review, private_map, "bible-two", "B-guided")[
                "omissions"
            ] = [self.issue("Guided omission in case two")]
            original = self.assessment(review, private_map, "bible-one", "B-original")
            guided = self.assessment(review, private_map, "bible-one", "B-guided")
            original["attribution_scope_errors"] = [{
                "error_kind": "attribution", **self.issue("Original attribution error")
            }]
            guided["attribution_scope_errors"] = [{
                "error_kind": "attribution", **self.issue("Different guided attribution error")
            }]

        result = self.integrate(mutate_individual=mutate)
        gates = result["promotion_gate"]["thresholds"]
        self.assertFalse(gates["no_guided_requested_content_omission_answers"])
        self.assertFalse(gates["no_guided_attribution_or_scope_error_answers"])
        self.assertEqual(
            result["bible_pairs"]["matched_complete_omission_answers"],
            {"B-original": 1, "B-guided": 1},
        )
        self.assertEqual(result["bible_pairs"]["regressions"]["omission_pairs"], 1)
        self.assertEqual(
            result["bible_pairs"]["shared_findings"]["attribution_error_pairs"], 1
        )
        self.assertFalse(result["promotion_gate"]["passed"])

    def test_guided_material_error_and_unverified_extra_each_block_gate(self):
        def mutate(review, _packet, private_map):
            guided = self.assessment(review, private_map, "bible-one", "B-guided")
            guided["material_errors"] = [self.issue("Guided material error")]
            guided["unsupported_or_unverified_assertions"] = [
                self.issue("Unverified material extra")
            ]

        result = self.integrate(mutate_individual=mutate)
        gates = result["promotion_gate"]["thresholds"]
        self.assertFalse(gates["no_guided_material_error_answers"])
        self.assertFalse(gates["no_guided_unresolved_material_assertions"])
        self.assertFalse(result["promotion_gate"]["passed"])


if __name__ == "__main__":
    unittest.main()
