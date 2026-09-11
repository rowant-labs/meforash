"""Coordinate an entirely offline, notice-bearing native collection simulation.

The coordinator rebuilds every upstream artifact from explicit inputs.  It has
no live transport, execution switch, environment access, retry path, model
call, training action, chat integration, or file writer.
"""
from __future__ import annotations

import copy
from decimal import Decimal, localcontext
import hashlib
from pathlib import Path

from bibleprep import evidence_delivery as delivery
from bibleprep import evidence_collection as collection
from bibleprep import evidence_native as native_bridge
from bibleprep import evidence_requests as request_bridge
from bibleprep import evaluate_evidence as planner
from bibleprep import native_diagnostics_v1 as native_diagnostics
from bibleprep.evidence import PRIVATE_DRAFTS, ROOT, sha256
from bibleprep.evidence_collection import canonical_sha256


SCHEMA_VERSION = 1
COORDINATOR_KIND = "constructed_offline_notice_coordinator_v1"
SIMULATION_KIND = "constructed_offline_notice_simulation_v1"
CURRENT_OPEN_REQUIREMENTS = [
    "live_native_transport_is_not_implemented",
    "fresh_question_and_quality_protocol_are_not_frozen",
    "current_provider_pricing_is_not_verified",
    "live_sampling_allowance_is_not_recorded",
    "checkpoint_identity_retention_and_live_preflight_are_not_verified",
]


class EvidenceCoordinatorError(ValueError):
    """Raised when an offline coordinated artifact fails closed."""


def _canonical_equal(left, right):
    try:
        return canonical_sha256(left) == canonical_sha256(right)
    except (TypeError, ValueError) as exc:
        raise EvidenceCoordinatorError("coordinator artifact is not finite JSON") from exc


def _module_bindings():
    return {
        "coordinator_module_sha256": sha256(Path(__file__)),
        "delivery_module_sha256": sha256(Path(delivery.__file__)),
        "collection_accounting_module_sha256": sha256(Path(collection.__file__)),
        "planner_module_sha256": sha256(Path(planner.__file__)),
        "request_preparation_module_sha256": sha256(Path(request_bridge.__file__)),
        "native_bridge_module_sha256": sha256(Path(native_bridge.__file__)),
        "native_diagnostics_module_sha256": sha256(Path(native_diagnostics.__file__)),
    }


def _recompute_slot_hashes(slot):
    model_input = slot.get("model_input")
    if not isinstance(model_input, dict) or set(model_input) != {
        "system_prompt", "question", "evidence",
    }:
        raise EvidenceCoordinatorError("planner slot model_input shape changed")
    if any(not isinstance(model_input[field], str) for field in model_input):
        raise EvidenceCoordinatorError("planner slot model_input must contain text")
    if slot.get("question") != model_input["question"]:
        raise EvidenceCoordinatorError("planner slot question differs from model_input")
    slot["question_sha256"] = canonical_sha256(slot["question"])
    slot["evidence_content"] = model_input["evidence"]
    slot["evidence_content_sha256"] = hashlib.sha256(
        model_input["evidence"].encode("utf-8")
    ).hexdigest()
    slot["model_input_sha256"] = canonical_sha256(model_input)


def build_coordinated_plan(*, root, cases, settings, policy, registry, saved_projection,
                           notice_manifest, record_directory=None, input_file_sha256=None):
    """Rebuild the original plan and replace evidence with verified notice delivery."""
    root = Path(root).resolve()
    directory = record_directory or root / PRIVATE_DRAFTS
    try:
        base = planner.build_offline_plan(
            root=root,
            cases=cases,
            settings=settings,
            policy=policy,
            registry=registry,
            saved_projection=saved_projection,
            record_directory=directory,
            input_file_sha256=input_file_sha256,
        )
    except ValueError as exc:
        raise EvidenceCoordinatorError("original evidence plan rebuild failed") from exc
    if base["engineering_readiness"]["status"] != "ready":
        raise EvidenceCoordinatorError("blocked original evidence plan cannot be coordinated")

    coordinated = copy.deepcopy(base)
    base_sha256 = canonical_sha256(base)
    delivered_slots = []
    cached = {}
    for slot in coordinated["planned_slots"]:
        keys = slot.get("evidence_component_keys")
        if not isinstance(keys, list):
            raise EvidenceCoordinatorError("planner slot lacks evidence component inventory")
        if not keys:
            if slot["model_input"]["evidence"] != "" or slot["evidence_content"] != "":
                raise EvidenceCoordinatorError("memory, control, or lookup-miss evidence is not empty")
            slot["delivery_provenance"] = None
            _recompute_slot_hashes(slot)
            continue

        cache_key = tuple(keys)
        if cache_key not in cached:
            try:
                candidate = delivery.build_candidate_bundle(
                    registry, keys, notice_manifest, root=root, record_directory=directory,
                )
                verified = delivery.verify_for_use(
                    candidate, registry, notice_manifest, root=root, record_directory=directory,
                )
                rendered = delivery.render_model_input(
                    verified, registry, notice_manifest, root=root, record_directory=directory,
                )
            except ValueError as exc:
                raise EvidenceCoordinatorError(
                    "notice-bearing evidence delivery verification failed"
                ) from exc
            cached[cache_key] = (candidate, verified, rendered)
        candidate, verified, rendered = cached[cache_key]
        slot["model_input"]["evidence"] = rendered
        slot["delivery_provenance"] = {
            "component_keys": list(keys),
            "candidate_sha256": verified["candidate_sha256"],
            "registry_sha256": verified["registry_sha256"],
            "notice_manifest_sha256": candidate["notice_manifest_sha256"],
        }
        _recompute_slot_hashes(slot)
        delivered_slots.append({
            "slot_id": slot["slot_id"],
            "component_keys": list(keys),
            "candidate_sha256": verified["candidate_sha256"],
            "registry_sha256": verified["registry_sha256"],
            "notice_manifest_sha256": candidate["notice_manifest_sha256"],
            "evidence_content_sha256": slot["evidence_content_sha256"],
            "model_input_sha256": slot["model_input_sha256"],
        })

    coordinated["execution_readiness"] = {
        "status": "not_ready",
        "open_requirements": list(CURRENT_OPEN_REQUIREMENTS),
    }
    bindings = coordinated.get("bindings")
    if not isinstance(bindings, dict):
        raise EvidenceCoordinatorError("original plan bindings are malformed")
    bindings.update({
        **_module_bindings(),
        "base_plan_sha256": base_sha256,
        "notice_manifest_content_sha256": canonical_sha256(notice_manifest),
        "delivered_slots_sha256": canonical_sha256(delivered_slots),
    })
    coordinated["coordinator"] = {
        "schema_version": SCHEMA_VERSION,
        "coordinator_kind": COORDINATOR_KIND,
        "base_plan_sha256": base_sha256,
        "delivered_slots": delivered_slots,
        "generation_authorized": False,
        "training_authorized": False,
    }
    coordinated["model_calls"] = 0
    coordinated["network_requests"] = 0
    return coordinated


def prepare_mock_coordination(*, root, cases, settings, policy, registry, saved_projection,
                              notice_manifest, input_rate_usd_per_million,
                              output_rate_usd_per_million, allowance_usd,
                              comparison_manifest=request_bridge.MANIFEST,
                              record_directory=None, input_file_sha256=None):
    """Build notice-bearing slots and exact locally rendered request records."""
    plan = build_coordinated_plan(
        root=root, cases=cases, settings=settings, policy=policy, registry=registry,
        saved_projection=saved_projection, notice_manifest=notice_manifest,
        record_directory=record_directory, input_file_sha256=input_file_sha256,
    )
    try:
        prepared_requests = request_bridge.prepare_constructed_requests(
            plan,
            input_rate_usd_per_million=input_rate_usd_per_million,
            output_rate_usd_per_million=output_rate_usd_per_million,
            allowance_usd=allowance_usd,
            comparison_manifest=comparison_manifest,
        )
    except ValueError as exc:
        raise EvidenceCoordinatorError("exact native request preparation failed") from exc
    return {
        "schema_version": SCHEMA_VERSION,
        "coordination_kind": COORDINATOR_KIND,
        "coordinated_plan_sha256": canonical_sha256(plan),
        "prepared_requests_sha256": canonical_sha256(prepared_requests),
        "coordinated_plan": plan,
        "prepared_requests": prepared_requests,
        "authorization": {
            "fixture_simulation_only": True,
            "generation_authorized": False,
            "training_authorized": False,
        },
        "model_calls": 0,
        "network_requests": 0,
    }


def _rebuild_preparation(prepared, *, root, cases, settings, policy, registry,
                         saved_projection, notice_manifest, input_rate_usd_per_million,
                         output_rate_usd_per_million, allowance_usd, comparison_manifest,
                         record_directory, input_file_sha256):
    if not isinstance(prepared, dict):
        raise EvidenceCoordinatorError("prepared coordination must be an object")
    rebuilt = prepare_mock_coordination(
        root=root, cases=cases, settings=settings, policy=policy, registry=registry,
        saved_projection=saved_projection, notice_manifest=notice_manifest,
        input_rate_usd_per_million=input_rate_usd_per_million,
        output_rate_usd_per_million=output_rate_usd_per_million,
        allowance_usd=allowance_usd, comparison_manifest=comparison_manifest,
        record_directory=record_directory, input_file_sha256=input_file_sha256,
    )
    if not _canonical_equal(prepared, rebuilt):
        raise EvidenceCoordinatorError("prepared coordination failed exact regeneration")
    return rebuilt


def _validate_fixture_prompts(fixtures, prepared_requests):
    if not isinstance(fixtures, list):
        raise EvidenceCoordinatorError("fixtures must be an ordered list")
    requests = prepared_requests["prepared_requests"]
    if len(fixtures) > len(requests):
        raise EvidenceCoordinatorError("more fixtures were supplied than prepared requests")
    for index, fixture in enumerate(fixtures):
        if not isinstance(fixture, dict):
            raise EvidenceCoordinatorError(f"fixtures[{index}] must be an object")
        request = requests[index]
        if fixture.get("slot_id") != request["slot_id"]:
            raise EvidenceCoordinatorError("fixture order differs from prepared requests")
        if fixture.get("model_input_sha256") != request["model_input_sha256"]:
            raise EvidenceCoordinatorError("fixture model input differs from prepared request")
        if fixture.get("outcome_kind") != "diagnostic":
            continue
        diagnostic = fixture.get("payload")
        if not isinstance(diagnostic, dict):
            raise EvidenceCoordinatorError("diagnostic fixture payload must be an object")
        prompt_hash = diagnostic.get("prompt_token_ids_sha256")
        prompt_count = diagnostic.get("prompt_token_count")
        if prompt_hash != request["prompt_token_ids_sha256"]:
            raise EvidenceCoordinatorError("diagnostic prompt hash differs from prepared request")
        if type(prompt_count) is not int or prompt_count != request["exact_input_tokens"]:
            raise EvidenceCoordinatorError("diagnostic prompt count differs from prepared request")
        generated_count = diagnostic.get("generated_token_count")
        raw_generated = diagnostic.get("raw_generated_token_ids")
        if type(generated_count) is not int or not isinstance(raw_generated, list):
            raise EvidenceCoordinatorError("diagnostic generated-token inventory is invalid")
        if (generated_count > request["max_output_tokens"]
                or len(raw_generated) > request["max_output_tokens"]):
            raise EvidenceCoordinatorError("diagnostic exceeds prepared maximum output tokens")


def _add(left, right):
    with localcontext() as context:
        context.prec = 50
        return left + right


def _money(value):
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise EvidenceCoordinatorError("prepared reservation is not a Decimal string") from exc
    if not parsed.is_finite() or parsed < 0:
        raise EvidenceCoordinatorError("prepared reservation is invalid")
    return parsed


def _cost_accounting(prepared_requests, audit):
    requests = prepared_requests["prepared_requests"]
    outcomes = audit["slot_outcomes"]
    if len(requests) != len(outcomes):
        raise EvidenceCoordinatorError("request and accounting inventories differ")
    submitted_total = Decimal(0)
    released_total = Decimal(0)
    rows = []
    for request, outcome in zip(requests, outcomes, strict=True):
        if request["slot_id"] != outcome["slot_id"]:
            raise EvidenceCoordinatorError("request and accounting slot order differs")
        maximum = _money(request["worst_case_reservation_usd"])
        if outcome["submitted"]:
            submitted_total = _add(submitted_total, maximum)
            state = "submitted_maximum_reserved"
            submitted = maximum
            released = Decimal(0)
            attempts = 1
        else:
            released_total = _add(released_total, maximum)
            state = "unsubmitted_released"
            submitted = Decimal(0)
            released = maximum
            attempts = 0
        rows.append({
            "slot_id": request["slot_id"],
            "outcome": outcome["outcome"],
            "submitted": outcome["submitted"],
            "attempt_count": attempts,
            "reservation_state": state,
            "per_attempt_maximum_reservation_usd": format(maximum, "f"),
            "submitted_maximum_reservation_usd": format(submitted, "f"),
            "released_unsubmitted_reservation_usd": format(released, "f"),
        })
    planned_total = _add(submitted_total, released_total)
    declared_total = _money(prepared_requests["full_run_worst_case_reservation_usd"])
    if planned_total != declared_total:
        raise EvidenceCoordinatorError("per-slot reservations do not equal full-run reservation")
    return {
        "basis": "maximum_sampling_reservation_not_invoice",
        "pricing_status": prepared_requests["cost_basis"]["kind"],
        "currency": "USD",
        "retry_count": 0,
        "planned_full_run_maximum_reservation_usd": format(planned_total, "f"),
        "submitted_maximum_reservation_usd": format(submitted_total, "f"),
        "released_unsubmitted_reservation_usd": format(released_total, "f"),
        "invoice_reconciled": False,
        "invoice_cost_claimed": False,
        "slots": rows,
    }


def simulate_mock_collection(prepared, fixtures, *, root, cases, settings, policy, registry,
                             saved_projection, notice_manifest, input_rate_usd_per_million,
                             output_rate_usd_per_million, allowance_usd,
                             comparison_manifest=request_bridge.MANIFEST,
                             record_directory=None, input_file_sha256=None):
    """Regenerate current inputs, bind fixture prompts, and simulate stop-all collection."""
    current = _rebuild_preparation(
        prepared, root=root, cases=cases, settings=settings, policy=policy, registry=registry,
        saved_projection=saved_projection, notice_manifest=notice_manifest,
        input_rate_usd_per_million=input_rate_usd_per_million,
        output_rate_usd_per_million=output_rate_usd_per_million,
        allowance_usd=allowance_usd, comparison_manifest=comparison_manifest,
        record_directory=record_directory, input_file_sha256=input_file_sha256,
    )
    _validate_fixture_prompts(fixtures, current["prepared_requests"])
    try:
        native = native_bridge.simulate_sequential_collection(
            current["coordinated_plan"], fixtures,
        )
    except ValueError as exc:
        raise EvidenceCoordinatorError("native fixture collection failed") from exc
    return {
        "schema_version": SCHEMA_VERSION,
        "simulation_kind": SIMULATION_KIND,
        "prepared_coordination_sha256": canonical_sha256(current),
        "native_simulation": native,
        "cost_accounting": _cost_accounting(current["prepared_requests"], native["audit"]),
        "authorization": {
            "fixture_simulation_only": True,
            "generation_authorized": False,
            "training_authorized": False,
        },
        "model_calls": 0,
        "network_requests": 0,
    }


def verify_mock_collection(prepared, fixtures, record, **kwargs):
    """Regenerate the complete simulation and require exact finite-JSON equality."""
    rebuilt = simulate_mock_collection(prepared, fixtures, **kwargs)
    if not _canonical_equal(record, rebuilt):
        raise EvidenceCoordinatorError("mock collection failed exact regeneration")
    return {
        "audit": copy.deepcopy(record["native_simulation"]["audit"]),
        "cost_accounting": copy.deepcopy(record["cost_accounting"]),
    }
