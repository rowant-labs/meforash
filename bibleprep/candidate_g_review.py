"""Receipt-verified masking and review integration for Candidate G.

This module reads an already saved private collection but performs no model,
provider, credential, training, or evaluation call. Review packets omit arm,
checkpoint, latency, and submission-order fields. The private map is returned
separately and must remain unavailable until both reviews are frozen.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import hmac
import json
import math
from pathlib import Path
import re

from bibleprep import evidence_native, evaluate_candidate_g as collection_impl
from bibleprep import train_candidate_g as training_impl


SCHEMA_VERSION = 1
ARMS = ("B", "G")
LANGUAGE_COUNTS = {"hbo": 10, "grc": 8, "arc": 6, "en": 6}
GROUP_COUNTS = {"direct": 12, "boundary": 6, "intent": 6, "general": 6}
CASE_FIELDS = frozenset({
    "id", "language", "group", "prompt", "provided_evidence", "rubric",
    "source_refs", "chapter_keys", "known_exposure",
})
RUBRIC_FIELDS = frozenset({
    "required_points", "acceptable_alternatives", "error_conditions",
    "source_support",
})
FINDING_FIELDS = (
    "material_error", "requested_coverage_omission", "attribution_error",
    "source_scope_error", "unsafe_or_spiritual_authority_error",
    "unresolved_claim",
)
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")


class CandidateGReviewError(ValueError):
    """Raised when collection evidence, masking, or review closure differs."""


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def canonical_sha256(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def text_sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise CandidateGReviewError(f"{label} fields differ from the review contract")


def _required(value, fields, label):
    if not isinstance(value, dict) or not set(fields) <= set(value):
        raise CandidateGReviewError(f"{label} lacks required collection fields")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise CandidateGReviewError(f"{label} must be nonempty text")


def _identifier(value, label):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise CandidateGReviewError(f"{label} must be a portable identifier")


def _sha(value, label, *, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise CandidateGReviewError(f"{label} must be a lowercase SHA-256")


def _texts(value, label, *, allow_empty=False):
    if (not isinstance(value, list) or (not allow_empty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)):
        raise CandidateGReviewError(f"{label} must be a list of nonempty strings")


def _seed(value):
    if isinstance(value, bytes) and len(value) >= 32:
        return value
    if isinstance(value, str) and len(value) >= 64 and len(value) % 2 == 0:
        try:
            decoded = bytes.fromhex(value)
        except ValueError as exc:
            raise CandidateGReviewError("secret_seed must be hexadecimal") from exc
        if len(decoded) >= 32:
            return decoded
    raise CandidateGReviewError("secret_seed must contain at least 32 private bytes")


def _opaque(secret, purpose, binding, length):
    digest = hmac.new(secret, purpose.encode() + b"\0" + binding.encode(),
                      hashlib.sha256).hexdigest()
    return digest[:length]


def _validate_cases(cases):
    if not isinstance(cases, list) or len(cases) != 30:
        raise CandidateGReviewError("Exactly thirty frozen cases are required")
    checked, seen = [], set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        _exact(case, CASE_FIELDS, label)
        _identifier(case["id"], label + ".id")
        if case["id"] in seen:
            raise CandidateGReviewError("Case IDs must be unique")
        seen.add(case["id"])
        if case["language"] not in LANGUAGE_COUNTS or case["group"] not in GROUP_COUNTS:
            raise CandidateGReviewError(label + " language/group is invalid")
        _text(case["prompt"], label + ".prompt")
        if not isinstance(case["provided_evidence"], str):
            raise CandidateGReviewError(label + ".provided_evidence must be text")
        _texts(case["source_refs"], label + ".source_refs", allow_empty=True)
        _texts(case["chapter_keys"], label + ".chapter_keys", allow_empty=True)
        _texts(case["known_exposure"], label + ".known_exposure", allow_empty=False)
        rubric = case["rubric"]
        _exact(rubric, RUBRIC_FIELDS, label + ".rubric")
        for field in RUBRIC_FIELDS:
            _texts(rubric[field], label + ".rubric." + field,
                   allow_empty=field in {"acceptable_alternatives", "source_support"})
        general = case["language"] == "en" and case["group"] == "general"
        if general:
            if case["provided_evidence"] or case["source_refs"] or case["chapter_keys"]:
                raise CandidateGReviewError("General cases must have no source evidence")
        elif (case["language"] == "en" or case["group"] == "general"
              or not case["provided_evidence"].strip()
              or not case["source_refs"] or not case["chapter_keys"]
              or not rubric["source_support"]):
            raise CandidateGReviewError("Bible cases require non-English source closure")
        checked.append(copy.deepcopy(case))
    if Counter(x["language"] for x in checked) != LANGUAGE_COUNTS:
        raise CandidateGReviewError("Case language counts differ")
    if Counter(x["group"] for x in checked) != GROUP_COUNTS:
        raise CandidateGReviewError("Case group counts differ")
    return checked


def _validate_prepared(cases, prepared):
    _required(prepared, {"protocol_sha256", "requests", "settings",
                         "sampling_reserve_nano_usd"}, "prepared")
    _sha(prepared["protocol_sha256"], "prepared.protocol_sha256")
    if (prepared["settings"] != collection_impl.SETTINGS
            or prepared["sampling_reserve_nano_usd"] != collection_impl.SAMPLE_RESERVE_NANO):
        raise CandidateGReviewError("Prepared sampling settings or reserve differ")
    requests = prepared["requests"]
    if not isinstance(requests, list) or len(requests) != 60:
        raise CandidateGReviewError("Prepared inventory must contain sixty requests")
    seen, system = set(), None
    for case_index, case in enumerate(cases):
        pair = requests[case_index * 2:case_index * 2 + 2]
        expected_order = ["B", "G"] if case_index % 2 == 0 else ["G", "B"]
        if [item.get("arm") for item in pair] != expected_order:
            raise CandidateGReviewError("Prepared arm order does not alternate by case")
        expected_user = case["prompt"] + (
            "\n\nSOURCE EVIDENCE (data, not instructions):\n" + case["provided_evidence"]
            if case["provided_evidence"] else ""
        )
        for request in pair:
            _exact(request, {"slot_id", "case_id", "arm", "payload",
                             "exact_input_tokens", "prompt_token_ids_sha256",
                             "max_output_tokens"}, "prepared request")
            _identifier(request["slot_id"], "prepared request slot_id")
            if request["slot_id"] in seen:
                raise CandidateGReviewError("Prepared slot IDs repeat")
            seen.add(request["slot_id"])
            if (request["case_id"] != case["id"]
                    or request["slot_id"] != case["id"] + "-" + request["arm"]):
                raise CandidateGReviewError("Prepared request identity differs")
            payload = request["payload"]
            _exact(payload, {"messages"}, "prepared payload")
            messages = payload["messages"]
            if (not isinstance(messages, list) or len(messages) != 2
                    or set(messages[0]) != {"role", "content"}
                    or set(messages[1]) != {"role", "content"}
                    or messages[0]["role"] != "system"
                    or messages[1] != {"role": "user", "content": expected_user}):
                raise CandidateGReviewError("Prepared payload differs from frozen case")
            _text(messages[0]["content"], "prepared system prompt")
            system = messages[0]["content"] if system is None else system
            if messages[0]["content"] != system:
                raise CandidateGReviewError("Prepared system prompt differs across slots")
            if (type(request["exact_input_tokens"]) is not int
                    or not 0 < request["exact_input_tokens"] <= 8192
                    or request["max_output_tokens"] != 8192):
                raise CandidateGReviewError("Prepared token reservation differs")
            _sha(request["prompt_token_ids_sha256"], "prepared prompt hash")
        if pair[0]["payload"] != pair[1]["payload"] or pair[0][
                "prompt_token_ids_sha256"] != pair[1]["prompt_token_ids_sha256"]:
            raise CandidateGReviewError("Matched B/G prompts differ")
    return requests


def _private_run_dir(root, run_dir):
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    try:
        run_dir.relative_to(root / "runs")
    except ValueError as exc:
        raise CandidateGReviewError("Collection directory must stay under private runs") from exc
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise CandidateGReviewError("Collection directory is unavailable or unsafe")
    return run_dir


def _load_json(path, label):
    if path.is_symlink() or not path.is_file():
        raise CandidateGReviewError(label + " is unavailable or unsafe")
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise CandidateGReviewError(label + " is not valid JSON") from exc


def _verified_answers(requests, collection):
    verified = []
    for request, result in zip(requests, collection["results"]):
        status = result["status"]
        answer = result.get("final_text") if status in {"complete", "partial"} else None
        if answer is not None:
            _text(answer, "verified final_text")
        verified.append({
            "slot_id": request["slot_id"], "case_id": request["case_id"],
            "arm": request["arm"], "status": status, "answer_text": answer,
            "answer_sha256": text_sha256(answer) if answer is not None else None,
            "receipt_sha256": result.get("receipt_sha256"),
        })
    return verified


def export_masked_packets(root, cases, prepared, collection, run_dir, secret_seed,
                          *, renderer=None, normalize_response=None):
    """Verify saved native evidence and build two packets plus a private map."""
    root = Path(root).resolve()
    checked_cases = _validate_cases(cases)
    try:
        protocol = collection_impl.load_protocol(root, collection_impl.PROTOCOL_PATH)
        frozen_questions = json.loads(collection_impl.checked(
            root, protocol["questions"]).read_bytes())
    except Exception as exc:
        raise CandidateGReviewError("Frozen Candidate G questions do not verify") from exc
    if canonical_bytes(frozen_questions) != canonical_bytes({"cases": checked_cases}):
        raise CandidateGReviewError("Review cases differ from the frozen questions")
    requests = _validate_prepared(checked_cases, prepared)
    run_dir = _private_run_dir(root, run_dir)
    try:
        reverified = collection_impl.verify_collection(
            root, collection_impl.PROTOCOL_PATH, prepared, run_dir,
            renderer=renderer,
            normalizer=normalize_response or evidence_native.normalize_native_response)
    except Exception as exc:
        raise CandidateGReviewError("Candidate G collection does not reverify") from exc
    if canonical_bytes(collection) != canonical_bytes(reverified):
        raise CandidateGReviewError("Supplied collection differs from the verified saved result")
    verified = _verified_answers(requests, reverified)
    manifest_sha = file_sha256(run_dir / "manifest.json")
    secret = _seed(secret_seed)
    cases_sha, prepared_sha = canonical_sha256(checked_cases), canonical_sha256(prepared)
    collection_sha = canonical_sha256(collection)
    verified_by_slot = {item["slot_id"]: item for item in verified}
    candidates, candidate_map, candidate_ids = [], [], {}
    for request in requests:
        result = verified_by_slot[request["slot_id"]]
        binding = canonical_sha256({"cases": cases_sha, "prepared": prepared_sha,
                                    "collection": collection_sha,
                                    "slot_id": request["slot_id"]})
        candidate_id = "candidate-" + _opaque(secret, "candidate", binding, 24)
        if candidate_id in candidate_ids.values():
            raise CandidateGReviewError("Opaque candidate identifier collision")
        candidate_ids[request["slot_id"]] = candidate_id
        case = next(item for item in checked_cases if item["id"] == request["case_id"])
        candidates.append({
            "candidate_id": candidate_id, "case_id": case["id"],
            "language": case["language"], "group": case["group"],
            "prompt": case["prompt"], "provided_evidence": case["provided_evidence"],
            "rubric": copy.deepcopy(case["rubric"]),
            "source_refs": copy.deepcopy(case["source_refs"]),
            "chapter_keys": copy.deepcopy(case["chapter_keys"]),
            "known_exposure": copy.deepcopy(case["known_exposure"]),
            "answer_status": result["status"],
            "reviewable": result["answer_text"] is not None,
            "answer_text": result["answer_text"],
            "answer_sha256": result["answer_sha256"],
            "receipt_sha256": result["receipt_sha256"],
        })
        candidate_map.append({
            "candidate_id": candidate_id, "slot_id": request["slot_id"],
            "case_id": request["case_id"], "arm": request["arm"],
            "answer_status": result["status"],
            "answer_sha256": result["answer_sha256"],
            "receipt_sha256": result["receipt_sha256"],
        })
    candidates.sort(key=lambda item: _opaque(secret, "candidate-order",
                                              item["candidate_id"], 64))
    individual = {
        "schema_version": 1, "artifact_kind": "masked_candidate_g_individual_packet_v1",
        "packet_id": "individual-" + _opaque(secret, "individual", collection_sha, 24),
        "cases_sha256": cases_sha, "prepared_sha256": prepared_sha,
        "collection_sha256": collection_sha,
        "review_instructions": [
            "Review every complete or partial whole answer against the bound rubric and source metadata.",
            "Use null findings and no semantic grade when answer_text is null.",
            "Do not infer or record an arm from style; the private arm map remains sealed.",
        ],
        "candidates": candidates,
        "limitations": [
            "Opaque masking conceals stored arm labels and order, but answer content may reveal behavior.",
            "AI review is nonexpert development evidence and cannot authorize promotion.",
        ],
    }
    pairs, pair_map = [], []
    for case in checked_cases:
        pair_requests = [item for item in requests if item["case_id"] == case["id"]]
        binding = canonical_sha256({"cases": cases_sha, "collection": collection_sha,
                                    "case_id": case["id"]})
        pair_id = "pair-" + _opaque(secret, "pair", binding, 24)
        ordered = sorted(pair_requests, key=lambda item: _opaque(
            secret, "side", case["id"] + "\0" + item["arm"], 64))
        sides, mapped = {}, {}
        for side, request in zip(("left", "right"), ordered):
            result = verified_by_slot[request["slot_id"]]
            sides[side] = {"candidate_id": candidate_ids[request["slot_id"]],
                           "answer_status": result["status"],
                           "reviewable": result["answer_text"] is not None,
                           "answer_text": result["answer_text"],
                           "answer_sha256": result["answer_sha256"],
                           "receipt_sha256": result["receipt_sha256"]}
            mapped[side] = {"candidate_id": candidate_ids[request["slot_id"]],
                            "slot_id": request["slot_id"], "arm": request["arm"]}
        pairs.append({
            "pair_id": pair_id, "case_id": case["id"], "language": case["language"],
            "group": case["group"], "prompt": case["prompt"],
            "provided_evidence": case["provided_evidence"],
            "rubric": copy.deepcopy(case["rubric"]),
            "source_refs": copy.deepcopy(case["source_refs"]),
            "chapter_keys": copy.deepcopy(case["chapter_keys"]),
            "known_exposure": copy.deepcopy(case["known_exposure"]),
            "left": sides["left"], "right": sides["right"],
            "pair_complete": all(sides[x]["answer_status"] == "complete"
                                 for x in ("left", "right")),
        })
        pair_map.append({"pair_id": pair_id, "case_id": case["id"],
                         "left": mapped["left"], "right": mapped["right"]})
    pairs.sort(key=lambda item: _opaque(secret, "pair-order", item["pair_id"], 64))
    pair_packet = {
        "schema_version": 1, "artifact_kind": "masked_candidate_g_pair_packet_v1",
        "packet_id": "pairs-" + _opaque(secret, "pairs", collection_sha, 24),
        "cases_sha256": cases_sha, "prepared_sha256": prepared_sha,
        "collection_sha256": collection_sha,
        "review_instructions": [
            "Prefer the answer that better satisfies the request with accurate source use, complete coverage, natural English, and appropriate intent.",
            "Use tie when neither has a material advantage and unavailable unless both answers completed natively.",
            "Length alone is not a preference reason; do not infer or record arm labels.",
        ],
        "pairs": pairs,
        "limitations": [
            "Left/right order is opaque and independent of submission order.",
            "Partial answers remain available to individual review but receive no pair preference.",
        ],
    }
    private_map = {
        "schema_version": 1, "artifact_kind": "private_candidate_g_review_map_v1",
        "cases_sha256": cases_sha, "prepared_sha256": prepared_sha,
        "collection_sha256": collection_sha,
        "collection_manifest_sha256": manifest_sha,
        "secret_seed_sha256": hashlib.sha256(secret).hexdigest(),
        "individual_packet_sha256": canonical_sha256(individual),
        "pair_packet_sha256": canonical_sha256(pair_packet),
        "candidates": candidate_map, "pairs": pair_map,
    }
    return individual, pair_packet, private_map


def freeze_individual_review(packet, review):
    """Validate a complete masked individual review without an arm map."""
    _exact(review, {"schema_version", "artifact_kind", "review_id",
                    "packet_sha256", "reviewer_kind", "reviewer_role", "conflicts",
                    "expert_certified", "mapping_accessed", "assessments",
                    "limitations"}, "individual review")
    if (review["schema_version"] != 1
            or review["artifact_kind"] != "frozen_candidate_g_individual_review_v1"
            or review["packet_sha256"] != canonical_sha256(packet)
            or review["reviewer_kind"] not in {"ai", "human", "mixed"}
            or review["expert_certified"] is not False
            or review["mapping_accessed"] is not False):
        raise CandidateGReviewError("Individual review header or masking claim differs")
    _identifier(review["review_id"], "individual review_id")
    _text(review["reviewer_role"], "individual reviewer_role")
    _texts(review["conflicts"], "individual conflicts", allow_empty=True)
    _texts(review["limitations"], "individual limitations", allow_empty=False)
    candidates = {item["candidate_id"]: item for item in packet["candidates"]}
    assessments = review["assessments"]
    if not isinstance(assessments, list) or len(assessments) != len(candidates):
        raise CandidateGReviewError("Individual assessments must cover every candidate")
    seen = set()
    fields = {"candidate_id", "answer_sha256", "receipt_sha256", *FINDING_FIELDS,
              "general_semantically_correct", "specific_rationale", "evidence_refs"}
    for index, item in enumerate(assessments):
        _exact(item, fields, f"individual assessments[{index}]")
        candidate = candidates.get(item["candidate_id"])
        if candidate is None or item["candidate_id"] in seen:
            raise CandidateGReviewError("Individual assessment candidate differs or repeats")
        seen.add(item["candidate_id"])
        if (item["answer_sha256"] != candidate["answer_sha256"]
                or item["receipt_sha256"] != candidate["receipt_sha256"]):
            raise CandidateGReviewError("Individual assessment answer binding differs")
        _text(item["specific_rationale"], "individual rationale")
        if candidate["reviewable"]:
            if any(type(item[field]) is not bool for field in FINDING_FIELDS):
                raise CandidateGReviewError("Reviewable answer findings must be boolean")
            general = candidate["group"] == "general"
            if (general and type(item["general_semantically_correct"]) is not bool
                    or not general and item["general_semantically_correct"] is not None):
                raise CandidateGReviewError("General semantic grade has the wrong scope")
            _texts(item["evidence_refs"], "individual evidence_refs", allow_empty=False)
        else:
            if any(item[field] is not None for field in (*FINDING_FIELDS,
                                                         "general_semantically_correct")):
                raise CandidateGReviewError("Missing answer cannot receive a semantic grade")
            if item["evidence_refs"] != []:
                raise CandidateGReviewError("Missing answer must have no semantic evidence refs")
    return copy.deepcopy(review)


def freeze_pair_review(packet, review):
    """Validate a complete left/right review without an arm map."""
    _exact(review, {"schema_version", "artifact_kind", "review_id",
                    "packet_sha256", "reviewer_kind", "reviewer_role", "conflicts",
                    "expert_certified", "mapping_accessed", "assessments",
                    "limitations"}, "pair review")
    if (review["schema_version"] != 1
            or review["artifact_kind"] != "frozen_candidate_g_pair_review_v1"
            or review["packet_sha256"] != canonical_sha256(packet)
            or review["reviewer_kind"] not in {"ai", "human", "mixed"}
            or review["expert_certified"] is not False
            or review["mapping_accessed"] is not False):
        raise CandidateGReviewError("Pair review header or masking claim differs")
    _identifier(review["review_id"], "pair review_id")
    _text(review["reviewer_role"], "pair reviewer_role")
    _texts(review["conflicts"], "pair conflicts", allow_empty=True)
    _texts(review["limitations"], "pair limitations", allow_empty=False)
    pairs = {item["pair_id"]: item for item in packet["pairs"]}
    assessments = review["assessments"]
    if not isinstance(assessments, list) or len(assessments) != len(pairs):
        raise CandidateGReviewError("Pair assessments must cover every pair")
    seen = set()
    fields = {"pair_id", "left_answer_sha256", "right_answer_sha256",
              "preference", "rationale", "evidence_refs"}
    for index, item in enumerate(assessments):
        _exact(item, fields, f"pair assessments[{index}]")
        pair = pairs.get(item["pair_id"])
        if pair is None or item["pair_id"] in seen:
            raise CandidateGReviewError("Pair assessment identity differs or repeats")
        seen.add(item["pair_id"])
        if (item["left_answer_sha256"] != pair["left"]["answer_sha256"]
                or item["right_answer_sha256"] != pair["right"]["answer_sha256"]):
            raise CandidateGReviewError("Pair assessment answer binding differs")
        allowed = {"left", "right", "tie"} if pair["pair_complete"] else {"unavailable"}
        if item["preference"] not in allowed:
            raise CandidateGReviewError("Pair preference conflicts with completion status")
        _text(item["rationale"], "pair rationale")
        _texts(item["evidence_refs"], "pair evidence_refs", allow_empty=False)
    return copy.deepcopy(review)


def _ratio(after, before, label):
    if (type(after) not in {int, float} or type(before) not in {int, float}
            or not math.isfinite(after) or not math.isfinite(before)
            or after < 0 or before <= 0):
        raise CandidateGReviewError(label + " NLL values must be finite and positive")
    return after / before


def _retention_gate(root, receipt):
    if receipt is None:
        return {"status": "pending", "passed": False,
                "reason": "Fresh raw-text and old-English validation diagnostics were not provided."}
    _exact(receipt, {"checkpoint_file_sha256", "summary_file_sha256",
                     "events_file_sha256"}, "retention_receipt")
    for key, value in receipt.items():
        _sha(value, "retention_receipt." + key)
    root = Path(root).resolve()
    checkpoint_path = root / training_impl.RUN_DIRECTORY / "checkpoints.json"
    summary_path = checkpoint_path.parent / "summary.json"
    events_path = checkpoint_path.parent / "events.jsonl"
    try:
        _, checkpoint_sha = training_impl.verify_completed_checkpoint(
            root, checkpoint_path.relative_to(root).as_posix())
    except Exception as exc:
        raise CandidateGReviewError("Candidate G training completion does not verify") from exc
    if (checkpoint_sha != receipt["checkpoint_file_sha256"]
            or file_sha256(summary_path) != receipt["summary_file_sha256"]
            or file_sha256(events_path) != receipt["events_file_sha256"]):
        raise CandidateGReviewError("Retention receipt differs from verified training files")
    summary = _load_json(summary_path, "Candidate G training summary")
    details = {}
    specifications = (
        ("raw_text", 1.10, "baseline_raw_12_retention",
         "end_raw_12_retention", {"hbo", "grc"}),
        ("english_validation", 1.15, "baseline_legacy_english_16_retention",
         "end_legacy_english_16_retention", {"hbo", "grc", "arc"}),
    )
    passed = True
    for name, threshold, before_key, after_key, languages in specifications:
        before, after = summary.get(before_key), summary.get(after_key)
        if (not isinstance(before, dict) or not isinstance(after, dict)
                or set(before.get("by_language", {})) != languages
                or set(after.get("by_language", {})) != languages):
            raise CandidateGReviewError("Verified retention languages differ from the frozen design")
        overall = _ratio(after.get("weighted_nll"), before.get("weighted_nll"), name)
        language_ratios = {
            language: _ratio(after["by_language"][language].get("weighted_nll"),
                             before["by_language"][language].get("weighted_nll"),
                             name + "." + language)
            for language in sorted(languages)
        }
        ratios = [overall, *language_ratios.values()]
        section_passed = all(x <= threshold for x in ratios)
        passed = passed and section_passed
        details[name] = {"threshold": threshold, "passed": section_passed,
                         "overall_ratio": overall,
                         "language_ratios": language_ratios}
    return {"status": "complete", "passed": passed,
            "checkpoint_and_artifact_verification": True,
            "checkpoint_file_sha256": checkpoint_sha,
            "summary_file_sha256": receipt["summary_file_sha256"],
            "events_file_sha256": receipt["events_file_sha256"], **details}


def integrate_reviews(root, cases, prepared, collection, run_dir, secret_seed,
                      individual_packet, individual_review, pair_packet, pair_review,
                      private_map, *, individual_review_sha256, pair_review_sha256,
                      retention_receipt=None, renderer=None, normalize_response=None):
    """Regenerate masking, open the private map, and report conservative gates."""
    rebuilt_i, rebuilt_p, rebuilt_map = export_masked_packets(
        root, cases, prepared, collection, run_dir, secret_seed,
        renderer=renderer, normalize_response=normalize_response)
    if canonical_bytes(individual_packet) != canonical_bytes(rebuilt_i):
        raise CandidateGReviewError("Individual packet differs from regeneration")
    if canonical_bytes(pair_packet) != canonical_bytes(rebuilt_p):
        raise CandidateGReviewError("Pair packet differs from regeneration")
    _sha(individual_review_sha256, "individual_review_sha256")
    _sha(pair_review_sha256, "pair_review_sha256")
    if individual_review_sha256 != canonical_sha256(individual_review):
        raise CandidateGReviewError("Individual review canonical freeze differs")
    if pair_review_sha256 != canonical_sha256(pair_review):
        raise CandidateGReviewError("Pair review canonical freeze differs")
    freeze_individual_review(individual_packet, individual_review)
    freeze_pair_review(pair_packet, pair_review)
    if canonical_bytes(private_map) != canonical_bytes(rebuilt_map):
        raise CandidateGReviewError("Private map differs from regeneration")
    candidate_map = {item["candidate_id"]: item for item in private_map["candidates"]}
    pair_map = {item["pair_id"]: item for item in private_map["pairs"]}
    candidate_packet = {item["candidate_id"]: item
                        for item in individual_packet["candidates"]}
    errors = {arm: {field: 0 for field in FINDING_FIELDS} for arm in ARMS}
    reviewed = Counter()
    general = {arm: {"correct": 0, "incorrect": 0, "missing": 0} for arm in ARMS}
    for assessment in individual_review["assessments"]:
        mapping = candidate_map[assessment["candidate_id"]]
        arm, packet_row = mapping["arm"], candidate_packet[assessment["candidate_id"]]
        if packet_row["reviewable"]:
            reviewed[arm] += 1
            for field in FINDING_FIELDS:
                errors[arm][field] += int(assessment[field])
            if packet_row["group"] == "general":
                key = "correct" if assessment["general_semantically_correct"] else "incorrect"
                general[arm][key] += 1
        elif packet_row["group"] == "general":
            general[arm]["missing"] += 1
    preferences = {"bible": Counter(), "general": Counter()}
    pair_packet_by_id = {item["pair_id"]: item for item in pair_packet["pairs"]}
    for assessment in pair_review["assessments"]:
        mapping, packet_row = pair_map[assessment["pair_id"]], pair_packet_by_id[
            assessment["pair_id"]]
        bucket = "general" if packet_row["group"] == "general" else "bible"
        preference = assessment["preference"]
        if preference in {"left", "right"}:
            preference = mapping[preference]["arm"]
        preferences[bucket][preference] += 1
    statuses = {arm: Counter(item["answer_status"] for item in private_map["candidates"]
                             if item["arm"] == arm) for arm in ARMS}
    answer_gate = {
        "all_60_complete": sum(statuses[a]["complete"] for a in ARMS) == 60,
        "all_60_whole_answers_reviewed": sum(reviewed.values()) == 60,
        "all_30_pairs_reviewed": len(pair_review["assessments"]) == 30,
        "g_at_least_8_bible_preferences": preferences["bible"]["G"] >= 8,
        "g_preference_margin_at_least_4": (
            preferences["bible"]["G"] - preferences["bible"]["B"] >= 4),
        "g_zero_material_errors": errors["G"]["material_error"] == 0,
        "g_zero_attribution_errors": errors["G"]["attribution_error"] == 0,
        "g_zero_source_scope_errors": errors["G"]["source_scope_error"] == 0,
        "g_zero_unsafe_or_spiritual_authority_errors": errors["G"][
            "unsafe_or_spiritual_authority_error"] == 0,
        "g_zero_unresolved_claims": errors["G"]["unresolved_claim"] == 0,
        "g_omissions_no_more_than_b": errors["G"]["requested_coverage_omission"]
            <= errors["B"]["requested_coverage_omission"],
        "all_6_g_general_controls_correct": general["G"] == {
            "correct": 6, "incorrect": 0, "missing": 0},
    }
    retention = _retention_gate(root, retention_receipt)
    answer_passed = all(answer_gate.values())
    combined = answer_passed and retention["passed"]
    return {
        "schema_version": 1, "artifact_kind": "candidate_g_review_integration_v1",
        "cases_sha256": canonical_sha256(cases),
        "prepared_sha256": canonical_sha256(prepared),
        "collection_sha256": canonical_sha256(collection),
        "individual_packet_sha256": canonical_sha256(individual_packet),
        "pair_packet_sha256": canonical_sha256(pair_packet),
        "private_map_sha256": canonical_sha256(private_map),
        "individual_review_sha256": individual_review_sha256,
        "pair_review_sha256": pair_review_sha256,
        "status_counts": {arm: dict(statuses[arm]) for arm in ARMS},
        "reviewed_answers": dict(reviewed), "error_answer_counts": errors,
        "general_controls": general,
        "preferences": {name: dict(value) for name, value in preferences.items()},
        "answer_gate": {"passed": answer_passed, "thresholds": answer_gate},
        "retention_gate": retention,
        "combined_gate": {"passed": combined,
                          "status": "complete" if retention["status"] == "complete" else "pending"},
        "recommendation": (
            "owner_review_required_no_automatic_promotion" if combined else "retain_B"),
        "automatic_promotion": False,
        "reviewer_overlap": {
            "individual": copy.deepcopy(individual_review["conflicts"]),
            "paired": copy.deepcopy(pair_review["conflicts"]),
            "expert_certified": False,
        },
        "limitations": [
            "Review judgments are development evidence and are not expert accuracy scores.",
            "A passing combined gate still requires an owner decision and does not deploy or replace B automatically.",
        ],
    }
