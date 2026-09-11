"""One prospective matched B/G collection with durable native receipts.

Preparation and verification are offline. Execution is fixed to one protocol,
one directory, and one durable sampling reservation already included in the
Candidate G sequence budget. There is no retry or resume path.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import re

from bibleprep import chat_model, evidence_native, guidance_collection
from bibleprep import native_diagnostics_v1 as diagnostics
from bibleprep import tinker_evaluate as native
from bibleprep import train_inkling as raw

MODEL = "thinkingmachines/Inkling"
BASELINE = "runs/evidence-pilot-v1/settings.json"
PROTOCOL_PATH = "runs/candidate-g-execution-v1/evaluation/protocol.json"
LIVE_RUN_PATH = "runs/candidate-g-execution-v1/evaluation/live"
SAMPLING_RESERVATION_PATH = "runs/candidate-g-execution-v1/evaluation/sampling-phase-reservation.json"
TRAINING_PROTOCOL_PATH = "runs/candidate-g-execution-v1/training-protocol.json"
SEQUENCE_RESERVATION_PATH = "runs/candidate-g-execution-v1/training/sequence-reservation.json"
B_CHECKPOINT_PATH = "runs/inkling-original-text-v1/checkpoints.json"
G_CHECKPOINT_PATH = "runs/candidate-g-execution-v1/training/checkpoints.json"
SETTINGS = {"max_input_tokens": 8192, "max_output_tokens": 8192,
            "timeout_seconds": 300, "reasoning_effort": "medium",
            "temperature": 0.0, "seed": 1702}
SAMPLE_RESERVE_NANO = 3_219_456_000
TRANSPORT_BUDGET_USD = 3.219456
PER_SLOT_RESERVE_NANO = SAMPLE_RESERVE_NANO // 60
CASE_FIELDS = frozenset({"id", "language", "group", "prompt", "provided_evidence",
                         "rubric", "source_refs", "chapter_keys", "known_exposure"})
RUBRIC_FIELDS = frozenset({"required_points", "error_conditions",
                           "acceptable_alternatives", "source_support"})
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _fixed(root, value, expected, *, must_exist=True):
    root = Path(root).resolve()
    supplied = Path(value)
    target = supplied.resolve() if supplied.is_absolute() else (root / supplied).resolve()
    wanted = (root / expected).resolve()
    if target != wanted:
        raise ValueError(f"Path must be the fixed project artifact: {expected}")
    current = root
    for part in Path(expected).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Fixed artifact path contains a symlink.")
    if must_exist and not target.is_file():
        raise ValueError("Fixed artifact is unavailable.")
    return target


def checked(root, entry):
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
        raise ValueError("Frozen file entry fields differ.")
    path = Path(entry["path"])
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Use portable frozen file references.")
    target = Path(root).resolve() / path
    if target.is_symlink() or not target.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("Frozen artifact escapes the project.")
    if sha(target) != entry["sha256"]:
        raise ValueError("Frozen artifact changed.")
    return target


def _texts(value, label, *, allow_empty=False):
    if (not isinstance(value, list) or (not allow_empty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)):
        raise ValueError(f"{label} must be a list of nonempty strings.")


def _validate_case(case):
    if not isinstance(case, dict) or set(case) != set(CASE_FIELDS):
        raise ValueError("Evaluation case fields differ from the frozen schema.")
    if not isinstance(case["id"], str) or not ID_RE.fullmatch(case["id"]):
        raise ValueError("Evaluation case id is invalid.")
    for field in ("language", "group", "prompt", "provided_evidence"):
        if not isinstance(case[field], str):
            raise ValueError(f"Evaluation case {field} must be text.")
    if not case["prompt"].strip():
        raise ValueError("An evaluation prompt is missing.")
    if case["language"] not in {"hbo", "grc", "arc", "en"}:
        raise ValueError("Evaluation language is invalid.")
    if case["group"] not in {"direct", "boundary", "intent", "general"}:
        raise ValueError("Evaluation group is invalid.")
    general = case["group"] == "general"
    if (case["language"] == "en") != general:
        raise ValueError("Only general controls may use language en.")
    for field in ("source_refs", "chapter_keys", "known_exposure"):
        _texts(case[field], field, allow_empty=(general and field != "known_exposure"))
    if general:
        if case["provided_evidence"] or case["source_refs"] or case["chapter_keys"]:
            raise ValueError("General controls cannot contain Bible evidence or references.")
    elif not case["provided_evidence"].strip():
        raise ValueError("Bible cases require evidence, source refs, and chapter keys.")
    rubric = case["rubric"]
    if not isinstance(rubric, dict) or set(rubric) != set(RUBRIC_FIELDS):
        raise ValueError("Evaluation rubric fields differ from the frozen schema.")
    for field in RUBRIC_FIELDS:
        _texts(rubric[field], "rubric." + field,
               allow_empty=field in {"acceptable_alternatives", "source_support"})
    if not general and not rubric["source_support"]:
        raise ValueError("Bible cases require source-support criteria.")


def load_protocol(root, path):
    root = Path(root).resolve()
    protocol_path = _fixed(root, path, PROTOCOL_PATH)
    protocol = json.loads(protocol_path.read_bytes())
    if (protocol.get("status") != "frozen_before_training_and_generation"
            or protocol.get("case_count") != 30 or protocol.get("slot_count") != 60
            or protocol.get("sampling") != SETTINGS
            or protocol.get("sampling_reserve_nano_usd") != SAMPLE_RESERVE_NANO
            or protocol.get("automatic_promotion") is not False
            or not isinstance(protocol.get("immutable_files"), list)):
        raise ValueError("Candidate G evaluation protocol differs.")
    for entry in protocol["immutable_files"]:
        checked(root, entry)
    checked(root, protocol["questions"])
    return protocol


def prepare(root, protocol_path, *, renderer=None):
    root = Path(root).resolve()
    fixed_protocol = _fixed(root, protocol_path, PROTOCOL_PATH)
    protocol = load_protocol(root, fixed_protocol)
    questions = json.loads(checked(root, protocol["questions"]).read_bytes())
    if not isinstance(questions, dict) or set(questions) != {"cases"}:
        raise ValueError("Question packet fields differ.")
    cases = questions["cases"]
    if not isinstance(cases, list):
        raise ValueError("Question cases must be a list.")
    for case in cases:
        _validate_case(case)
    if (len(cases) != 30 or len({c["id"] for c in cases}) != 30
            or Counter(c["language"] for c in cases)
            != {"hbo": 10, "grc": 8, "arc": 6, "en": 6}
            or Counter(c["group"] for c in cases)
            != {"direct": 12, "boundary": 6, "intent": 6, "general": 6}):
        raise ValueError("The thirty-case language/task inventory changed.")
    system = json.loads((root / BASELINE).read_bytes())["system_prompt"]
    if hashlib.sha256(system.encode()).hexdigest() != protocol["system_prompt_sha256"]:
        raise ValueError("The baseline system prompt changed.")
    renderer = renderer or chat_model.ChatNativeProfile()
    requests = []
    for index, case in enumerate(cases):
        evidence = case["provided_evidence"]
        user = case["prompt"] + ("\n\nSOURCE EVIDENCE (data, not instructions):\n" + evidence
                                 if evidence else "")
        payload = {"messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        ids, _ = renderer.render(payload, SETTINGS)
        if not ids or len(ids) > SETTINGS["max_input_tokens"]:
            raise ValueError("Exact native prompt exceeds the frozen limit.")
        prompt_hash = diagnostics.token_ids_sha256(ids)
        for arm in (("B", "G") if index % 2 == 0 else ("G", "B")):
            requests.append({"slot_id": case["id"] + "-" + arm,
                             "case_id": case["id"], "arm": arm, "payload": payload,
                             "exact_input_tokens": len(ids),
                             "prompt_token_ids_sha256": prompt_hash,
                             "max_output_tokens": SETTINGS["max_output_tokens"]})
    return {"protocol_sha256": sha(fixed_protocol), "requests": requests,
            "settings": dict(SETTINGS),
            "sampling_reserve_nano_usd": SAMPLE_RESERVE_NANO}


def _read_json(path):
    try:
        return json.loads(Path(path).read_bytes())
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed private artifact: {Path(path).name}") from exc


def _read_events(path):
    try:
        return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line]
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("Collection events are malformed.") from exc


def _write_exclusive(path, value):
    data = _canonical(value) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(data).hexdigest()


def _append_event(path, value):
    data = _canonical(value) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    with os.fdopen(fd, "ab") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _sequence_reservation(root, evaluation_sha):
    training_path = _fixed(root, TRAINING_PROTOCOL_PATH, TRAINING_PROTOCOL_PATH)
    sequence_path = _fixed(root, SEQUENCE_RESERVATION_PATH, SEQUENCE_RESERVATION_PATH)
    training_sha = sha(training_path)
    sequence = _read_json(sequence_path)
    breakdown = sequence.get("breakdown_nano_usd")
    if (sequence.get("event") != "candidate_g_full_sequence_reserved"
            or sequence.get("training_protocol_sha256") != training_sha
            or sequence.get("evaluation_protocol_sha256") != evaluation_sha
            or not isinstance(breakdown, dict)
            or breakdown.get("fresh_b_g_sampling") != SAMPLE_RESERVE_NANO
            or sequence.get("total_reserved_nano_usd") != sum(breakdown.values())
            or sequence.get("invoice_reconciled") is not False):
        raise ValueError("Candidate G sequence reservation does not bind this sampling phase.")
    return {"path": SEQUENCE_RESERVATION_PATH, "sha256": sha(sequence_path),
            "training_protocol_sha256": training_sha,
            "evaluation_protocol_sha256": evaluation_sha,
            "run_id": sequence.get("run_id")}


def _sampling_reservation(root, prepared, sequence):
    path = _fixed(root, SAMPLING_RESERVATION_PATH, SAMPLING_RESERVATION_PATH,
                  must_exist=False)
    value = {"schema_version": 1, "event": "candidate_g_sampling_phase_reserved",
             "run_path": LIVE_RUN_PATH,
             "sampling_reserved_nano_usd": SAMPLE_RESERVE_NANO,
             "transport_budget_usd": "3.219456",
             "protocol_sha256": prepared["protocol_sha256"],
             "prepared_sha256": _digest(prepared), "sequence_reservation": sequence,
             "automatic_retry": False, "resume_supported": False,
             "invoice_reconciled": False}
    return path, value, _write_exclusive(path, value)


def _make_run(root, run_dir):
    target = _fixed(root, run_dir, LIVE_RUN_PATH, must_exist=False)
    if target.exists() or target.is_symlink():
        raise ValueError("The fixed evaluation run already exists.")
    target.mkdir(mode=0o700, parents=False)
    os.chmod(target, 0o700)
    receipts = target / "receipts"
    receipts.mkdir(mode=0o700)
    os.chmod(receipts, 0o700)
    fd = os.open(target / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    return target


def _result(request, status, *, facts=None, receipt_sha256=None):
    value = {"slot_id": request["slot_id"], "case_id": request["case_id"],
             "arm": request["arm"], "status": status,
             "receipt_sha256": receipt_sha256}
    if facts is not None:
        value.update(facts)
    return value


def _summary(prepared, results, stop_reason):
    counts = Counter(item["status"] for item in results)
    complete = counts["complete"] == 60 and len(results) == 60
    expected_stop = (None if complete else "partial" if counts["partial"] else
                     "uncertain" if counts["uncertain"] else
                     "pre_submission_verification_failed")
    if stop_reason != expected_stop:
        raise ValueError("Collection stop reason differs from terminal outcomes.")
    known = [item for item in results if "prompt_tokens" in item]
    return {"schema_version": 1, "artifact_kind": "candidate_g_native_collection_v1",
            "status": "complete" if complete else "stopped", "stop_reason": stop_reason,
            "slot_count": 60, "counts": dict(counts), "results": results,
            "known_input_tokens": sum(item["prompt_tokens"] for item in known),
            "known_output_tokens": sum(item["completion_tokens"] for item in known),
            "known_estimated_nano_usd": sum(item["prompt_tokens"] * 1870
                                             + item["completion_tokens"] * 4680
                                             for item in known),
            "sampling_reserved_nano_usd": SAMPLE_RESERVE_NANO,
            "uncertain_reserved_nano_usd": counts["uncertain"] * PER_SLOT_RESERVE_NANO,
            "accounting_uncertain": bool(counts["uncertain"]),
            "invoice_reconciled": False, "automatic_retry": False,
            "resume_supported": False, "automatic_promotion": False}


def _verify_checkpoints(root, checkpoints):
    expected = {"B": B_CHECKPOINT_PATH, "G": G_CHECKPOINT_PATH}
    if (not isinstance(checkpoints, dict) or set(checkpoints) != set(expected)
            or any(not isinstance(checkpoints[arm], dict)
                   or checkpoints[arm].get("path") != path
                   for arm, path in expected.items())):
        raise ValueError("Candidate G evaluation requires the fixed B and G checkpoint files.")
    from bibleprep.evaluate_adapter import checkpoint_identity
    refs = {}
    for arm, entry in checkpoints.items():
        file = checked(root, entry)
        sampler, fingerprint = checkpoint_identity(file)
        if arm == "B" and sampler != chat_model.resolve_b_checkpoint(root):
            raise ValueError("B provenance does not match.")
        if arm == "G":
            from bibleprep import train_candidate_g
            verified = train_candidate_g.verify_completed_checkpoint(
                root, G_CHECKPOINT_PATH)
            if verified != (sampler, fingerprint):
                raise ValueError("G completion receipt does not match.")
        refs[arm] = {"checkpoint_reference_file": str(file),
                     "checkpoint_reference_sha256": fingerprint,
                     "adapter_sampler_path": sampler}
    return refs


def collect(root, protocol_path, prepared, checkpoints, *, run_dir, execute=False,
            secret=None, renderer=None, transport_factory=None, normalizer=None):
    root = Path(root).resolve()
    protocol_file = _fixed(root, protocol_path, PROTOCOL_PATH)
    active_renderer = renderer or chat_model.ChatNativeProfile()
    if prepare(root, protocol_file, renderer=active_renderer) != prepared:
        raise ValueError("Prepared requests differ from the frozen questions.")
    _fixed(root, run_dir, LIVE_RUN_PATH, must_exist=False)
    if not execute:
        return {"status": "dry_run", "slots": len(prepared["requests"]),
                "reserve_usd": raw.money(SAMPLE_RESERVE_NANO)}
    if not secret:
        raise ValueError("Explicit credential and both verified checkpoints required.")
    refs = _verify_checkpoints(root, checkpoints)
    sequence = _sequence_reservation(root, prepared["protocol_sha256"])
    live = _fixed(root, run_dir, LIVE_RUN_PATH, must_exist=False)
    reservation_path = _fixed(root, SAMPLING_RESERVATION_PATH,
                              SAMPLING_RESERVATION_PATH, must_exist=False)
    if live.exists() or reservation_path.exists():
        raise ValueError("Candidate G sampling is already reserved or collected.")
    _, reservation, reservation_sha = _sampling_reservation(root, prepared, sequence)
    destination = _make_run(root, run_dir)
    manifest = {"schema_version": 1,
                "artifact_kind": "candidate_g_native_collection_manifest_v1",
                "protocol_sha256": prepared["protocol_sha256"],
                "prepared_sha256": _digest(prepared), "slot_count": 60,
                "checkpoint_files": copy.deepcopy(checkpoints),
                "sequence_reservation": sequence,
                "sampling_reservation_sha256": reservation_sha,
                "sampling_reserved_nano_usd": SAMPLE_RESERVE_NANO,
                "transport_budget_usd": "3.219456", "automatic_retry": False,
                "resume_supported": False}
    _write_exclusive(destination / "manifest.json", manifest)
    transports, results, stop_reason = {}, [], None
    normalize = normalizer or evidence_native.normalize_native_response
    try:
        for request in prepared["requests"]:
            try:
                if (prepare(root, protocol_file, renderer=active_renderer) != prepared
                        or _sequence_reservation(root, prepared["protocol_sha256"]) != sequence
                        or _read_json(root / SAMPLING_RESERVATION_PATH) != reservation):
                    raise ValueError("Frozen inputs changed.")
                for entry in checkpoints.values():
                    checked(root, entry)
            except Exception:
                stop_reason = "pre_submission_verification_failed"
                _append_event(destination / "events.jsonl",
                              {"event": stop_reason, "slot_id": request["slot_id"]})
                break
            arm = request["arm"]
            if arm not in transports:
                transports[arm] = (transport_factory(arm) if transport_factory else
                    native.BoundedNativeTransport(worker=diagnostics.sampling_worker))
            config = {**SETTINGS, **refs[arm], "model": MODEL,
                      "base_url": native.TINKER_URL, "run_dir": str(destination),
                      "max_cases": 60, "budget_usd": TRANSPORT_BUDGET_USD,
                      "input_price_per_million": 1.87,
                      "output_price_per_million": 4.68,
                      "prompt_date": "2026-09-09",
                      "comparison_manifest": "manifests/comparison-large-models-v1.json"}
            request_sha = _digest(request)
            _append_event(destination / "events.jsonl",
                          {"event": "submitted", "slot_id": request["slot_id"],
                           "request_sha256": request_sha,
                           "reserved_nano_usd": PER_SLOT_RESERVE_NANO})
            response = None
            try:
                response = transports[arm](request["payload"], config, secret)
                facts = guidance_collection._validated_normalized(
                    response, normalize(response, destination), request)
                result = _result(request, facts["status"], facts=facts)
                receipt = {"schema_version": 1,
                           "artifact_kind": "candidate_g_response_receipt_v1",
                           "prepared_sha256": _digest(prepared), "request": request,
                           "request_sha256": request_sha, "response": response,
                           "normalized": facts}
                receipt_path = destination / "receipts" / (request["slot_id"] + ".json")
                receipt_sha = _write_exclusive(receipt_path, receipt)
                result["receipt_sha256"] = receipt_sha
                results.append(result)
                _append_event(destination / "events.jsonl",
                              {"event": "result", "slot_id": request["slot_id"],
                               "status": facts["status"],
                               "receipt_path": str(receipt_path.relative_to(destination)),
                               "receipt_sha256": receipt_sha})
                if facts["status"] != "complete":
                    stop_reason = "partial" if facts["status"] == "partial" else "uncertain"
                    break
            except BaseException as exc:
                receipt = {"schema_version": 1,
                           "artifact_kind": "candidate_g_uncertain_response_receipt_v1",
                           "prepared_sha256": _digest(prepared), "request": request,
                           "request_sha256": request_sha,
                           "response_received": response is not None, "response": response,
                           "exception_type": type(exc).__name__}
                receipt_path = destination / "receipts" / (request["slot_id"] + "-uncertain.json")
                receipt_sha = _write_exclusive(receipt_path, receipt)
                results.append(_result(request, "uncertain", receipt_sha256=receipt_sha))
                _append_event(destination / "events.jsonl",
                              {"event": "uncertain", "slot_id": request["slot_id"],
                               "status": "uncertain",
                               "receipt_path": str(receipt_path.relative_to(destination)),
                               "receipt_sha256": receipt_sha})
                stop_reason = "uncertain"
                break
    finally:
        for transport in transports.values():
            if hasattr(transport, "close"):
                transport.close()
        secret = ""
    seen = {item["slot_id"] for item in results}
    results.extend(_result(request, "unsubmitted") for request in prepared["requests"]
                   if request["slot_id"] not in seen)
    order = {request["slot_id"]: index for index, request in enumerate(prepared["requests"])}
    results.sort(key=lambda item: order[item["slot_id"]])
    summary = _summary(prepared, results, stop_reason)
    _write_exclusive(destination / "collection.json", summary)
    return summary


def verify_collection(root, protocol_path, prepared, run_dir, renderer=None,
                      normalizer=None):
    """Verify fixed inputs, reservations, journal, sidecars, receipts, and summary."""
    root = Path(root).resolve()
    protocol_file = _fixed(root, protocol_path, PROTOCOL_PATH)
    destination = _fixed(root, run_dir, LIVE_RUN_PATH, must_exist=False)
    if not destination.is_dir() or destination.is_symlink():
        raise ValueError("Fixed collection directory is unavailable.")
    active_renderer = renderer or chat_model.ChatNativeProfile()
    if prepare(root, protocol_file, renderer=active_renderer) != prepared:
        raise ValueError("Prepared requests differ from frozen questions.")
    sequence = _sequence_reservation(root, prepared["protocol_sha256"])
    reservation_path = _fixed(root, SAMPLING_RESERVATION_PATH, SAMPLING_RESERVATION_PATH)
    reservation = _read_json(reservation_path)
    expected_reservation = {"schema_version": 1,
        "event": "candidate_g_sampling_phase_reserved", "run_path": LIVE_RUN_PATH,
        "sampling_reserved_nano_usd": SAMPLE_RESERVE_NANO,
        "transport_budget_usd": "3.219456",
        "protocol_sha256": prepared["protocol_sha256"],
        "prepared_sha256": _digest(prepared), "sequence_reservation": sequence,
        "automatic_retry": False, "resume_supported": False,
        "invoice_reconciled": False}
    if reservation != expected_reservation:
        raise ValueError("Sampling reservation differs from the frozen run.")
    manifest = _read_json(destination / "manifest.json")
    expected_manifest = {"schema_version": 1,
        "artifact_kind": "candidate_g_native_collection_manifest_v1",
        "protocol_sha256": prepared["protocol_sha256"],
        "prepared_sha256": _digest(prepared), "slot_count": 60,
        "checkpoint_files": manifest.get("checkpoint_files"),
        "sequence_reservation": sequence,
        "sampling_reservation_sha256": sha(reservation_path),
        "sampling_reserved_nano_usd": SAMPLE_RESERVE_NANO,
        "transport_budget_usd": "3.219456", "automatic_retry": False,
        "resume_supported": False}
    if manifest != expected_manifest or set(manifest.get("checkpoint_files", {})) != {"B", "G"}:
        raise ValueError("Collection manifest differs from the frozen run.")
    _verify_checkpoints(root, manifest["checkpoint_files"])
    events = _read_events(destination / "events.jsonl")
    cursor, results, stopped, stop_reason = 0, [], False, None
    normalize = normalizer or evidence_native.normalize_native_response
    for request in prepared["requests"]:
        if stopped or cursor == len(events):
            results.append(_result(request, "unsubmitted"))
            continue
        event = events[cursor]
        if event.get("event") == "pre_submission_verification_failed":
            if event != {"event": "pre_submission_verification_failed",
                         "slot_id": request["slot_id"]}:
                raise ValueError("Stale-input terminal event differs.")
            cursor += 1
            results.append(_result(request, "unsubmitted"))
            stopped, stop_reason = True, "pre_submission_verification_failed"
            continue
        submitted = {"event": "submitted", "slot_id": request["slot_id"],
                     "request_sha256": _digest(request),
                     "reserved_nano_usd": PER_SLOT_RESERVE_NANO}
        if event != submitted:
            raise ValueError("Submission order or request binding differs.")
        cursor += 1
        if cursor == len(events):
            raise ValueError("Submitted request lacks a terminal event.")
        terminal = events[cursor]
        cursor += 1
        if terminal.get("event") not in {"result", "uncertain"}:
            raise ValueError("Submitted request terminal event is invalid.")
        if terminal.get("slot_id") != request["slot_id"]:
            raise ValueError("Terminal slot differs from submission.")
        receipt_path = destination / terminal.get("receipt_path", "")
        if (receipt_path.parent != destination / "receipts" or receipt_path.is_symlink()
                or not receipt_path.is_file() or sha(receipt_path) != terminal.get("receipt_sha256")):
            raise ValueError("Response receipt path or hash differs.")
        receipt = _read_json(receipt_path)
        if (receipt.get("prepared_sha256") != _digest(prepared)
                or receipt.get("request") != request
                or receipt.get("request_sha256") != _digest(request)):
            raise ValueError("Response receipt request binding differs.")
        if terminal["event"] == "uncertain":
            expected = {"event": "uncertain", "slot_id": request["slot_id"],
                        "status": "uncertain", "receipt_path": terminal["receipt_path"],
                        "receipt_sha256": terminal["receipt_sha256"]}
            if terminal != expected or receipt.get("artifact_kind") != "candidate_g_uncertain_response_receipt_v1":
                raise ValueError("Uncertain receipt differs.")
            results.append(_result(request, "uncertain",
                                   receipt_sha256=terminal["receipt_sha256"]))
            stopped, stop_reason = True, "uncertain"
            continue
        if receipt.get("artifact_kind") != "candidate_g_response_receipt_v1":
            raise ValueError("Native response receipt kind differs.")
        facts = guidance_collection._validated_normalized(
            receipt.get("response"), normalize(receipt.get("response"), destination), request)
        if receipt.get("normalized") != facts:
            raise ValueError("Receipt facts differ from native sidecar normalization.")
        expected = {"event": "result", "slot_id": request["slot_id"],
                    "status": facts["status"], "receipt_path": terminal["receipt_path"],
                    "receipt_sha256": terminal["receipt_sha256"]}
        if terminal != expected:
            raise ValueError("Result event differs from verified response receipt.")
        results.append(_result(request, facts["status"], facts=facts,
                               receipt_sha256=terminal["receipt_sha256"]))
        if facts["status"] != "complete":
            stopped = True
            stop_reason = "partial" if facts["status"] == "partial" else "uncertain"
    if cursor != len(events):
        raise ValueError("Events continue after stop or slot inventory.")
    saved = _read_json(destination / "collection.json")
    expected = _summary(prepared, results, stop_reason)
    if saved != expected:
        raise ValueError("Claimed collection summary differs from verified terminals.")
    if saved["status"] == "complete" and saved["counts"] != {"complete": 60}:
        raise ValueError("Only sixty complete responses can complete the collection.")
    return copy.deepcopy(expected)
