"""Run the frozen 18-slot known-topic evidence pilot through retained Inkling B.

Preparation is offline.  Execution is a single sequential collection with an
explicit opt-in, exact source/request regeneration, durable pre-submit events,
native diagnostic sidecars, no application retry, and no training path.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import re

from bibleprep import chat_model
from bibleprep import evidence_collection as collection
from bibleprep import evidence_coordinator as coordinator
from bibleprep import evidence_native as native_bridge
from bibleprep import evaluate_adapter as adapter
from bibleprep import native_diagnostics_v1 as native_diagnostics
from bibleprep import tinker_evaluate
from bibleprep.evidence import ROOT, sha256, strict_load


SCHEMA_VERSION = 1
PROTOCOL_ID = "evidence-known-topic-pilot-v1"
MODEL = "thinkingmachines/Inkling"
INPUT_NAMES = frozenset({
    "cases", "settings", "policy", "registry", "saved_projection",
    "notice_manifest", "criteria", "criteria_review", "review_plan",
    "provider_preflight", "comparison_manifest",
})
REQUIRED_IMPLEMENTATION_FILES = frozenset({
    "bibleprep/evidence_pilot.py", "tests/test_evidence_pilot.py",
    "bibleprep/evidence_coordinator.py", "bibleprep/evidence_delivery.py",
    "bibleprep/evidence_eligibility.py", "bibleprep/evidence.py",
    "bibleprep/evaluate_evidence.py", "bibleprep/evidence_requests.py",
    "bibleprep/evidence_native.py", "bibleprep/evidence_collection.py",
    "bibleprep/native_diagnostics_v1.py", "bibleprep/tinker_compare.py",
    "bibleprep/tinker_evaluate.py", "bibleprep/evaluate.py",
    "bibleprep/evaluate_adapter.py", "bibleprep/chat_model.py",
})
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
PRICING_FILES = frozenset({"review", "snapshot"})


class EvidencePilotError(ValueError):
    """A frozen pilot input or live collection boundary failed closed."""


def _canonical_bytes(value):
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidencePilotError("pilot artifact must be finite JSON") from exc


def _canonical_sha256(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha(value, label):
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise EvidencePilotError(f"{label} must be a lowercase SHA-256")


def _identifier(value, label):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise EvidencePilotError(f"{label} must be a stable identifier")


def _strict_int(value, label, expected):
    if type(value) is not int or value != expected:
        raise EvidencePilotError(f"{label} must equal {expected}")


def _exact_keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise EvidencePilotError(f"{label} fields differ from the frozen schema")


def _confined_file(root, relative, label, *, allowed_roots=None):
    if not isinstance(relative, str):
        raise EvidencePilotError(f"{label}.path must be text")
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or str(raw) != relative:
        raise EvidencePilotError(f"{label}.path must be a portable project-relative path")
    path = (root / raw).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise EvidencePilotError(f"{label}.path escapes the project") from exc
    if allowed_roots and not any(path.is_relative_to((root / base).resolve()) for base in allowed_roots):
        raise EvidencePilotError(f"{label}.path is outside its allowed private/public roots")
    current = root
    for part in raw.parts:
        current = current / part
        if current.is_symlink():
            raise EvidencePilotError(f"{label}.path must not contain a symlink")
    if not path.is_file():
        raise EvidencePilotError(f"{label}.path is not a regular file")
    return path


def _load_bound_file(root, entry, label, *, allowed_roots=None):
    _exact_keys(entry, {"path", "sha256"}, label)
    _sha(entry["sha256"], label + ".sha256")
    path = _confined_file(root, entry["path"], label, allowed_roots=allowed_roots)
    if sha256(path) != entry["sha256"]:
        raise EvidencePilotError(f"{label} bytes differ from the frozen hash")
    try:
        value = strict_load(path)
    except (OSError, ValueError, TypeError) as exc:
        raise EvidencePilotError(f"{label} is not strict JSON") from exc
    return path, value


def _decimal(value, label):
    if not isinstance(value, str):
        raise EvidencePilotError(f"{label} must be an exact decimal string")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise EvidencePilotError(f"{label} is not decimal") from exc
    if not result.is_finite() or result <= 0 or format(result, "f") != value:
        raise EvidencePilotError(f"{label} must be a positive canonical decimal string")
    return result


def _utc(value, label):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidencePilotError(f"{label} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise EvidencePilotError(f"{label} must be UTC-aware")
    return parsed


def _now():
    return datetime.now(timezone.utc)


def _validate_criteria(cases, criteria):
    _exact_keys(criteria, {"schema_version", "suite_id", "fixture_kind", "cases"}, "criteria")
    _strict_int(criteria["schema_version"], "criteria.schema_version", 1)
    if criteria["suite_id"] != PROTOCOL_ID or criteria["fixture_kind"] != "constructed":
        raise EvidencePilotError("criteria identity differs from the frozen pilot")
    if not isinstance(cases.get("cases"), list) or not isinstance(criteria["cases"], list):
        raise EvidencePilotError("case inventories must be lists")
    if len(cases["cases"]) != 6 or len(criteria["cases"]) != 6:
        raise EvidencePilotError("pilot must contain exactly six cases")
    for source, rubric in zip(cases["cases"], criteria["cases"], strict=True):
        _exact_keys(
            rubric,
            {"case_id", "general_control", "question", "reviewer_instructions", "scoring_criteria"},
            "criteria.case",
        )
        if (rubric["case_id"] != source.get("case_id")
                or rubric["question"] != source.get("question")
                or rubric["general_control"] is not source.get("general_control")):
            raise EvidencePilotError("criteria do not exactly match case identity and question")
        if not isinstance(rubric["general_control"], bool):
            raise EvidencePilotError("criteria general_control must be boolean")
        for field in ("reviewer_instructions", "scoring_criteria"):
            if (not isinstance(rubric[field], list) or not rubric[field]
                    or any(not isinstance(item, str) or not item.strip() for item in rubric[field])):
                raise EvidencePilotError(f"criteria {field} must contain nonempty text")


def _validate_review_plan(review):
    expected = {
        "schema_version", "review_plan_id", "status", "study_role", "case_count",
        "bible_cases", "source_families", "general_controls", "planned_slot_count",
        "contrasts", "masking", "all_returned_finals_reviewed_including_partials",
        "collection_gate", "quality_gate", "reporting", "training_authorized",
        "promotion_authorized",
    }
    _exact_keys(review, expected, "review_plan")
    _strict_int(review["schema_version"], "review_plan.schema_version", 1)
    for key, value in (("case_count", 6), ("bible_cases", 4), ("source_families", 2),
                       ("general_controls", 2), ("planned_slot_count", 18)):
        _strict_int(review[key], "review_plan." + key, value)
    if (review["status"] != "frozen_before_generation"
            or review["study_role"] != "known_topic_development_pilot_not_fresh_benchmark"
            or review["all_returned_finals_reviewed_including_partials"] is not True
            or review["training_authorized"] is not False
            or review["promotion_authorized"] is not False):
        raise EvidencePilotError("review plan does not preserve the frozen pilot gates")


def _validate_criteria_review(review, hashes):
    required = {
        "schema_version", "review_id", "status", "protocol_id", "reviewer_kind",
        "expert_certification", "cases_file_sha256", "criteria_file_sha256",
        "registry_file_sha256", "notice_manifest_file_sha256", "limitations",
    }
    if not isinstance(review, dict) or not required <= set(review):
        raise EvidencePilotError("criteria review lacks required frozen fields")
    _strict_int(review["schema_version"], "criteria_review.schema_version", 1)
    _identifier(review["review_id"], "criteria_review.review_id")
    if (review["status"] != "accepted_for_known_topic_pilot"
            or review["protocol_id"] != PROTOCOL_ID
            or review["reviewer_kind"] != "ai"
            or review["expert_certification"] is not False):
        raise EvidencePilotError("criteria review does not close the frozen pre-generation review")
    for key in ("cases", "criteria", "registry", "notice_manifest"):
        if review[key + "_file_sha256"] != hashes[key]:
            raise EvidencePilotError(f"criteria review does not bind {key}")
    if (not isinstance(review["limitations"], list) or not review["limitations"]
            or any(not isinstance(item, str) or not item.strip() for item in review["limitations"])):
        raise EvidencePilotError("criteria review limitations must be retained")


def _validate_provider_preflight(value, checkpoint_file_sha, sampler_sha):
    expected = {
        "checked_at_utc", "status", "sampling_calls", "training_calls", "provider_mutations",
        "read_only_requests", "model", "is_lora", "lora_rank", "checkpoint_file_sha256",
        "sampler_path_sha256", "sampler_size_bytes", "expires_at_utc", "public",
    }
    _exact_keys(value, expected, "provider_preflight")
    for key, wanted in (("sampling_calls", 0), ("training_calls", 0),
                        ("provider_mutations", 0), ("read_only_requests", 2), ("lora_rank", 8)):
        _strict_int(value[key], "provider_preflight." + key, wanted)
    if (value["status"] != "passed" or value["model"] != MODEL
            or value["is_lora"] is not True or value["public"] is not False
            or value["checkpoint_file_sha256"] != checkpoint_file_sha
            or value["sampler_path_sha256"] != sampler_sha
            or type(value["sampler_size_bytes"]) is not int or value["sampler_size_bytes"] <= 0):
        raise EvidencePilotError("provider preflight does not identify retained private Inkling B")
    now = _now()
    checked = _utc(value["checked_at_utc"], "provider_preflight.checked_at_utc")
    if checked > now or (now - checked).total_seconds() > 24 * 60 * 60:
        raise EvidencePilotError("provider preflight is not current within 24 hours")
    if value["expires_at_utc"] is not None:
        expires = _utc(value["expires_at_utc"], "provider_preflight.expires_at_utc")
        if expires <= now:
            raise EvidencePilotError("retained B checkpoint is expired")


def _validate_pricing(root, pricing):
    required = {
        "currency", "rate_unit", "input_rate_usd_per_million",
        "output_rate_usd_per_million", "allowance_usd", "cache_discount_assumed",
        "verified_on", "files",
    }
    _exact_keys(pricing, required, "pricing")
    if (pricing["currency"] != "USD" or pricing["rate_unit"] != "per_1m_tokens"
            or pricing["input_rate_usd_per_million"] != "1.87"
            or pricing["output_rate_usd_per_million"] != "4.68"
            or pricing["allowance_usd"] != "2"
            or pricing["cache_discount_assumed"] is not False
            or pricing["verified_on"] != "2026-09-09"):
        raise EvidencePilotError("pilot pricing or allowance differs from the reviewed cap")
    _exact_keys(pricing["files"], PRICING_FILES, "pricing.files")
    review_path, review = _load_bound_file(
        root, pricing["files"]["review"], "pricing.files.review", allowed_roots=("runs",),
    )
    snapshot_path, snapshot = _load_bound_file(
        root, pricing["files"]["snapshot"], "pricing.files.snapshot", allowed_roots=("runs",),
    )
    if (review.get("model") != MODEL or review.get("input_usd_per_million") != "1.87"
            or review.get("output_usd_per_million") != "4.68"
            or review.get("cache_discount_assumed") is not False
            or review.get("invoice_reconciled") is not False
            or review.get("snapshot_sha256") != sha256(snapshot_path)):
        raise EvidencePilotError("pricing review does not bind the official snapshot and rates")
    checked = _utc(review.get("checked_at_utc"), "pricing_review.checked_at_utc")
    now = _now()
    if checked > now or (now - checked).total_seconds() > 24 * 60 * 60:
        raise EvidencePilotError("pricing review is not current within 24 hours")
    rows = [row for row in snapshot if isinstance(row, dict) and row.get("tinker_id") == MODEL]
    if len(rows) != 1 or rows[0].get("prefill") != "$1.87" or rows[0].get("sample") != "$4.68":
        raise EvidencePilotError("pricing snapshot does not contain the reviewed Inkling rates")
    return Decimal("1.87"), Decimal("4.68"), Decimal("2"), review_path


def _validate_implementation_files(root, mapping):
    if not isinstance(mapping, dict) or not REQUIRED_IMPLEMENTATION_FILES <= set(mapping):
        raise EvidencePilotError("implementation_files omits a pilot engine dependency")
    for relative, expected in mapping.items():
        _sha(expected, "implementation_files hash")
        path = _confined_file(root, relative, "implementation_files", allowed_roots=("bibleprep", "tests", "runs"))
        if sha256(path) != expected:
            raise EvidencePilotError(f"implementation file changed: {relative}")
    return _canonical_sha256(mapping)


def _verify_checkpoint(root, checkpoint):
    expected = {
        "checkpoint_id", "state", "model", "reference_file", "reference_file_sha256",
        "sampler_path_sha256",
    }
    _exact_keys(checkpoint, expected, "checkpoint")
    if (checkpoint["checkpoint_id"] != "retained-B-original-text-only"
            or checkpoint["state"] != "original_text_lora_adapter" or checkpoint["model"] != MODEL):
        raise EvidencePilotError("protocol checkpoint is not retained Inkling B")
    _sha(checkpoint["reference_file_sha256"], "checkpoint.reference_file_sha256")
    _sha(checkpoint["sampler_path_sha256"], "checkpoint.sampler_path_sha256")
    path = _confined_file(root, checkpoint["reference_file"], "checkpoint", allowed_roots=("runs",))
    if sha256(path) != checkpoint["reference_file_sha256"]:
        raise EvidencePilotError("checkpoint receipt bytes changed")
    try:
        resolved = chat_model.resolve_b_checkpoint(root, path)
        sampler, receipt_sha = adapter.checkpoint_identity(path)
    except Exception as exc:
        raise EvidencePilotError("retained B provenance verification failed") from exc
    sampler_sha = hashlib.sha256(sampler.encode("utf-8")).hexdigest()
    if resolved != sampler or receipt_sha != checkpoint["reference_file_sha256"]:
        raise EvidencePilotError("checkpoint helpers disagree on retained B identity")
    if sampler_sha != checkpoint["sampler_path_sha256"]:
        raise EvidencePilotError("retained B sampler identity changed")
    return path, sampler, sampler_sha


def _validate_protocol(protocol):
    expected = {
        "schema_version", "protocol_id", "status", "study_role", "case_count",
        "planned_slot_count", "run_directory", "input_files", "implementation_files",
        "checkpoint", "sampling", "pricing", "execution", "training_authorized",
        "promotion_authorized",
    }
    _exact_keys(protocol, expected, "protocol")
    _strict_int(protocol["schema_version"], "protocol.schema_version", 1)
    if (protocol["protocol_id"] != PROTOCOL_ID
            or protocol["status"] != "frozen_authorized_single_run"
            or protocol["study_role"] != "known_topic_development_pilot_not_fresh_benchmark"):
        raise EvidencePilotError("protocol identity or status differs from the accepted pilot")
    _strict_int(protocol["case_count"], "protocol.case_count", 6)
    _strict_int(protocol["planned_slot_count"], "protocol.planned_slot_count", 18)
    if protocol["run_directory"] != "runs/evidence-pilot-v1/live":
        raise EvidencePilotError("protocol run directory changed")
    if protocol["training_authorized"] is not False or protocol["promotion_authorized"] is not False:
        raise EvidencePilotError("pilot cannot authorize training or promotion")
    _exact_keys(protocol["input_files"], INPUT_NAMES, "protocol.input_files")
    sampling = protocol["sampling"]
    _exact_keys(sampling, {
        "model", "effort", "reasoning_effort", "temperature", "seed",
        "max_input_tokens", "max_output_tokens", "timeout_seconds",
    }, "protocol.sampling")
    if (sampling["model"] != MODEL or type(sampling["effort"]) is not float
            or sampling["effort"] != 0.7 or sampling["reasoning_effort"] != "medium"
            or type(sampling["temperature"]) is not float or sampling["temperature"] != 0.0):
        raise EvidencePilotError("pilot model or sampling values changed")
    for key, wanted in (("seed", 1702), ("max_input_tokens", 8192),
                        ("max_output_tokens", 8192), ("timeout_seconds", 300)):
        _strict_int(sampling[key], "protocol.sampling." + key, wanted)
    execution = protocol["execution"]
    _exact_keys(execution, {
        "authorization", "authorized_on", "execute_opt_in_required", "sequential",
        "automatic_retry", "max_attempts", "stop_rule",
    }, "protocol.execution")
    if (execution["authorization"] != "continuing_owner_project_authorization_with_operator_cap"
            or execution["authorized_on"] != "2026-09-09"
            or execution["execute_opt_in_required"] is not True
            or execution["sequential"] is not True
            or execution["automatic_retry"] is not False
            or execution["stop_rule"] != "stop_after_uncertain_or_incomplete"):
        raise EvidencePilotError("execution controls differ from the accepted one-pass pilot")
    _strict_int(execution["max_attempts"], "protocol.execution.max_attempts", 18)


def _load_context(protocol_file, protocol_sha256, root):
    root = Path(root).resolve()
    supplied = Path(protocol_file)
    try:
        relative = str(supplied.resolve().relative_to(root)) if supplied.is_absolute() else str(supplied)
    except ValueError as exc:
        raise EvidencePilotError("protocol path escapes the project") from exc
    protocol_path = _confined_file(root, relative, "protocol", allowed_roots=("runs",))
    _sha(protocol_sha256, "protocol_sha256")
    if sha256(protocol_path) != protocol_sha256:
        raise EvidencePilotError("protocol bytes differ from the explicit frozen hash")
    try:
        protocol = strict_load(protocol_path)
    except (OSError, ValueError, TypeError) as exc:
        raise EvidencePilotError("protocol is not strict JSON") from exc
    _validate_protocol(protocol)
    implementation_sha = _validate_implementation_files(root, protocol["implementation_files"])
    inputs = {}
    paths = {}
    hashes = {}
    for name, entry in protocol["input_files"].items():
        allowed = ("manifests",) if name == "comparison_manifest" else ("data/evidence", "runs")
        paths[name], inputs[name] = _load_bound_file(root, entry, "input_files." + name, allowed_roots=allowed)
        hashes[name] = entry["sha256"]
    _validate_criteria(inputs["cases"], inputs["criteria"])
    _validate_review_plan(inputs["review_plan"])
    _validate_criteria_review(inputs["criteria_review"], hashes)
    input_rate, output_rate, allowance, _ = _validate_pricing(root, protocol["pricing"])
    checkpoint_path, sampler, sampler_sha = _verify_checkpoint(root, protocol["checkpoint"])
    _validate_provider_preflight(
        inputs["provider_preflight"], protocol["checkpoint"]["reference_file_sha256"], sampler_sha,
    )
    settings = inputs["settings"]
    expected_sampling = {
        "effort": 0.7, "temperature": 0.0, "seed": 1702, "max_tokens": 8192,
        "input_token_limit": 8192, "deadline_seconds": 300,
    }
    if (settings.get("sampling") != expected_sampling
            or settings.get("stop_rule") != "stop_after_uncertain_or_incomplete"
            or settings.get("request_order") != "case_then_arm"
            or settings.get("checkpoint_id") != "retained-B-original-text-only"):
        raise EvidencePilotError("settings file differs from protocol sampling and checkpoint")
    base_hashes = {
        "cases": hashes["cases"], "settings": hashes["settings"], "policy": hashes["policy"],
        "registry": hashes["registry"], "projection": hashes["saved_projection"],
    }
    try:
        prepared = _build_preparation(
            root=root, cases=inputs["cases"], settings=settings, policy=inputs["policy"],
            registry=inputs["registry"], saved_projection=inputs["saved_projection"],
            notice_manifest=inputs["notice_manifest"], input_rate=input_rate,
            output_rate=output_rate, allowance=allowance,
            comparison_manifest=paths["comparison_manifest"], input_file_sha256=base_hashes,
        )
    except ValueError as exc:
        raise EvidencePilotError("current source closure or exact request regeneration failed") from exc
    if (prepared.get("coordinated_plan", {}).get("planned_slot_count") != 18
            or prepared.get("prepared_requests", {}).get("planned_slot_count") != 18):
        raise EvidencePilotError("prepared pilot does not contain all 18 slots")
    expected_cost = Decimal("0.9658368")
    if Decimal(prepared["prepared_requests"]["full_run_worst_case_reservation_usd"]) != expected_cost:
        raise EvidencePilotError("prepared worst-case reservation differs from the fixed pilot")
    return {
        "root": root, "protocol_path": protocol_path, "protocol": protocol,
        "protocol_sha256": protocol_sha256, "inputs": inputs, "paths": paths,
        "input_hashes": hashes, "implementation_files_sha256": implementation_sha,
        "prepared": prepared, "prepared_sha256": _canonical_sha256(prepared),
        "checkpoint_path": checkpoint_path, "sampler": sampler,
        "input_rate": input_rate, "output_rate": output_rate, "allowance": allowance,
    }


def _build_preparation(**kwargs):
    """Private mock seam; production always calls the exact existing coordinator."""
    return coordinator.prepare_mock_coordination(
        root=kwargs["root"], cases=kwargs["cases"], settings=kwargs["settings"],
        policy=kwargs["policy"], registry=kwargs["registry"],
        saved_projection=kwargs["saved_projection"], notice_manifest=kwargs["notice_manifest"],
        input_rate_usd_per_million=kwargs["input_rate"],
        output_rate_usd_per_million=kwargs["output_rate"], allowance_usd=kwargs["allowance"],
        comparison_manifest=kwargs["comparison_manifest"], input_file_sha256=kwargs["input_file_sha256"],
    )


def prepare_known_topic_pilot(protocol_file, protocol_sha256, *, root=ROOT):
    """Regenerate all frozen inputs, source delivery, tokens, identity, and cost offline."""
    context = _load_context(protocol_file, protocol_sha256, root)
    requests = context["prepared"]["prepared_requests"]
    return {
        "schema_version": SCHEMA_VERSION,
        "pilot_kind": "known_topic_development_pilot_preparation_v1",
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": protocol_sha256,
        "prepared_coordination_sha256": context["prepared_sha256"],
        "planned_slots_sha256": requests["planned_slots_sha256"],
        "planned_slot_count": requests["planned_slot_count"],
        "full_run_worst_case_reservation_usd": requests["full_run_worst_case_reservation_usd"],
        "allowance_usd": format(context["allowance"], "f"),
        "checkpoint_reference_sha256": context["protocol"]["checkpoint"]["reference_file_sha256"],
        "sampler_path_sha256": context["protocol"]["checkpoint"]["sampler_path_sha256"],
        "implementation_files_sha256": context["implementation_files_sha256"],
        "exact_request_records": copy.deepcopy(requests["prepared_requests"]),
        "execution_ready_for_explicit_opt_in": True,
        "generation_performed": False,
        "training_authorized": False,
    }


def _load_secret(root):
    """Runtime-only credential seam; never called by offline preparation."""
    from bibleprep.environment import load_project_environment
    load_project_environment()
    secret = os.environ.get("TINKER_API_KEY", "").strip()
    if not secret:
        raise EvidencePilotError("sampling credential is unavailable")
    return secret


def _make_transport():
    """The only production transport: bounded native retained-adapter diagnostics."""
    return tinker_evaluate.BoundedNativeTransport(worker=native_diagnostics.sampling_worker)


def _normalize_response(response, run_dir):
    return native_bridge.normalize_native_response(response, run_dir)


def _write_exclusive(path, value):
    raw = _canonical_bytes(value) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(raw).hexdigest()


def _append_event(path, value):
    raw = _canonical_bytes(value) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "ab") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _create_empty_journal(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _read_events(path):
    try:
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                def pairs(items):
                    result = {}
                    for key, value in items:
                        if key in result:
                            raise ValueError("duplicate key")
                        result[key] = value
                    return result
                events.append(json.loads(
                    line, object_pairs_hook=pairs,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
                ))
        return events
    except (OSError, ValueError, TypeError) as exc:
        raise EvidencePilotError("pilot journal is malformed") from exc


def _transport_config(context, run_dir):
    sampling = context["protocol"]["sampling"]
    return {
        "base_url": tinker_evaluate.TINKER_URL, "model": MODEL,
        "run_dir": str(run_dir), "max_cases": 18,
        "max_input_tokens": sampling["max_input_tokens"],
        "max_output_tokens": sampling["max_output_tokens"],
        "timeout_seconds": sampling["timeout_seconds"],
        "input_price_per_million": float(context["input_rate"]),
        "output_price_per_million": float(context["output_rate"]),
        "budget_usd": float(context["allowance"]),
        "reasoning_effort": sampling["reasoning_effort"],
        "temperature": sampling["temperature"], "seed": sampling["seed"],
        "prompt_date": context["protocol"]["execution"]["authorized_on"],
        "comparison_manifest": str(context["paths"]["comparison_manifest"].relative_to(context["root"])),
        "adapter_sampler_path": context["sampler"],
        "checkpoint_reference_file": str(context["checkpoint_path"]),
        "checkpoint_reference_sha256": context["protocol"]["checkpoint"]["reference_file_sha256"],
    }


def _validate_native_result(response, normalized, request):
    try:
        usage = response["usage"]
        prompt_count = usage["prompt_tokens"]
        output_count = usage["completion_tokens"]
        prompt_sha = response["native_tinker"]["prompt_sha256"]
    except (KeyError, TypeError) as exc:
        raise EvidencePilotError("native response lacks exact token accounting") from exc
    if (type(prompt_count) is not int or prompt_count != request["exact_input_tokens"]
            or prompt_sha != request["prompt_token_ids_sha256"]
            or normalized.get("native_prompt_sha256") != request["prompt_token_ids_sha256"]):
        raise EvidencePilotError("native response prompt differs from the prepared request")
    if type(output_count) is not int or not 0 <= output_count <= request["max_output_tokens"]:
        raise EvidencePilotError("native output exceeds its prepared reservation")
    if response.get("model") != MODEL:
        raise EvidencePilotError("native response identifies a different base model")
    return prompt_count, output_count


def _receipt_binding(context, request, normalized, prompt_count, output_count):
    final_text = normalized["final_text"]
    return {
        "schema_version": SCHEMA_VERSION, "protocol_sha256": context["protocol_sha256"],
        "prepared_coordination_sha256": context["prepared_sha256"],
        "planned_slots_sha256": context["prepared"]["prepared_requests"]["planned_slots_sha256"],
        "slot_id": request["slot_id"], "slot_sha256": request["slot_sha256"],
        "model_input_sha256": request["model_input_sha256"],
        "request_sha256": _canonical_sha256(request), "payload_sha256": request["payload_sha256"],
        "prompt_token_ids_sha256": request["prompt_token_ids_sha256"],
        "prompt_token_count": prompt_count, "output_token_count": output_count,
        "max_output_tokens": request["max_output_tokens"],
        "diagnostic_sha256": normalized["diagnostic_sha256"],
        "raw_generated_token_ids_sha256": normalized["raw_generated_token_ids_sha256"],
        "stop_reason": normalized["stop_reason"],
        "final_text_sha256": hashlib.sha256(final_text.encode("utf-8")).hexdigest(),
        "checkpoint_reference_sha256": context["protocol"]["checkpoint"]["reference_file_sha256"],
        "sampler_path_sha256": context["protocol"]["checkpoint"]["sampler_path_sha256"],
        "implementation_files_sha256": context["implementation_files_sha256"],
        "criteria_file_sha256": context["input_hashes"]["criteria"],
        "criteria_review_file_sha256": context["input_hashes"]["criteria_review"],
        "review_plan_file_sha256": context["input_hashes"]["review_plan"],
    }


def _same_preparation(left, right):
    return _canonical_sha256(left) == _canonical_sha256(right)


def _summary(context, journal, local_stop_reason):
    plan = context["prepared"]["coordinated_plan"]
    audit = collection.audit_collection(plan["planned_slots"], journal)
    audit["limitations"] = [
        "Terminal results are normalized from receipt-verified native diagnostic sidecars; the accounting auditor does not itself parse native output.",
        "The pilot verifier independently checks every result receipt, prompt binding, final text, and stop reason.",
        *audit["limitations"][2:],
    ]
    costs = coordinator._cost_accounting(context["prepared"]["prepared_requests"], audit)
    return {
        "schema_version": SCHEMA_VERSION, "pilot_kind": "known_topic_development_pilot_run_v1",
        "protocol_sha256": context["protocol_sha256"],
        "prepared_coordination_sha256": context["prepared_sha256"],
        "journal_sha256": collection.canonical_sha256(journal),
        "audit": audit, "cost_accounting": costs,
        "local_stop_reason": local_stop_reason,
        "collection_complete": audit["collection_evidence"]["all_planned_complete"],
        "quality_review_complete": False, "model_or_feature_promotion_authorized": False,
        "training_authorized": False,
    }


def run_known_topic_pilot(protocol_file, protocol_sha256, *, execute=False, root=ROOT):
    """Execute the exact one-pass pilot; ``execute=True`` is the required opt-in."""
    if not isinstance(execute, bool):
        raise EvidencePilotError("execute must be boolean")
    if not execute:
        return prepare_known_topic_pilot(protocol_file, protocol_sha256, root=root)
    context = _load_context(protocol_file, protocol_sha256, root)
    raw_run_dir = context["root"] / context["protocol"]["run_directory"]
    current = context["root"]
    for part in Path(context["protocol"]["run_directory"]).parts:
        current = current / part
        if current.is_symlink():
            raise EvidencePilotError("pilot run path must not contain symlinks")
    run_dir = raw_run_dir.resolve()
    if run_dir.exists():
        raise EvidencePilotError("pilot run directory already exists; automatic resume is forbidden")
    run_dir.mkdir(mode=0o700, parents=False)
    os.chmod(run_dir, 0o700)
    receipts_dir = run_dir / "receipts"
    receipts_dir.mkdir(mode=0o700)
    manifest = {
        "schema_version": SCHEMA_VERSION, "protocol_sha256": protocol_sha256,
        "prepared_coordination_sha256": context["prepared_sha256"],
        "planned_slots_sha256": context["prepared"]["prepared_requests"]["planned_slots_sha256"],
        "planned_slot_count": 18, "implementation_files_sha256": context["implementation_files_sha256"],
        "checkpoint_reference_sha256": context["protocol"]["checkpoint"]["reference_file_sha256"],
        "sampler_path_sha256": context["protocol"]["checkpoint"]["sampler_path_sha256"],
        "created_at_utc": _now().isoformat(), "automatic_retry": False,
        "training_authorized": False,
    }
    journal_path = run_dir / "events.jsonl"
    _write_exclusive(run_dir / "manifest.json", manifest)
    _create_empty_journal(journal_path)
    local_stop_reason = None
    transport = None
    secret = ""
    try:
        try:
            secret = _load_secret(context["root"])
            transport = _make_transport()
        except Exception:
            local_stop_reason = "pre_submission_setup_failed"
        original = context["prepared"]
        for index in range(18) if local_stop_reason is None else ():
            try:
                current = _load_context(protocol_file, protocol_sha256, root)
                if not _same_preparation(original, current["prepared"]):
                    raise EvidencePilotError("prepared pilot changed before submission")
                request = current["prepared"]["prepared_requests"]["prepared_requests"][index]
                _validate_implementation_files(current["root"], current["protocol"]["implementation_files"])
            except Exception:
                local_stop_reason = "pre_submission_verification_failed"
                break
            _append_event(journal_path, {"event": "submission", "slot_id": request["slot_id"]})
            try:
                response = transport(request["payload"], _transport_config(current, run_dir), secret)
                normalized = _normalize_response(response, run_dir)
                prompt_count, output_count = _validate_native_result(response, normalized, request)
                binding = _receipt_binding(current, request, normalized, prompt_count, output_count)
                receipt_sha = _canonical_sha256(binding)
                _write_exclusive(
                    receipts_dir / f"{index:02d}-{request['slot_id']}.json",
                    {"receipt_sha256": receipt_sha, "binding": binding, "response": response},
                )
                event = {
                    "event": "result", "slot_id": request["slot_id"],
                    "stop_reason": normalized["stop_reason"], "final_text": normalized["final_text"],
                    "receipt_sha256": receipt_sha,
                }
                _append_event(journal_path, event)
                if normalized["stop_reason"] != "stop" or not normalized["final_text"].strip():
                    break
            except Exception:
                _append_event(journal_path, {
                    "event": "failure", "slot_id": request["slot_id"],
                    "disposition": "uncertain", "receipt_sha256": None,
                })
                break
    finally:
        try:
            if transport is not None:
                transport.close()
        except Exception:
            pass
        secret = ""
    journal = _read_events(journal_path)
    summary = _summary(context, journal, local_stop_reason)
    _write_exclusive(run_dir / "summary.json", summary)
    return summary


def verify_pilot_run(protocol_file, protocol_sha256, *, root=ROOT):
    """Rebuild current closure and verify the private journal, receipts, and sidecars."""
    context = _load_context(protocol_file, protocol_sha256, root)
    run_dir = (context["root"] / context["protocol"]["run_directory"]).resolve()
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise EvidencePilotError("pilot run directory is unavailable")
    manifest = strict_load(run_dir / "manifest.json")
    if (manifest.get("protocol_sha256") != protocol_sha256
            or manifest.get("prepared_coordination_sha256") != context["prepared_sha256"]
            or manifest.get("implementation_files_sha256") != context["implementation_files_sha256"]
            or manifest.get("training_authorized") is not False
            or manifest.get("automatic_retry") is not False):
        raise EvidencePilotError("pilot manifest differs from current frozen inputs")
    journal = _read_events(run_dir / "events.jsonl")
    plan = context["prepared"]["coordinated_plan"]
    audit = collection.audit_collection(plan["planned_slots"], journal)
    requests = {item["slot_id"]: item for item in context["prepared"]["prepared_requests"]["prepared_requests"]}
    receipt_files = sorted((run_dir / "receipts").glob("*.json"))
    result_events = [event for event in journal if event["event"] == "result"]
    if len(receipt_files) != len(result_events):
        raise EvidencePilotError("receipt inventory differs from returned results")
    receipts = {}
    for path in receipt_files:
        if path.is_symlink():
            raise EvidencePilotError("pilot receipt must not be a symlink")
        record = strict_load(path)
        _exact_keys(record, {"receipt_sha256", "binding", "response"}, "receipt")
        if _canonical_sha256(record["binding"]) != record["receipt_sha256"]:
            raise EvidencePilotError("pilot receipt binding hash mismatch")
        slot_id = record["binding"].get("slot_id")
        if slot_id in receipts or slot_id not in requests:
            raise EvidencePilotError("pilot receipt slot inventory is invalid")
        normalized = _normalize_response(record["response"], run_dir)
        prompt_count, output_count = _validate_native_result(record["response"], normalized, requests[slot_id])
        expected = _receipt_binding(context, requests[slot_id], normalized, prompt_count, output_count)
        if not _same_preparation(expected, record["binding"]):
            raise EvidencePilotError("pilot receipt failed exact regeneration")
        receipts[slot_id] = record["receipt_sha256"]
    if any(receipts.get(event["slot_id"]) != event["receipt_sha256"] for event in result_events):
        raise EvidencePilotError("journal result is not bound to its native receipt")
    by_slot = {
        record["binding"]["slot_id"]: _normalize_response(record["response"], run_dir)
        for record in (strict_load(path) for path in receipt_files)
    }
    if any(
        event["final_text"] != by_slot[event["slot_id"]]["final_text"]
        or event["stop_reason"] != by_slot[event["slot_id"]]["stop_reason"]
        for event in result_events
    ):
        raise EvidencePilotError("journal terminal facts differ from the native receipt")
    saved_summary = strict_load(run_dir / "summary.json")
    expected_summary = _summary(context, journal, saved_summary.get("local_stop_reason"))
    if not _same_preparation(saved_summary, expected_summary):
        raise EvidencePilotError("pilot summary failed exact regeneration")
    return {"audit": expected_summary["audit"], "cost_accounting": expected_summary["cost_accounting"]}
