"""Pure, deterministic accounting for a bounded evidence comparison journal.

This module consumes normalized transport facts.  It does not contact a model,
inspect native output, score answers, apply a completeness gate, or write files.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re


SCHEMA_VERSION = 1
STOP_REASONS = frozenset({"stop", "output_limit", "incomplete"})
FAILURE_DISPOSITIONS = frozenset({"failed", "uncertain"})
OUTCOMES = ("complete", "partial", "failed", "uncertain", "outstanding", "unsubmitted")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class CollectionAccountingError(ValueError):
    """Raised when a planned inventory or append-only journal is invalid."""


def _validate_json(value, label):
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CollectionAccountingError(f"{label} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CollectionAccountingError(f"{label} has a non-string object key")
            _validate_json(item, f"{label}.{key}")
        return
    raise CollectionAccountingError(f"{label} is not finite JSON data")


def _canonical_bytes(value):
    _validate_json(value, "value")
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value):
    """Hash finite JSON data with a deterministic UTF-8 representation."""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _text_sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_identifier(value, label):
    if not isinstance(value, str) or not value.strip():
        raise CollectionAccountingError(f"{label} must be a nonempty string")


def _require_sha(value, label, *, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise CollectionAccountingError(f"{label} must be a lowercase SHA-256 digest")


def _require_exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise CollectionAccountingError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise CollectionAccountingError(
            f"{label} fields differ; missing={missing}, extra={extra}"
        )


def _validate_plan(planned_slots):
    if not isinstance(planned_slots, list):
        raise CollectionAccountingError("planned_slots must be a list")
    _validate_json(planned_slots, "planned_slots")
    by_id = {}
    case_arms = set()
    for index, slot in enumerate(planned_slots):
        label = f"planned_slots[{index}]"
        if not isinstance(slot, dict):
            raise CollectionAccountingError(f"{label} must be an object")
        for field in ("slot_id", "case_id", "arm"):
            if field not in slot:
                raise CollectionAccountingError(f"{label} is missing {field}")
            _require_identifier(slot[field], f"{label}.{field}")
        slot_id = slot["slot_id"]
        if slot_id in by_id:
            raise CollectionAccountingError(f"Duplicate planned slot_id: {slot_id}")
        pair = (slot["case_id"], slot["arm"])
        if pair in case_arms:
            raise CollectionAccountingError(
                f"Duplicate planned case/arm pair: {slot['case_id']} / {slot['arm']}"
            )
        by_id[slot_id] = slot
        case_arms.add(pair)
    return by_id


def _empty_slot_outcome(slot):
    return {
        "slot_id": slot["slot_id"],
        "case_id": slot["case_id"],
        "arm": slot["arm"],
        "outcome": "unsubmitted",
        "outcome_reason": "not_submitted",
        "submitted": False,
        "terminal_event": False,
        "returned_result": False,
        "reviewable": False,
        "outstanding": False,
        "stop_reason": None,
        "receipt_sha256": None,
        "final_text_sha256": None,
    }


def _validate_submission(event, label):
    _require_exact_keys(event, {"event", "slot_id"}, label)
    _require_identifier(event["slot_id"], f"{label}.slot_id")


def _validate_result(event, label):
    _require_exact_keys(
        event, {"event", "slot_id", "stop_reason", "final_text", "receipt_sha256"}, label
    )
    _require_identifier(event["slot_id"], f"{label}.slot_id")
    if event["stop_reason"] not in STOP_REASONS:
        raise CollectionAccountingError(f"Unsupported {label}.stop_reason")
    if not isinstance(event["final_text"], str):
        raise CollectionAccountingError(f"{label}.final_text must be a string")
    _require_sha(event["receipt_sha256"], f"{label}.receipt_sha256")


def _validate_failure(event, label):
    _require_exact_keys(
        event, {"event", "slot_id", "disposition", "receipt_sha256"}, label
    )
    _require_identifier(event["slot_id"], f"{label}.slot_id")
    if event["disposition"] not in FAILURE_DISPOSITIONS:
        raise CollectionAccountingError(f"Unsupported {label}.disposition")
    _require_sha(event["receipt_sha256"], f"{label}.receipt_sha256", nullable=True)


def _counts(slot_outcomes, arm=None):
    selected = [row for row in slot_outcomes if arm is None or row["arm"] == arm]
    outcomes = Counter(row["outcome"] for row in selected)
    return {
        "planned": len(selected),
        "complete": outcomes["complete"],
        "partial": outcomes["partial"],
        "failed": outcomes["failed"],
        "uncertain": outcomes["uncertain"],
        # Outstanding is an overlapping subset of uncertain, not another outcome bucket.
        "outstanding": sum(row["outstanding"] for row in selected),
        "unsubmitted": outcomes["unsubmitted"],
    }


def audit_collection(planned_slots, journal):
    """Validate and account for one sequential, stop-all collection journal.

    ``stop`` is a normalized fact meaning a native adapter has validated the
    completed turn. ``output_limit`` and ``incomplete`` never become complete
    solely because final text exists. Unknown native facts must be rejected by
    the adapter rather than mapped optimistically here.
    """
    by_id = _validate_plan(planned_slots)
    if not isinstance(journal, list):
        raise CollectionAccountingError("journal must be a list")
    _validate_json(journal, "journal")

    slot_outcomes = [_empty_slot_outcome(slot) for slot in planned_slots]
    outcome_by_id = {row["slot_id"]: row for row in slot_outcomes}
    submitted = set()
    open_slot = None
    open_submission_index = None
    next_plan_index = 0
    stop_trigger = None
    reviewable_answers = []

    for index, event in enumerate(journal):
        label = f"journal[{index}]"
        if not isinstance(event, dict) or not isinstance(event.get("event"), str):
            raise CollectionAccountingError(f"{label} must have a string event field")
        kind = event["event"]

        if kind == "submission":
            _validate_submission(event, label)
            slot_id = event["slot_id"]
            if stop_trigger is not None:
                raise CollectionAccountingError("Submission appears after the fixed stop-all trigger")
            if slot_id not in by_id:
                raise CollectionAccountingError(f"Unknown submitted slot_id: {slot_id}")
            if slot_id in submitted:
                raise CollectionAccountingError(f"Duplicate submission or retry for slot_id: {slot_id}")
            if open_slot is not None:
                raise CollectionAccountingError(
                    f"Submission appears while slot {open_slot} is still outstanding"
                )
            expected = planned_slots[next_plan_index]["slot_id"]
            if slot_id != expected:
                raise CollectionAccountingError(
                    f"Submission order differs from plan; expected {expected}, received {slot_id}"
                )
            submitted.add(slot_id)
            open_slot = slot_id
            open_submission_index = index
            next_plan_index += 1
            row = outcome_by_id[slot_id]
            row.update({
                "outcome": "uncertain", "outcome_reason": "submitted_outstanding",
                "submitted": True, "outstanding": True,
            })
            continue

        if kind not in {"result", "failure"}:
            raise CollectionAccountingError(f"Unsupported journal event: {kind}")
        if kind == "result":
            _validate_result(event, label)
        else:
            _validate_failure(event, label)
        slot_id = event["slot_id"]
        if slot_id not in by_id:
            raise CollectionAccountingError(f"Unknown terminal slot_id: {slot_id}")
        if open_slot != slot_id:
            raise CollectionAccountingError(
                f"Terminal event for {slot_id} does not follow its open submission"
            )

        row = outcome_by_id[slot_id]
        row.update({
            "terminal_event": True, "outstanding": False,
            "receipt_sha256": event["receipt_sha256"],
        })
        open_slot = None
        open_submission_index = None
        if kind == "failure":
            outcome = event["disposition"]
            row.update({
                "outcome": outcome,
                "outcome_reason": "transport_failure" if outcome == "failed" else "transport_uncertain",
            })
            stop_trigger = {"slot_id": slot_id, "outcome": outcome, "journal_index": index}
            continue

        final_text = event["final_text"]
        has_final = bool(final_text.strip())
        row.update({
            "returned_result": True,
            "stop_reason": event["stop_reason"],
            "final_text_sha256": _text_sha256(final_text) if has_final else None,
        })
        if event["stop_reason"] == "stop" and has_final:
            outcome, reason = "complete", "validated_native_stop"
        elif has_final:
            outcome, reason = "partial", (
                "output_limit" if event["stop_reason"] == "output_limit"
                else "incomplete_native_turn"
            )
        else:
            outcome, reason = "failed", "returned_no_final_content"
        row.update({"outcome": outcome, "outcome_reason": reason, "reviewable": has_final})
        if has_final:
            reviewable_answers.append({
                "slot_id": slot_id,
                "case_id": row["case_id"],
                "arm": row["arm"],
                "answer_status": outcome,
                "stop_reason": event["stop_reason"],
                "final_text": final_text,
                "final_text_sha256": row["final_text_sha256"],
                "receipt_sha256": event["receipt_sha256"],
                "review_required": True,
            })
        if outcome != "complete":
            stop_trigger = {"slot_id": slot_id, "outcome": outcome, "journal_index": index}

    if open_slot is not None:
        stop_trigger = {
            "slot_id": open_slot,
            "outcome": "uncertain",
            "reason": "submitted_outstanding",
            "journal_index": open_submission_index,
        }

    totals = _counts(slot_outcomes)
    arms = {
        arm: _counts(slot_outcomes, arm)
        for arm in sorted({slot["arm"] for slot in planned_slots})
    }
    planned_count = totals["planned"]
    complete_rate = totals["complete"] / planned_count if planned_count else None
    reviewable_rate = (totals["complete"] + totals["partial"]) / planned_count if planned_count else None
    return {
        "schema_version": SCHEMA_VERSION,
        "policy": "sequential_one_request_fixed_stop_all_v1",
        "planned_slots_sha256": canonical_sha256(planned_slots),
        "journal_sha256": canonical_sha256(journal),
        "hash_encoding": "sha256(canonical finite JSON UTF-8); final text hashes use exact UTF-8 bytes",
        "totals": totals,
        "arms": arms,
        "slot_outcomes": slot_outcomes,
        "reviewable_answers": reviewable_answers,
        "stop_trigger": stop_trigger,
        "collection_evidence": {
            "inventory_bound": True,
            "journal_valid": True,
            "all_planned_complete": bool(planned_count) and totals["complete"] == planned_count,
            "complete_final_answer_rate": complete_rate,
            "reviewable_final_answer_rate": reviewable_rate,
            "semantic_answer_completeness": "not_assessed",
            "collection_completeness_gate": "not_supplied_or_evaluated",
            "model_quality_or_promotion_decision": "not_assessed",
        },
        "limitations": [
            "Transport events are normalized synthetic facts pending a verified native adapter.",
            "Caller-supplied receipt hashes are opaque bindings; this audit does not verify native receipts.",
            "Outstanding is included in uncertain and is also reported separately, so those counts overlap.",
            "Technical completion does not establish semantic completeness, expertise, answer quality, or promotion readiness.",
        ],
    }
