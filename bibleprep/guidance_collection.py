"""Prepare and collect a private two-condition native guidance comparison.

Preparation is offline and regenerates every supplied comparison pair. Collection
requires explicit execution opt-in, a caller-supplied credential, and a new private
run directory. It has no training, retry, resume, review, or protocol-authoring path.
"""
from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import re

from bibleprep import evidence_native
from bibleprep import evidence_requests
from bibleprep import native_diagnostics_v1 as native_diagnostics
from bibleprep import tinker_compare
from bibleprep import tinker_evaluate
from bibleprep.evidence import ROOT
from bibleprep.evidence_guidance_comparison import (
    CONDITION_IDS,
    verify_comparison_pair,
)


SCHEMA_VERSION = 1
PREPARATION_KIND = "offline_guidance_native_requests_v1"
COLLECTION_KIND = "private_guidance_sequential_collection_v1"
MODEL = "thinkingmachines/Inkling"
CONDITIONS = tuple(CONDITION_IDS)
CONTEXT_WINDOW_TOKENS = 65_536
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
SAMPLER_RE = re.compile(r"tinker://[A-Za-z0-9._:/-]+\Z")
SYNTHETIC_SAMPLER_RE = re.compile(r"synthetic://[A-Za-z0-9._:/-]+\Z")


class GuidanceCollectionError(ValueError):
    """A two-condition request or collection boundary failed closed."""


def _canonical_bytes(value):
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GuidanceCollectionError("artifact must be finite JSON") from exc


def canonical_sha256(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _text_sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_sha(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except (OSError, TypeError) as exc:
        raise GuidanceCollectionError("bound file could not be read") from exc


def _exact_keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise GuidanceCollectionError(f"{label} fields differ from schema")


def _identifier(value, label):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise GuidanceCollectionError(f"{label} must be a stable identifier")


def _sha(value, label):
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise GuidanceCollectionError(f"{label} must be a lowercase SHA-256")


def _decimal(value, label, *, positive=False):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise GuidanceCollectionError(f"{label} must be an explicit finite Decimal")
    if value < 0 or (positive and value <= 0) or value > Decimal("1000000"):
        raise GuidanceCollectionError(f"{label} is outside the bounded range")
    if len(value.as_tuple().digits) > 18 or abs(value.as_tuple().exponent) > 12:
        raise GuidanceCollectionError(f"{label} has excessive precision")
    return value


def _decimal_text(value):
    return format(value, "f")


def _cost(input_tokens, output_tokens, input_rate, output_rate):
    with localcontext() as context:
        context.prec = 50
        return (
            Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
        ) / Decimal(1_000_000)


def _settings(value):
    _exact_keys(value, {
        "deadline_seconds", "effort", "input_token_limit", "max_tokens", "prompt_date",
        "reasoning_effort", "seed", "temperature",
    }, "settings")
    for key in ("effort", "temperature", "deadline_seconds"):
        number = value[key]
        if not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(number):
            raise GuidanceCollectionError(f"settings.{key} must be finite")
    if not 0 <= value["effort"] < 1 or not 0 <= value["temperature"] <= 2:
        raise GuidanceCollectionError("effort or temperature is outside the supported range")
    if not 0 < value["deadline_seconds"] <= 300:
        raise GuidanceCollectionError("deadline_seconds is outside the supported range")
    if value["reasoning_effort"] not in {"low", "medium", "high"}:
        raise GuidanceCollectionError("reasoning_effort is unsupported")
    if value["effort"] != tinker_compare.TML_EFFORT[value["reasoning_effort"]]:
        raise GuidanceCollectionError("numeric effort differs from native reasoning_effort")
    for key, minimum, maximum in (
        ("seed", 0, 2**31 - 1),
        ("input_token_limit", 1, CONTEXT_WINDOW_TOKENS),
        ("max_tokens", 1, CONTEXT_WINDOW_TOKENS),
    ):
        if type(value[key]) is not int or not minimum <= value[key] <= maximum:
            raise GuidanceCollectionError(f"settings.{key} is outside the supported range")
    if value["input_token_limit"] + value["max_tokens"] > CONTEXT_WINDOW_TOKENS:
        raise GuidanceCollectionError("declared input and output limits exceed model context")
    try:
        date.fromisoformat(value["prompt_date"])
    except (TypeError, ValueError) as exc:
        raise GuidanceCollectionError("settings.prompt_date must be YYYY-MM-DD") from exc
    return copy.deepcopy(value)


def _portable_file(root, relative, label):
    if not isinstance(relative, str):
        raise GuidanceCollectionError(f"{label} must be project-relative text")
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or str(raw) != relative:
        raise GuidanceCollectionError(f"{label} must be a portable project-relative path")
    current = root
    for part in raw.parts:
        current = current / part
        if current.is_symlink():
            raise GuidanceCollectionError(f"{label} must not contain a symlink")
    path = (root / raw).resolve()
    try:
        path.relative_to((root / "runs").resolve())
    except ValueError as exc:
        raise GuidanceCollectionError(f"{label} must stay under private runs") from exc
    if not path.is_file():
        raise GuidanceCollectionError(f"{label} is unavailable")
    return path


def _model_reference(value, root, *, allow_synthetic):
    _exact_keys(value, {
        "adapter_sampler_path", "checkpoint_id", "checkpoint_reference_file",
        "checkpoint_reference_sha256", "model", "sampler_path_sha256", "state",
    }, "model_reference")
    if value["model"] != MODEL or value["state"] != "original_text_lora_adapter":
        raise GuidanceCollectionError("model reference must identify retained Inkling adapter B")
    _identifier(value["checkpoint_id"], "model_reference.checkpoint_id")
    _sha(value["checkpoint_reference_sha256"], "model_reference.checkpoint_reference_sha256")
    _sha(value["sampler_path_sha256"], "model_reference.sampler_path_sha256")
    sampler = value["adapter_sampler_path"]
    allowed = isinstance(sampler, str) and (
        SAMPLER_RE.fullmatch(sampler)
        or (allow_synthetic and SYNTHETIC_SAMPLER_RE.fullmatch(sampler))
    )
    if not allowed:
        raise GuidanceCollectionError("model_reference.adapter_sampler_path is invalid")
    path = _portable_file(root, value["checkpoint_reference_file"], "checkpoint_reference_file")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != value["checkpoint_reference_sha256"]:
        raise GuidanceCollectionError("checkpoint reference file hash differs")
    try:
        checkpoint = json.loads(raw)
        if checkpoint["sampler_path"] != value["adapter_sampler_path"]:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise GuidanceCollectionError("checkpoint reference does not identify the selected sampler") from exc
    if _text_sha256(value["adapter_sampler_path"]) != value["sampler_path_sha256"]:
        raise GuidanceCollectionError("sampler path hash differs")
    return copy.deepcopy(value)


def _protocol_bindings(value):
    _exact_keys(value, {
        "criteria_sha256", "protocol_sha256", "review_plan_sha256",
    }, "protocol_bindings")
    for key in value:
        _sha(value[key], "protocol_bindings." + key)
    return copy.deepcopy(value)


def _case_pairs(case_specs):
    if not isinstance(case_specs, (list, tuple)) or not case_specs or len(case_specs) > 1000:
        raise GuidanceCollectionError("case_specs must be a bounded nonempty sequence")
    pairs = []
    seen = set()
    common = None
    for index, spec in enumerate(case_specs):
        _exact_keys(spec, {"pair_inputs", "prepared_pair"}, f"case_specs[{index}]")
        inputs = spec["pair_inputs"]
        if not isinstance(inputs, dict):
            raise GuidanceCollectionError(f"case_specs[{index}].pair_inputs must be an object")
        try:
            pair = verify_comparison_pair(spec["prepared_pair"], **inputs)
        except (TypeError, ValueError) as exc:
            raise GuidanceCollectionError(f"case_specs[{index}] failed exact pair regeneration") from exc
        case_id = pair.get("case_id")
        _identifier(case_id, f"case_specs[{index}].case_id")
        if case_id in seen:
            raise GuidanceCollectionError("case IDs must be unique")
        seen.add(case_id)
        if pair.get("condition_order") != list(CONDITIONS) or set(pair.get("conditions", {})) != set(CONDITIONS):
            raise GuidanceCollectionError("pair must contain exactly B-original and B-guided")
        if not isinstance(pair.get("general_control"), bool):
            raise GuidanceCollectionError("pair general_control must be boolean")
        binding = pair.get("pair_bindings")
        if not isinstance(binding, dict):
            raise GuidanceCollectionError("pair bindings are missing")
        shared = {
            key: binding.get(key) for key in (
                "registry_sha256", "notice_manifest_sha256", "guidance_version",
                "guidance_sha256", "comparison_module_sha256",
                "answer_context_module_sha256", "delivery_module_sha256",
            )
        }
        prior = common if common is not None else shared
        if prior != shared:
            raise GuidanceCollectionError("cases do not share one source/notice/guidance/code closure")
        common = prior
        pairs.append(copy.deepcopy(pair))
    return pairs, common


def _load_renderer(comparison_manifest):
    return evidence_requests._PinnedRenderer(comparison_manifest)


def prepare_native_requests(
    case_specs, *, model_reference, protocol_bindings, settings, input_rate_usd_per_million,
    output_rate_usd_per_million, allowance_usd,
    comparison_manifest=evidence_requests.MANIFEST, renderer=None, root=ROOT,
):
    """Regenerate all pairs and prepare an interleaved two-condition inventory."""
    root = Path(root).resolve()
    pairs, common_bindings = _case_pairs(case_specs)
    model_ref = _model_reference(model_reference, root, allow_synthetic=renderer is not None)
    protocol = _protocol_bindings(protocol_bindings)
    sampling = _settings(settings)
    input_rate = _decimal(input_rate_usd_per_million, "input_rate_usd_per_million")
    output_rate = _decimal(output_rate_usd_per_million, "output_rate_usd_per_million")
    allowance = _decimal(allowance_usd, "allowance_usd", positive=True)
    settings_sha = canonical_sha256(sampling)
    model_sha = canonical_sha256(model_ref)
    per_slot_reservation = _cost(
        sampling["input_token_limit"], sampling["max_tokens"], input_rate, output_rate,
    )
    with localcontext() as context:
        context.prec = 50
        full_reservation = per_slot_reservation * Decimal(len(pairs) * 2)
    if full_reservation > allowance:
        raise GuidanceCollectionError("allowance is below the full-run worst-case reservation")
    active_renderer = _load_renderer(comparison_manifest) if renderer is None else renderer
    provenance = getattr(active_renderer, "provenance", None)
    if not isinstance(provenance, dict):
        raise GuidanceCollectionError("renderer provenance is unavailable")

    slots = []
    requests = []
    exact_estimate = Decimal(0)
    for case_index, pair in enumerate(pairs):
        order = CONDITIONS if case_index % 2 == 0 else tuple(reversed(CONDITIONS))
        for condition_id in order:
            condition = pair["conditions"][condition_id]
            model_input = condition["model_input"]
            messages = evidence_requests._messages(model_input)
            payload = {"messages": messages}
            try:
                tokens = list(active_renderer.render(messages, sampling["effort"]))
                prompt_sha = native_diagnostics.token_ids_sha256(tokens)
            except Exception as exc:
                raise GuidanceCollectionError("native request rendering failed") from exc
            if len(tokens) > sampling["input_token_limit"]:
                raise GuidanceCollectionError("exact native prompt exceeds input limit")
            if len(tokens) + sampling["max_tokens"] > CONTEXT_WINDOW_TOKENS:
                raise GuidanceCollectionError("exact native prompt plus output cap exceeds context")
            slot_id = pair["case_id"] + "--" + condition_id.lower()
            slot = {
                "slot_id": slot_id,
                "case_id": pair["case_id"],
                "condition_id": condition_id,
                "general_control": pair["general_control"],
                "question": model_input["question"],
                "question_text_sha256": condition["question_text_sha256"],
                "model_input_sha256": condition["model_input_sha256"],
                "pair_sha256": canonical_sha256(pair),
                "pair_bindings_sha256": canonical_sha256(pair["pair_bindings"]),
                "settings_sha256": settings_sha,
                "model_reference_sha256": model_sha,
                "prompt_token_ids_sha256": prompt_sha,
            }
            request = {
                **copy.deepcopy(slot),
                "slot_sha256": canonical_sha256(slot),
                "payload": payload,
                "payload_sha256": canonical_sha256(payload),
                "prompt_token_ids": tokens,
                "exact_input_tokens": len(tokens),
                "max_output_tokens": sampling["max_tokens"],
                "worst_case_reservation_usd": _decimal_text(per_slot_reservation),
            }
            slots.append(slot)
            requests.append(request)
            with localcontext() as context:
                context.prec = 50
                exact_estimate += _cost(len(tokens), sampling["max_tokens"], input_rate, output_rate)

    return {
        "schema_version": SCHEMA_VERSION,
        "preparation_kind": PREPARATION_KIND,
        "status": "prepared_offline_not_executed",
        "case_count": len(pairs),
        "planned_slot_count": len(slots),
        "condition_ids": list(CONDITIONS),
        "request_order": "case_interleaved_alternating_first_condition",
        "stop_rule": "stop_after_partial_empty_or_uncertain_no_retry",
        "planned_slots": slots,
        "planned_slots_sha256": canonical_sha256(slots),
        "prepared_requests": requests,
        "model_reference": model_ref,
        "model_reference_sha256": model_sha,
        "protocol_bindings": protocol,
        "protocol_bindings_sha256": canonical_sha256(protocol),
        "settings": sampling,
        "settings_sha256": settings_sha,
        "source_notice_guidance_code_bindings": common_bindings,
        "renderer_provenance": copy.deepcopy(provenance),
        "renderer_provenance_sha256": canonical_sha256(provenance),
        "comparison_manifest": comparison_manifest,
        "code_bindings": {
            "guidance_collection_module_sha256": _file_sha(__file__),
            "guidance_collection_tests_sha256": _file_sha(
                ROOT / "tests/test_guidance_collection.py"
            ),
            "comparison_module_sha256": _file_sha(__import__(
                "bibleprep.evidence_guidance_comparison", fromlist=["_"]
            ).__file__),
            "request_renderer_module_sha256": _file_sha(evidence_requests.__file__),
            "native_diagnostics_module_sha256": _file_sha(native_diagnostics.__file__),
            "native_bridge_module_sha256": _file_sha(evidence_native.__file__),
            "bounded_transport_module_sha256": _file_sha(tinker_evaluate.__file__),
            "comparison_manifest_sha256": _file_sha(ROOT / comparison_manifest),
        },
        "cost_basis": {
            "kind": "caller_declared_rates_require_protocol_time_verification",
            "currency": "USD",
            "rate_unit": "per_1m_tokens",
            "input_rate_usd_per_million": _decimal_text(input_rate),
            "output_rate_usd_per_million": _decimal_text(output_rate),
            "allowance_usd": _decimal_text(allowance),
            "cache_discount_assumed": False,
        },
        "full_run_worst_case_reservation_usd": _decimal_text(full_reservation),
        "full_run_exact_input_plus_output_cap_estimate_usd": _decimal_text(exact_estimate),
        "execution_authorized": False,
        "generation_authorized": False,
        "training_authorized": False,
        "model_calls": 0,
        "network_requests": 0,
    }


def verify_prepared_requests(case_specs, prepared, **prepare_kwargs):
    """Regenerate the complete preparation and reject any changed field."""
    rebuilt = prepare_native_requests(case_specs, **prepare_kwargs)
    if canonical_sha256(rebuilt) != canonical_sha256(prepared):
        raise GuidanceCollectionError("prepared requests failed exact regeneration")
    return True


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
    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    with os.fdopen(fd, "ab") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        return json.loads(
            path.read_bytes(), object_pairs_hook=pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("nonfinite")),
        )
    except (OSError, TypeError, ValueError) as exc:
        raise GuidanceCollectionError(f"malformed private artifact: {path.name}") from exc


def _read_events(path):
    try:
        rows = []
        for line in path.read_bytes().splitlines():
            if not line:
                continue
            rows.append(json.loads(line))
        return rows
    except (OSError, TypeError, ValueError) as exc:
        raise GuidanceCollectionError("collection journal is malformed") from exc


def _create_run_dir(run_dir, root):
    root = Path(root).resolve()
    run_dir = Path(run_dir)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    current = root
    try:
        relative = run_dir.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise GuidanceCollectionError("run directory escapes the project") from exc
    if not relative.parts or relative.parts[0] != "runs":
        raise GuidanceCollectionError("run directory must stay under private runs")
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise GuidanceCollectionError("run directory parent is missing or unsafe")
    destination = root / relative
    if destination.exists() or destination.is_symlink():
        raise GuidanceCollectionError("run directory already exists; retry and resume are forbidden")
    os.mkdir(destination, 0o700)
    os.chmod(destination, 0o700)
    receipts = destination / "receipts"
    os.mkdir(receipts, 0o700)
    os.chmod(receipts, 0o700)
    journal = destination / "events.jsonl"
    fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    return destination


def _default_transport():
    return tinker_evaluate.BoundedNativeTransport(worker=native_diagnostics.sampling_worker)


def _default_normalize(response, run_dir):
    return evidence_native.normalize_native_response(response, run_dir)


def _transport_config(prepared, run_dir, root):
    settings = prepared["settings"]
    reference = prepared["model_reference"]
    cost = prepared["cost_basis"]
    return {
        "base_url": tinker_evaluate.TINKER_URL,
        "model": MODEL,
        "run_dir": str(run_dir),
        "max_cases": prepared["planned_slot_count"],
        "max_input_tokens": settings["input_token_limit"],
        "max_output_tokens": settings["max_tokens"],
        "timeout_seconds": settings["deadline_seconds"],
        "input_price_per_million": float(cost["input_rate_usd_per_million"]),
        "output_price_per_million": float(cost["output_rate_usd_per_million"]),
        "budget_usd": float(cost["allowance_usd"]),
        "reasoning_effort": settings["reasoning_effort"],
        "temperature": settings["temperature"],
        "seed": settings["seed"],
        "prompt_date": settings["prompt_date"],
        "comparison_manifest": prepared["comparison_manifest"],
        "adapter_sampler_path": reference["adapter_sampler_path"],
        "checkpoint_reference_file": str(Path(root).resolve() / reference["checkpoint_reference_file"]),
        "checkpoint_reference_sha256": reference["checkpoint_reference_sha256"],
    }


def _validated_normalized(response, normalized, request):
    try:
        prompt_count = response["usage"]["prompt_tokens"]
        output_count = response["usage"]["completion_tokens"]
        response_prompt_sha = response["native_tinker"]["prompt_sha256"]
        final_text = normalized["final_text"]
        stop_reason = normalized["stop_reason"]
        diagnostic_sha = normalized["diagnostic_sha256"]
        output_sha = normalized["raw_generated_token_ids_sha256"]
        normalized_prompt_sha = normalized["native_prompt_sha256"]
    except (KeyError, TypeError) as exc:
        raise GuidanceCollectionError("native result lacks required receipt facts") from exc
    if type(prompt_count) is not int or prompt_count != request["exact_input_tokens"]:
        raise GuidanceCollectionError("native prompt count differs from prepared request")
    if response_prompt_sha != request["prompt_token_ids_sha256"] or normalized_prompt_sha != response_prompt_sha:
        raise GuidanceCollectionError("native prompt hash differs from prepared request")
    if type(output_count) is not int or not 0 <= output_count <= request["max_output_tokens"]:
        raise GuidanceCollectionError("native output count exceeds reservation")
    if response.get("model") != MODEL:
        raise GuidanceCollectionError("native response identifies a different model")
    if not isinstance(final_text, str) or stop_reason not in {"stop", "output_limit", "incomplete"}:
        raise GuidanceCollectionError("normalized native result is malformed")
    _sha(diagnostic_sha, "normalized.diagnostic_sha256")
    _sha(output_sha, "normalized.raw_generated_token_ids_sha256")
    if stop_reason == "stop" and final_text.strip():
        status = "complete"
    elif final_text.strip():
        status = "partial"
    else:
        status = "uncertain"
    return {
        "status": status,
        "stop_reason": stop_reason,
        "final_text": final_text if status != "uncertain" else None,
        "prompt_tokens": prompt_count,
        "completion_tokens": output_count,
        "diagnostic_sha256": diagnostic_sha,
        "raw_generated_token_ids_sha256": output_sha,
    }


def _result(slot, status, *, final_text=None, receipt_sha256=None):
    return {
        "slot_id": slot["slot_id"],
        "status": status,
        "final_text": final_text,
        "final_text_sha256": _text_sha256(final_text) if final_text is not None else None,
        "receipt_sha256": receipt_sha256,
    }


def _collection_summary(prepared, results, journal, local_stop_reason):
    completed = sum(item["status"] == "complete" for item in results)
    partial = sum(item["status"] == "partial" for item in results)
    uncertain = sum(item["status"] == "uncertain" for item in results)
    unsubmitted = sum(item["status"] == "unsubmitted" for item in results)
    derived_stop_reason = (
        "partial" if partial else "uncertain" if uncertain else
        "pre_submission_verification_failed" if unsubmitted else None
    )
    if local_stop_reason != derived_stop_reason:
        raise GuidanceCollectionError("local stop reason differs from collection outcomes")
    usages = [event["usage"] for event in journal if event["event"] == "result"]
    input_rate = Decimal(prepared["cost_basis"]["input_rate_usd_per_million"])
    output_rate = Decimal(prepared["cost_basis"]["output_rate_usd_per_million"])
    known_cost = sum(
        (_cost(item["prompt_tokens"], item["completion_tokens"], input_rate, output_rate)
         for item in usages), Decimal(0),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "collection_kind": COLLECTION_KIND,
        "status": "complete" if completed == len(results) else "stopped",
        "local_stop_reason": local_stop_reason,
        "planned_slots": copy.deepcopy(prepared["planned_slots"]),
        "results": results,
        "usage": {
            "submitted_slots": completed + partial + uncertain,
            "complete_slots": completed,
            "partial_slots": partial,
            "uncertain_slots": uncertain,
            "unsubmitted_slots": unsubmitted,
            "known_prompt_tokens": sum(item["prompt_tokens"] for item in usages),
            "known_completion_tokens": sum(item["completion_tokens"] for item in usages),
            "known_accounted_cost_usd": _decimal_text(known_cost),
            "full_run_worst_case_reservation_usd": prepared["full_run_worst_case_reservation_usd"],
            "accounting_uncertain": bool(uncertain),
            "invoice_reconciled": False,
        },
        "bindings": {
            "prepared_requests_sha256": canonical_sha256(prepared),
            "planned_slots_sha256": prepared["planned_slots_sha256"],
            "model_reference_sha256": prepared["model_reference_sha256"],
            "settings_sha256": prepared["settings_sha256"],
            "source_notice_guidance_code_bindings": copy.deepcopy(
                prepared["source_notice_guidance_code_bindings"]
            ),
            "protocol_bindings": copy.deepcopy(prepared["protocol_bindings"]),
            "protocol_bindings_sha256": prepared["protocol_bindings_sha256"],
            "journal_sha256": canonical_sha256(journal),
        },
        "automatic_retry": False,
        "resume_supported": False,
        "quality_review_complete": False,
        "promotion_authorized": False,
        "training_authorized": False,
    }


def collect_sequential(
    case_specs, prepared, *, run_dir, execute=False, secret=None, transport=None,
    normalize=None, renderer=None, root=ROOT,
):
    """Collect one sequential run; stop all after any non-complete outcome."""
    if type(execute) is not bool:
        raise GuidanceCollectionError("execute must be boolean")
    prepare_kwargs = {
        "model_reference": prepared.get("model_reference"),
        "protocol_bindings": prepared.get("protocol_bindings"),
        "settings": prepared.get("settings"),
        "input_rate_usd_per_million": Decimal(prepared.get("cost_basis", {}).get(
            "input_rate_usd_per_million", "NaN"
        )),
        "output_rate_usd_per_million": Decimal(prepared.get("cost_basis", {}).get(
            "output_rate_usd_per_million", "NaN"
        )),
        "allowance_usd": Decimal(prepared.get("cost_basis", {}).get("allowance_usd", "NaN")),
        "comparison_manifest": prepared.get("comparison_manifest"),
        "renderer": renderer,
        "root": root,
    }
    verify_prepared_requests(case_specs, prepared, **prepare_kwargs)
    if not execute:
        return copy.deepcopy(prepared)
    if not isinstance(secret, str) or not secret:
        raise GuidanceCollectionError("an explicit sampling credential is required for execution")
    if transport is None and not SAMPLER_RE.fullmatch(
        prepared["model_reference"]["adapter_sampler_path"]
    ):
        raise GuidanceCollectionError("synthetic sampler references require an injected transport")
    destination = _create_run_dir(run_dir, root)
    journal_path = destination / "events.jsonl"
    receipts_dir = destination / "receipts"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "collection_kind": COLLECTION_KIND,
        "prepared_requests_sha256": canonical_sha256(prepared),
        "planned_slots_sha256": prepared["planned_slots_sha256"],
        "planned_slot_count": prepared["planned_slot_count"],
        "model_reference_sha256": prepared["model_reference_sha256"],
        "protocol_bindings": copy.deepcopy(prepared["protocol_bindings"]),
        "protocol_bindings_sha256": prepared["protocol_bindings_sha256"],
        "settings_sha256": prepared["settings_sha256"],
        "automatic_retry": False,
        "resume_supported": False,
        "training_authorized": False,
    }
    _write_exclusive(destination / "manifest.json", manifest)
    active_transport = _default_transport() if transport is None else transport
    active_normalize = _default_normalize if normalize is None else normalize
    results = []
    local_stop_reason = None
    try:
        for index, saved_request in enumerate(prepared["prepared_requests"]):
            try:
                current = prepare_native_requests(case_specs, **prepare_kwargs)
                if canonical_sha256(current) != canonical_sha256(prepared):
                    raise GuidanceCollectionError("source, pair, request, or native prompt changed")
                request = current["prepared_requests"][index]
                if canonical_sha256(request) != canonical_sha256(saved_request):
                    raise GuidanceCollectionError("next native request changed")
            except Exception:
                local_stop_reason = "pre_submission_verification_failed"
                break
            _append_event(journal_path, {
                "event": "submitted", "slot_id": request["slot_id"],
                "request_sha256": canonical_sha256(request),
            })
            response = None
            try:
                config = _transport_config(prepared, destination, root)
                response = active_transport(request["payload"], config, secret)
                normalized = active_normalize(response, destination)
                facts = _validated_normalized(response, normalized, request)
                receipt = {
                    "schema_version": SCHEMA_VERSION,
                    "receipt_kind": "native_result",
                    "prepared_requests_sha256": canonical_sha256(prepared),
                    "planned_slots_sha256": prepared["planned_slots_sha256"],
                    "slot_id": request["slot_id"],
                    "slot_sha256": request["slot_sha256"],
                    "request_sha256": canonical_sha256(request),
                    "model_reference_sha256": prepared["model_reference_sha256"],
                    "protocol_bindings_sha256": prepared["protocol_bindings_sha256"],
                    "settings_sha256": prepared["settings_sha256"],
                    "normalized": facts,
                    "response": response,
                }
                receipt_path = receipts_dir / f"{index:04d}-{request['slot_id']}.json"
                receipt_sha = _write_exclusive(receipt_path, receipt)
                event = {
                    "event": "result",
                    "slot_id": request["slot_id"],
                    "status": facts["status"],
                    "stop_reason": facts["stop_reason"],
                    "final_text": facts["final_text"],
                    "final_text_sha256": (
                        _text_sha256(facts["final_text"]) if facts["final_text"] is not None else None
                    ),
                    "receipt_path": str(receipt_path.relative_to(destination)),
                    "receipt_sha256": receipt_sha,
                    "usage": {
                        "prompt_tokens": facts["prompt_tokens"],
                        "completion_tokens": facts["completion_tokens"],
                    },
                }
                _append_event(journal_path, event)
                results.append(_result(
                    prepared["planned_slots"][index], facts["status"],
                    final_text=facts["final_text"], receipt_sha256=receipt_sha,
                ))
                if facts["status"] != "complete":
                    local_stop_reason = "partial" if facts["status"] == "partial" else "uncertain"
                    break
            except Exception:
                failure_receipt = {
                    "schema_version": SCHEMA_VERSION,
                    "receipt_kind": "uncertain_failure",
                    "prepared_requests_sha256": canonical_sha256(prepared),
                    "planned_slots_sha256": prepared["planned_slots_sha256"],
                    "slot_id": request["slot_id"],
                    "slot_sha256": request["slot_sha256"],
                    "request_sha256": canonical_sha256(request),
                    "model_reference_sha256": prepared["model_reference_sha256"],
                    "protocol_bindings_sha256": prepared["protocol_bindings_sha256"],
                    "settings_sha256": prepared["settings_sha256"],
                    "response_received": response is not None,
                    "response": response,
                }
                receipt_path = receipts_dir / f"{index:04d}-{request['slot_id']}-uncertain.json"
                receipt_sha = _write_exclusive(receipt_path, failure_receipt)
                _append_event(journal_path, {
                    "event": "failure", "slot_id": request["slot_id"],
                    "status": "uncertain",
                    "receipt_path": str(receipt_path.relative_to(destination)),
                    "receipt_sha256": receipt_sha,
                })
                results.append(_result(
                    prepared["planned_slots"][index], "uncertain", receipt_sha256=receipt_sha,
                ))
                local_stop_reason = "uncertain"
                break
    finally:
        try:
            if hasattr(active_transport, "close"):
                active_transport.close()
        finally:
            secret = ""
    completed_ids = {item["slot_id"] for item in results}
    for slot in prepared["planned_slots"]:
        if slot["slot_id"] not in completed_ids:
            results.append(_result(slot, "unsubmitted"))
    order = {slot["slot_id"]: index for index, slot in enumerate(prepared["planned_slots"])}
    results.sort(key=lambda item: order[item["slot_id"]])
    journal = _read_events(journal_path)
    summary = _collection_summary(prepared, results, journal, local_stop_reason)
    _write_exclusive(destination / "collection.json", summary)
    return summary


def verify_collection_run(
    case_specs, prepared, *, run_dir, renderer=None, normalize=None, root=ROOT,
):
    """Verify current inputs, journal order, every receipt byte, and saved summary."""
    prepare_kwargs = {
        "model_reference": prepared["model_reference"],
        "protocol_bindings": prepared["protocol_bindings"],
        "settings": prepared["settings"],
        "input_rate_usd_per_million": Decimal(prepared["cost_basis"]["input_rate_usd_per_million"]),
        "output_rate_usd_per_million": Decimal(prepared["cost_basis"]["output_rate_usd_per_million"]),
        "allowance_usd": Decimal(prepared["cost_basis"]["allowance_usd"]),
        "comparison_manifest": prepared["comparison_manifest"],
        "renderer": renderer,
        "root": root,
    }
    verify_prepared_requests(case_specs, prepared, **prepare_kwargs)
    destination = Path(run_dir)
    if not destination.is_absolute():
        destination = Path(root) / destination
    if not destination.is_dir() or destination.is_symlink():
        raise GuidanceCollectionError("collection run directory is unavailable")
    manifest = _read_json(destination / "manifest.json")
    if manifest != {
        "schema_version": SCHEMA_VERSION,
        "collection_kind": COLLECTION_KIND,
        "prepared_requests_sha256": canonical_sha256(prepared),
        "planned_slots_sha256": prepared["planned_slots_sha256"],
        "planned_slot_count": prepared["planned_slot_count"],
        "model_reference_sha256": prepared["model_reference_sha256"],
        "protocol_bindings": copy.deepcopy(prepared["protocol_bindings"]),
        "protocol_bindings_sha256": prepared["protocol_bindings_sha256"],
        "settings_sha256": prepared["settings_sha256"],
        "automatic_retry": False,
        "resume_supported": False,
        "training_authorized": False,
    }:
        raise GuidanceCollectionError("collection manifest differs from preparation")
    journal = _read_events(destination / "events.jsonl")
    results = []
    cursor = 0
    stopped = False
    active_normalize = _default_normalize if normalize is None else normalize
    for index, (slot, request) in enumerate(zip(
        prepared["planned_slots"], prepared["prepared_requests"], strict=True,
    )):
        if stopped or cursor == len(journal):
            results.append(_result(slot, "unsubmitted"))
            continue
        submitted = journal[cursor]
        if submitted != {
            "event": "submitted", "slot_id": slot["slot_id"],
            "request_sha256": canonical_sha256(request),
        }:
            raise GuidanceCollectionError("journal submission order or binding differs")
        cursor += 1
        if cursor == len(journal):
            raise GuidanceCollectionError("submitted slot lacks terminal journal event")
        terminal = journal[cursor]
        cursor += 1
        if terminal.get("event") not in {"result", "failure"} or terminal.get("slot_id") != slot["slot_id"]:
            raise GuidanceCollectionError("journal terminal event differs")
        path = destination / terminal.get("receipt_path", "")
        if path.parent != destination / "receipts" or path.is_symlink() or not path.is_file():
            raise GuidanceCollectionError("receipt path is unsafe or missing")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != terminal.get("receipt_sha256"):
            raise GuidanceCollectionError("receipt bytes differ from journal hash")
        receipt = _read_json(path)
        for key, wanted in (
            ("prepared_requests_sha256", canonical_sha256(prepared)),
            ("planned_slots_sha256", prepared["planned_slots_sha256"]),
            ("slot_id", slot["slot_id"]),
            ("slot_sha256", request["slot_sha256"]),
            ("request_sha256", canonical_sha256(request)),
            ("model_reference_sha256", prepared["model_reference_sha256"]),
            ("protocol_bindings_sha256", prepared["protocol_bindings_sha256"]),
            ("settings_sha256", prepared["settings_sha256"]),
        ):
            if receipt.get(key) != wanted:
                raise GuidanceCollectionError("receipt binding differs from preparation")
        if terminal["event"] == "failure":
            if terminal.get("status") != "uncertain" or receipt.get("receipt_kind") != "uncertain_failure":
                raise GuidanceCollectionError("failure receipt is malformed")
            results.append(_result(slot, "uncertain", receipt_sha256=terminal["receipt_sha256"]))
            stopped = True
            continue
        if receipt.get("receipt_kind") != "native_result":
            raise GuidanceCollectionError("result receipt kind is malformed")
        normalized = active_normalize(receipt.get("response"), destination)
        facts = _validated_normalized(receipt.get("response"), normalized, request)
        expected_terminal = {
            "event": "result", "slot_id": slot["slot_id"], "status": facts["status"],
            "stop_reason": facts["stop_reason"], "final_text": facts["final_text"],
            "final_text_sha256": (
                _text_sha256(facts["final_text"]) if facts["final_text"] is not None else None
            ),
            "receipt_path": terminal["receipt_path"],
            "receipt_sha256": terminal["receipt_sha256"],
            "usage": {
                "prompt_tokens": facts["prompt_tokens"],
                "completion_tokens": facts["completion_tokens"],
            },
        }
        if terminal != expected_terminal or receipt.get("normalized") != facts:
            raise GuidanceCollectionError("result receipt differs from normalized native facts")
        results.append(_result(
            slot, facts["status"], final_text=facts["final_text"],
            receipt_sha256=terminal["receipt_sha256"],
        ))
        stopped = facts["status"] != "complete"
    if cursor != len(journal):
        raise GuidanceCollectionError("journal contains events after stop or inventory end")
    saved = _read_json(destination / "collection.json")
    expected = _collection_summary(prepared, results, journal, saved.get("local_stop_reason"))
    if canonical_sha256(saved) != canonical_sha256(expected):
        raise GuidanceCollectionError("saved collection summary differs from verified receipts")
    return copy.deepcopy(expected)
