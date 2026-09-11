"""Constructed tests for pure evidence collection accounting."""
import copy
import unittest

from bibleprep.evidence_collection import (
    CollectionAccountingError,
    audit_collection,
    canonical_sha256,
)


RECEIPT = "a" * 64


def slots(count=3):
    arms = ("B-memory", "B-packet", "B-lookup")
    return [
        {"slot_id": f"case-1::{arms[index]}", "case_id": "case-1", "arm": arms[index],
         "settings_sha256": str(index) * 64}
        for index in range(count)
    ]


def submission(slot_id):
    return {"event": "submission", "slot_id": slot_id}


def result(slot_id, text="Constructed final.", stop_reason="stop", receipt=RECEIPT):
    return {
        "event": "result", "slot_id": slot_id, "stop_reason": stop_reason,
        "final_text": text, "receipt_sha256": receipt,
    }


def failure(slot_id, disposition="uncertain", receipt=None):
    return {
        "event": "failure", "slot_id": slot_id,
        "disposition": disposition, "receipt_sha256": receipt,
    }


class EvidenceCollectionTests(unittest.TestCase):
    def test_success_binds_exact_inventory_journal_and_all_answers(self):
        plan = slots()
        journal = []
        for item in plan:
            journal.extend([submission(item["slot_id"]), result(item["slot_id"])])
        audit = audit_collection(plan, journal)

        self.assertEqual(audit["planned_slots_sha256"], canonical_sha256(plan))
        self.assertEqual(audit["journal_sha256"], canonical_sha256(journal))
        self.assertEqual(audit["totals"], {
            "planned": 3, "complete": 3, "partial": 0, "failed": 0,
            "uncertain": 0, "outstanding": 0, "unsubmitted": 0,
        })
        self.assertEqual(len(audit["reviewable_answers"]), 3)
        self.assertEqual(audit["arms"]["B-memory"]["complete"], 1)
        self.assertEqual(audit["arms"]["B-packet"]["planned"], 1)
        self.assertTrue(audit["collection_evidence"]["all_planned_complete"])
        self.assertEqual(audit["collection_evidence"]["semantic_answer_completeness"], "not_assessed")

        changed = copy.deepcopy(plan)
        changed[0]["settings_sha256"] = "f" * 64
        self.assertNotEqual(audit["planned_slots_sha256"], canonical_sha256(changed))

    def test_output_limit_preserves_partial_and_unsubmitted_denominator(self):
        plan = slots()
        first, second = plan[0]["slot_id"], plan[1]["slot_id"]
        journal = [
            submission(first), result(first),
            submission(second), result(second, "Partial visible final", "output_limit", "b" * 64),
        ]
        audit = audit_collection(plan, journal)

        self.assertEqual(audit["totals"], {
            "planned": 3, "complete": 1, "partial": 1, "failed": 0,
            "uncertain": 0, "outstanding": 0, "unsubmitted": 1,
        })
        partial = audit["reviewable_answers"][1]
        self.assertEqual(partial["answer_status"], "partial")
        self.assertEqual(partial["final_text"], "Partial visible final")
        self.assertEqual(partial["stop_reason"], "output_limit")
        self.assertEqual(audit["slot_outcomes"][2]["outcome"], "unsubmitted")
        self.assertFalse(audit["slot_outcomes"][2]["submitted"])

        with self.assertRaisesRegex(CollectionAccountingError, "after the fixed stop-all"):
            audit_collection(plan, journal + [submission(plan[2]["slot_id"])])

    def test_incomplete_native_final_is_reviewable_partial_and_stops(self):
        plan = slots(2)
        journal = [submission(plan[0]["slot_id"]), result(
            plan[0]["slot_id"], "Unverified framing final", "incomplete", "c" * 64
        )]
        audit = audit_collection(plan, journal)
        self.assertEqual(audit["totals"]["partial"], 1)
        self.assertEqual(audit["slot_outcomes"][0]["outcome_reason"], "incomplete_native_turn")
        self.assertEqual(audit["reviewable_answers"][0]["answer_status"], "partial")

    def test_returned_no_final_is_failed_but_not_a_transport_failure(self):
        plan = slots(2)
        audit = audit_collection(plan, [
            submission(plan[0]["slot_id"]), result(plan[0]["slot_id"], " \n", "stop"),
        ])
        first = audit["slot_outcomes"][0]
        self.assertEqual(first["outcome"], "failed")
        self.assertEqual(first["outcome_reason"], "returned_no_final_content")
        self.assertTrue(first["returned_result"])
        self.assertEqual(audit["reviewable_answers"], [])
        self.assertEqual(audit["totals"]["unsubmitted"], 1)

    def test_timeout_uncertain_stops_without_retry_or_later_submission(self):
        plan = slots()
        slot_id = plan[0]["slot_id"]
        journal = [submission(slot_id), failure(slot_id, "uncertain")]
        audit = audit_collection(plan, journal)
        self.assertEqual(audit["totals"]["uncertain"], 1)
        self.assertEqual(audit["totals"]["unsubmitted"], 2)
        self.assertEqual(audit["slot_outcomes"][0]["outcome_reason"], "transport_uncertain")

        for later in (submission(slot_id), submission(plan[1]["slot_id"])):
            with self.subTest(later=later), self.assertRaisesRegex(
                CollectionAccountingError, "after the fixed stop-all"
            ):
                audit_collection(plan, journal + [later])

    def test_submitted_without_terminal_is_uncertain_and_outstanding(self):
        plan = slots()
        audit = audit_collection(plan, [submission(plan[0]["slot_id"])])
        self.assertEqual(audit["totals"]["uncertain"], 1)
        self.assertEqual(audit["totals"]["outstanding"], 1)
        self.assertEqual(audit["totals"]["unsubmitted"], 2)
        self.assertTrue(audit["slot_outcomes"][0]["outstanding"])
        self.assertFalse(audit["slot_outcomes"][0]["terminal_event"])
        self.assertEqual(audit["stop_trigger"]["reason"], "submitted_outstanding")

        with self.assertRaisesRegex(CollectionAccountingError, "still outstanding"):
            audit_collection(plan, [
                submission(plan[0]["slot_id"]), submission(plan[1]["slot_id"]),
            ])

    def test_unknown_duplicate_and_out_of_order_events_are_rejected(self):
        plan = slots()
        first = plan[0]["slot_id"]
        cases = [
            ([submission("unknown")], "Unknown submitted"),
            ([result(first)], "does not follow its open submission"),
            ([submission(plan[1]["slot_id"])], "Submission order differs"),
            ([submission(first), result(first), submission(first)], "Duplicate submission"),
            ([submission(first), result(first), result(first)], "does not follow its open submission"),
            ([{"event": "mystery", "slot_id": first}], "Unsupported journal event"),
        ]
        for journal, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(CollectionAccountingError, message):
                audit_collection(plan, journal)

    def test_strict_events_reject_hidden_reasoning_and_bad_receipts(self):
        plan = slots(1)
        slot_id = plan[0]["slot_id"]
        with self.assertRaisesRegex(CollectionAccountingError, "extra=.*reasoning"):
            audit_collection(plan, [
                submission(slot_id), {**result(slot_id), "reasoning": "must not be accepted"},
            ])
        with self.assertRaisesRegex(CollectionAccountingError, "lowercase SHA-256"):
            audit_collection(plan, [submission(slot_id), result(slot_id, receipt="A" * 64)])

    def test_plan_requires_distinct_ids_pairs_and_finite_json(self):
        plan = slots(2)
        duplicate_id = copy.deepcopy(plan)
        duplicate_id[1]["slot_id"] = duplicate_id[0]["slot_id"]
        duplicate_pair = copy.deepcopy(plan)
        duplicate_pair[1]["arm"] = duplicate_pair[0]["arm"]
        nonfinite = copy.deepcopy(plan)
        nonfinite[0]["temperature"] = float("nan")
        for bad, message in (
            (duplicate_id, "Duplicate planned slot_id"),
            (duplicate_pair, "Duplicate planned case/arm pair"),
            (nonfinite, "non-finite"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(CollectionAccountingError, message):
                audit_collection(bad, [])


if __name__ == "__main__":
    unittest.main()
