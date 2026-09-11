"""Offline native-result normalization for constructed evidence simulations.

This bridge has no transport, credential, environment, tokenizer, or execution
path.  It turns verified native-diagnostic artifacts into the strict events
accepted by :mod:`bibleprep.evidence_collection` and binds those events back to
the exact constructed planner inventory.
"""
from __future__ import annotations

import copy
import hashlib
import re

from bibleprep import native_diagnostics_v1 as native
from bibleprep.evidence_collection import audit_collection, canonical_sha256


SCHEMA_VERSION = 1
PLANNER_KIND = "constructed_offline_evidence_inventory"
FIXTURE_KIND = "constructed_native_outcome_v1"
SIMULATION_KIND = "constructed_native_collection_simulation_v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ARMS = frozenset({"B-memory", "B-packet", "B-lookup"})
PLANNED_STATUSES = frozenset({"planned_offline", "repeat_control_planned"})


class EvidenceNativeError(ValueError):
    """Raised when native evidence cannot be normalized conservatively."""


def _exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise EvidenceNativeError(f"{label} must be an object")
    actual = set(value)
    if actual != set(expected):
        raise EvidenceNativeError(
            f"{label} fields differ; missing={sorted(set(expected) - actual)}, "
            f"extra={sorted(actual - set(expected))}"
        )


def _sha(value, label):
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise EvidenceNativeError(f"{label} must be a lowercase SHA-256 digest")


def _identifier(value, label):
    if not isinstance(value, str) or not value.strip():
        raise EvidenceNativeError(f"{label} must be a nonempty string")


def _plan_slots(plan):
    if (
        not isinstance(plan, dict)
        or type(plan.get("schema_version")) is not int
        or plan["schema_version"] != SCHEMA_VERSION
    ):
        raise EvidenceNativeError("plan must use schema_version 1")
    if plan.get("planner_kind") != PLANNER_KIND:
        raise EvidenceNativeError("simulation accepts only the constructed evidence planner")
    readiness = plan.get("engineering_readiness")
    if not isinstance(readiness, dict) or readiness.get("status") != "ready":
        raise EvidenceNativeError("blocked or malformed engineering plan cannot be simulated")
    execution = plan.get("execution_readiness")
    if not isinstance(execution, dict) or execution.get("status") != "not_ready":
        raise EvidenceNativeError(
            "constructed planner must retain execution_readiness.status=not_ready"
        )
    slots = plan.get("planned_slots")
    count = plan.get("planned_slot_count")
    if (
        not isinstance(slots, list)
        or type(count) is not int
        or count < 1
        or count != len(slots)
    ):
        raise EvidenceNativeError("planned slot inventory is missing or has the wrong count")
    seen = set()
    for index, slot in enumerate(slots):
        label = f"planned_slots[{index}]"
        if not isinstance(slot, dict):
            raise EvidenceNativeError(f"{label} must be an object")
        for field in ("slot_id", "case_id", "arm"):
            _identifier(slot.get(field), f"{label}.{field}")
        if slot["slot_id"] in seen:
            raise EvidenceNativeError(f"duplicate planned slot_id: {slot['slot_id']}")
        seen.add(slot["slot_id"])
        if slot["arm"] not in ARMS:
            raise EvidenceNativeError(f"{label}.arm is not a constructed planner arm")
        if slot.get("status") not in PLANNED_STATUSES:
            raise EvidenceNativeError(f"{label}.status is not a simulatable planner status")
        if "model_input" not in slot:
            raise EvidenceNativeError(f"{label} is missing model_input")
        expected_input = canonical_sha256(slot["model_input"])
        if slot.get("model_input_sha256") != expected_input:
            raise EvidenceNativeError(f"{label}.model_input_sha256 does not match model_input")
    # Reuse the collection auditor's stricter uniqueness checks without events.
    audit_collection(slots, [])
    return slots


def _joined_final(diagnostic):
    completed = diagnostic["completed_final_text"]
    partial = diagnostic["partial_final_text"]
    return "\n".join(item for item in (completed, partial) if item)


def _text_sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_diagnostic_artifact(diagnostic, declared_sha256):
    """Validate one native-diagnostics-v1 artifact and derive collection facts.

    The declared hash binds supplied bytes conceptually, but constructed object
    fixtures use ``canonical_sha256`` rather than claiming filesystem receipt
    verification.  Native parser errors are rejected instead of converted into
    optimistic stop labels.
    """
    _sha(declared_sha256, "declared_sha256")
    if canonical_sha256(diagnostic) != declared_sha256:
        raise EvidenceNativeError("diagnostic artifact hash does not match")
    if (
        not isinstance(diagnostic, dict)
        or type(diagnostic.get("schema_version")) is not int
        or diagnostic["schema_version"] != native.SCHEMA_VERSION
    ):
        raise EvidenceNativeError("diagnostic must use native-diagnostics schema_version 1")
    try:
        summary = native.public_summary(diagnostic, raw_ids_retained=True)
        raw_hash = native.token_ids_sha256(diagnostic["raw_generated_token_ids"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceNativeError("native diagnostic failed schema verification") from exc
    if raw_hash != diagnostic.get("raw_generated_token_ids_sha256"):
        raise EvidenceNativeError("native diagnostic raw token hash does not match")
    if diagnostic.get("generated_token_count") != len(diagnostic["raw_generated_token_ids"]):
        raise EvidenceNativeError("native diagnostic generated token count does not match")
    if summary["parse_issues"]:
        raise EvidenceNativeError("malformed native parser evidence is not reviewable")

    completed = diagnostic["completed_final_text"]
    partial = diagnostic["partial_final_text"]
    if not isinstance(completed, str) or not isinstance(partial, str):
        raise EvidenceNativeError("native final content must be text")
    expected_state = (
        "completed_and_partial" if completed and partial else
        "completed_messages_only" if completed else
        "partial_only" if partial else "absent"
    )
    if summary["final_content_state"] != expected_state:
        raise EvidenceNativeError("native final content state is inconsistent")
    if partial and summary["partial_final_status"] != "present":
        raise EvidenceNativeError("native partial final status is inconsistent")
    if not partial and summary["partial_final_status"] not in {"absent", "empty_open_content"}:
        raise EvidenceNativeError("native partial final status is ambiguous")

    finish = summary["finish_reason"]
    complete = summary["native_turn_complete"]
    provider_stop = summary["provider_stop_reason"]
    if complete and not (
        summary["turn_end_observed"]
        and summary["turn_end_token_present"]
        and summary["parser_at_message_boundary"]
        and summary["stream_extraction_finished_without_error"]
    ):
        raise EvidenceNativeError("native completion flags are inconsistent")
    if finish == "stop":
        if not complete or provider_stop != "stop" or not completed.strip() or partial:
            raise EvidenceNativeError("native stop evidence is inconsistent")
        stop_reason = "stop"
    elif finish == "length":
        if provider_stop != "length":
            raise EvidenceNativeError("native output-limit evidence is inconsistent")
        stop_reason = "output_limit"
    elif finish == "incomplete_tml":
        if complete and completed.strip():
            raise EvidenceNativeError("native incomplete evidence is inconsistent")
        stop_reason = "incomplete"
    else:  # public_summary currently closes this branch, kept fail-closed.
        raise EvidenceNativeError("unsupported native finish reason")

    native_prompt_sha256 = diagnostic.get("prompt_token_ids_sha256")
    if native_prompt_sha256 is not None:
        _sha(native_prompt_sha256, "diagnostic.prompt_token_ids_sha256")
        count = diagnostic.get("prompt_token_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise EvidenceNativeError("diagnostic.prompt_token_count is invalid")
    elif "prompt_token_count" in diagnostic:
        raise EvidenceNativeError("prompt token count lacks a prompt-token hash")
    return {
        "stop_reason": stop_reason,
        "final_text": _joined_final(diagnostic),
        "diagnostic_sha256": declared_sha256,
        "raw_generated_token_ids_sha256": raw_hash,
        "native_prompt_sha256": native_prompt_sha256,
    }


def normalize_native_response(response, run_dir):
    """Normalize an existing receipt-verified native response, without transport.

    This verifies the native sidecar through the existing helper.  It does not
    establish that native prompt tokens are the rendering of a planner input.
    """
    try:
        projection = native.final_text_for_review(response, run_dir)
        summary = native.verify_private_artifact(response, run_dir)
    except ValueError as exc:
        raise EvidenceNativeError("native response receipt verification failed") from exc
    if projection["final_text_withheld_due_to_malformed_structure"]:
        raise EvidenceNativeError("malformed native parser evidence is not reviewable")
    if projection["finish_reason"] == "stop":
        if not projection["native_turn_complete"]:
            raise EvidenceNativeError("native stop evidence is inconsistent")
        stop_reason = "stop"
    elif projection["finish_reason"] == "length":
        stop_reason = "output_limit"
    elif projection["finish_reason"] == "incomplete_tml":
        stop_reason = "incomplete"
    else:
        raise EvidenceNativeError("unsupported native finish reason")
    final_text = "\n".join(
        item for item in (
            projection["completed_final_text"], projection["partial_final_text"]
        ) if item
    )
    return {
        "stop_reason": stop_reason,
        "final_text": final_text,
        "diagnostic_sha256": summary["private_artifact_sha256"],
        "raw_generated_token_ids_sha256": summary["raw_generated_token_ids_sha256"],
        "native_prompt_sha256": response["native_tinker"]["prompt_sha256"],
    }


def _fixture(fixture, slot):
    _exact_keys(fixture, {
        "schema_version", "fixture_kind", "slot_id", "model_input_sha256",
        "outcome_kind", "payload", "payload_sha256",
    }, "fixture")
    if (
        type(fixture["schema_version"]) is not int
        or fixture["schema_version"] != SCHEMA_VERSION
        or fixture["fixture_kind"] != FIXTURE_KIND
    ):
        raise EvidenceNativeError("only labeled constructed native fixtures are accepted")
    if fixture["slot_id"] != slot["slot_id"]:
        raise EvidenceNativeError("fixture slot_id does not match the next planned slot")
    if fixture["model_input_sha256"] != slot["model_input_sha256"]:
        raise EvidenceNativeError("fixture model_input_sha256 does not match the planned input")
    _sha(fixture["payload_sha256"], "fixture.payload_sha256")
    if canonical_sha256(fixture["payload"]) != fixture["payload_sha256"]:
        raise EvidenceNativeError("fixture payload hash does not match")
    if fixture["outcome_kind"] == "diagnostic":
        return normalize_diagnostic_artifact(fixture["payload"], fixture["payload_sha256"])
    if fixture["outcome_kind"] == "failure":
        _exact_keys(fixture["payload"], {"disposition"}, "fixture.payload")
        if fixture["payload"]["disposition"] not in {"failed", "uncertain"}:
            raise EvidenceNativeError("unsupported constructed failure disposition")
        return {"disposition": fixture["payload"]["disposition"]}
    raise EvidenceNativeError("unsupported constructed fixture outcome_kind")


def _binding(slot, slots_sha256, fixture, normalized):
    terminal = (
        {"event": "failure", "disposition": normalized["disposition"]}
        if fixture["outcome_kind"] == "failure" else
        {
            "event": "result", "stop_reason": normalized["stop_reason"],
            "final_text_sha256": _text_sha256(normalized["final_text"]),
        }
    )
    binding = {
        "schema_version": SCHEMA_VERSION,
        "slot_id": slot["slot_id"],
        "planned_slots_sha256": slots_sha256,
        "slot_sha256": canonical_sha256(slot),
        "model_input_sha256": slot["model_input_sha256"],
        "fixture_payload_sha256": fixture["payload_sha256"],
        "native_prompt_sha256": normalized.get("native_prompt_sha256"),
        "terminal": terminal,
    }
    return binding, canonical_sha256(binding)


def simulate_sequential_collection(plan, fixtures):
    """Run a deterministic stop-all simulation over ordered injected fixtures."""
    slots = _plan_slots(plan)
    if not isinstance(fixtures, list):
        raise EvidenceNativeError("fixtures must be an ordered list")
    if len(fixtures) > len(slots):
        raise EvidenceNativeError("more fixtures were supplied than planned slots")
    journal = []
    bindings = []
    slots_sha256 = canonical_sha256(slots)
    stopped = False
    for index, fixture in enumerate(fixtures):
        if stopped:
            raise EvidenceNativeError("fixture appears after the fixed stop-all trigger")
        slot = slots[index]
        # Submission is recorded before any simulated outcome is interpreted.
        journal.append({"event": "submission", "slot_id": slot["slot_id"]})
        normalized = _fixture(fixture, slot)
        binding, receipt_sha256 = _binding(slot, slots_sha256, fixture, normalized)
        bindings.append({"receipt_sha256": receipt_sha256, "binding": binding})
        if fixture["outcome_kind"] == "failure":
            journal.append({
                "event": "failure", "slot_id": slot["slot_id"],
                "disposition": normalized["disposition"],
                "receipt_sha256": receipt_sha256,
            })
            stopped = True
        else:
            journal.append({
                "event": "result", "slot_id": slot["slot_id"],
                "stop_reason": normalized["stop_reason"],
                "final_text": normalized["final_text"],
                "receipt_sha256": receipt_sha256,
            })
            stopped = normalized["stop_reason"] != "stop" or not normalized["final_text"].strip()
    if len(fixtures) < len(slots) and not stopped:
        raise EvidenceNativeError(
            "fixtures ended before either the full inventory or a stop-all trigger"
        )
    audit = audit_collection(slots, journal)
    return {
        "schema_version": SCHEMA_VERSION,
        "simulation_kind": SIMULATION_KIND,
        "plan_sha256": canonical_sha256(plan),
        "planned_slots_sha256": slots_sha256,
        "execution_readiness": copy.deepcopy(plan["execution_readiness"]),
        "journal": journal,
        "receipt_bindings": bindings,
        "audit": audit,
        "model_calls": 0,
        "network_requests": 0,
    }


def verify_simulated_collection(plan, fixtures, record):
    """Rebuild and compare a simulation, failing on any missing or changed binding."""
    rebuilt = simulate_sequential_collection(plan, fixtures)
    try:
        matches = canonical_sha256(record) == canonical_sha256(rebuilt)
    except (TypeError, ValueError) as exc:
        raise EvidenceNativeError("simulated collection record is not finite JSON") from exc
    if not matches:
        raise EvidenceNativeError("simulated collection record failed exact verification")
    receipts = {item["receipt_sha256"] for item in record["receipt_bindings"]}
    terminal = [event for event in record["journal"] if event["event"] != "submission"]
    if len(receipts) != len(record["receipt_bindings"]) or any(
        event["receipt_sha256"] not in receipts for event in terminal
    ):
        raise EvidenceNativeError("terminal event is missing its unique receipt binding")
    return record["audit"]
