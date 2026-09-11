"""Build, freeze, and integrate a constructed offline blinded review.

The module has no model, network, environment, source-approval, or promotion
logic.  Candidate wording is copied exactly from the normalized collection
journal.  Concealment is procedural: answer content can reveal its treatment.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import hmac
import copy
import json
import os
from pathlib import Path
import re
import secrets

from bibleprep.evidence import ROOT, confined_path, sha256, strict_load
from bibleprep.evidence_collection import audit_collection, canonical_sha256


SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
REVIEWER_KINDS = frozenset({"ai", "human", "mixed"})


class BlindedReviewError(ValueError):
    """Raised when a packet, review, label map, or binding is invalid."""


def _exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise BlindedReviewError(f"{label} must be an object")
    actual = set(value)
    expected = set(expected)
    if actual != expected:
        raise BlindedReviewError(
            f"{label} fields differ; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _identifier(value, label):
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise BlindedReviewError(f"{label} must be a stable identifier")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise BlindedReviewError(f"{label} must be a nonempty string")


def _text_list(value, label, *, allow_empty=True):
    if (not isinstance(value, list) or (not allow_empty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)):
        qualifier = "" if allow_empty else "nonempty "
        raise BlindedReviewError(f"{label} must be a {qualifier}list of nonempty strings")


def _sha(value, label):
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise BlindedReviewError(f"{label} must be a lowercase SHA-256 digest")


def _criteria_cases(document):
    _exact_keys(document, {"schema_version", "suite_id", "fixture_kind", "cases"}, "criteria")
    if type(document["schema_version"]) is not int or document["schema_version"] != SCHEMA_VERSION:
        raise BlindedReviewError("Unsupported criteria schema_version")
    _identifier(document["suite_id"], "criteria.suite_id")
    if document["fixture_kind"] != "constructed":
        raise BlindedReviewError("Only constructed criteria are accepted")
    if not isinstance(document["cases"], list) or not document["cases"]:
        raise BlindedReviewError("criteria.cases must be a nonempty list")

    by_case = {}
    for index, case in enumerate(document["cases"]):
        label = f"criteria.cases[{index}]"
        _exact_keys(case, {
            "case_id", "question", "general_control", "scoring_criteria",
            "reviewer_instructions",
        }, label)
        _identifier(case["case_id"], label + ".case_id")
        if case["case_id"] in by_case:
            raise BlindedReviewError(f"Duplicate criteria case_id: {case['case_id']}")
        _text(case["question"], label + ".question")
        if type(case["general_control"]) is not bool:
            raise BlindedReviewError(label + ".general_control must be boolean")
        _text_list(case["scoring_criteria"], label + ".scoring_criteria", allow_empty=False)
        _text_list(case["reviewer_instructions"], label + ".reviewer_instructions")
        by_case[case["case_id"]] = case
    return by_case


def _validate_criteria(document, planned_slots):
    by_case = _criteria_cases(document)
    plan_cases = {}
    for index, slot in enumerate(planned_slots):
        if not isinstance(slot, dict):
            raise BlindedReviewError(f"planned_slots[{index}] must be an object")
        for field in ("case_id", "question", "general_control"):
            if field not in slot:
                raise BlindedReviewError(f"planned_slots[{index}] is missing {field}")
        if type(slot["general_control"]) is not bool:
            raise BlindedReviewError(f"planned_slots[{index}].general_control must be boolean")
        identity = (slot["question"], slot["general_control"])
        previous = plan_cases.setdefault(slot["case_id"], identity)
        if previous != identity:
            raise BlindedReviewError(f"Planned case metadata differs within case {slot['case_id']}")
    for case_id, (question, general_control) in plan_cases.items():
        case = by_case.get(case_id)
        if case is not None and (
                case["question"] != question or case["general_control"] is not general_control):
            raise BlindedReviewError(f"Criteria metadata does not match the plan for case {case_id}")
    if set(by_case) != set(plan_cases):
        raise BlindedReviewError("Criteria case IDs must exactly cover planned case IDs")
    return by_case


def _seed_bytes(seed):
    if seed is None:
        return secrets.token_bytes(32)
    if isinstance(seed, bytes) and len(seed) >= 32:
        return seed
    if isinstance(seed, str) and re.fullmatch(r"[0-9a-f]{64,}", seed) and len(seed) % 2 == 0:
        return bytes.fromhex(seed)
    raise BlindedReviewError("seed must be at least 32 secret bytes or 64 lowercase hex characters")


def _opaque(seed, purpose, binding):
    message = purpose.encode("ascii") + b"\0" + binding.encode("utf-8")
    return hmac.new(seed, message, hashlib.sha256).hexdigest()


def build_review_artifacts(planned_slots, journal, criteria, *, seed=None):
    """Return an arm-free review packet and a separate private label map.

    The optional seed exists for constructed tests.  Production callers should
    omit it so a fresh 256-bit system secret is generated.
    """
    audit = audit_collection(planned_slots, journal)
    criteria_by_case = _validate_criteria(criteria, planned_slots)
    if not audit["reviewable_answers"]:
        raise BlindedReviewError("The collection has no reviewable final answers")
    secret = _seed_bytes(seed)
    candidates = []
    mappings = []
    seen_ids = set()
    for answer in audit["reviewable_answers"]:
        binding = canonical_sha256({
            "planned_slots_sha256": audit["planned_slots_sha256"],
            "journal_sha256": audit["journal_sha256"],
            "slot_id": answer["slot_id"],
            "final_text_sha256": answer["final_text_sha256"],
            "receipt_sha256": answer["receipt_sha256"],
        })
        candidate_id = "candidate-" + _opaque(secret, "candidate-id", binding)[:24]
        if candidate_id in seen_ids:
            raise BlindedReviewError("Opaque candidate ID collision")
        seen_ids.add(candidate_id)
        case = criteria_by_case[answer["case_id"]]
        criteria_binding = {
            "case_id": case["case_id"],
            "question": case["question"],
            "general_control": case["general_control"],
            "scoring_criteria": case["scoring_criteria"],
            "reviewer_instructions": case["reviewer_instructions"],
        }
        candidates.append({
            "candidate_id": candidate_id,
            "case_id": answer["case_id"],
            "question": case["question"],
            "general_control": case["general_control"],
            "scoring_criteria": list(case["scoring_criteria"]),
            "reviewer_instructions": list(case["reviewer_instructions"]),
            "criteria_sha256": canonical_sha256(criteria_binding),
            "answer_status": answer["answer_status"],
            "stop_reason": answer["stop_reason"],
            "answer_text": answer["final_text"],
            "answer_sha256": answer["final_text_sha256"],
            "receipt_sha256": answer["receipt_sha256"],
        })
        mappings.append({
            "candidate_id": candidate_id,
            "slot_id": answer["slot_id"],
            "case_id": answer["case_id"],
            "arm": answer["arm"],
            "answer_status": answer["answer_status"],
            "stop_reason": answer["stop_reason"],
            "answer_sha256": answer["final_text_sha256"],
            "receipt_sha256": answer["receipt_sha256"],
        })

    candidates.sort(key=lambda item: _opaque(secret, "packet-order", item["candidate_id"]))
    packet = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "constructed_blinded_review_packet",
        "packet_id": "packet-" + _opaque(secret, "packet-id", audit["journal_sha256"])[:24],
        "fixture_kind": "constructed",
        "criteria_document_sha256": canonical_sha256(criteria),
        "criteria": copy.deepcopy(criteria),
        "paired_preference": "not_implemented",
        "review_instructions": [
            "Assess every candidate independently against its question and criteria.",
            "Record critical errors and requested-content omissions separately.",
            "Use general_semantic_pass true or false for general controls and null otherwise.",
        ],
        "candidates": candidates,
        "limitations": [
            "Candidate IDs and ordering conceal arm and plan position, but answer content can reveal the evidence treatment.",
            "This packet contains constructed fixtures and cannot establish model quality or expert certification.",
            "Paired preference judging is not implemented in this bounded workflow.",
        ],
    }
    label_map = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "private_blinded_review_label_map",
        "packet_sha256": canonical_sha256(packet),
        "planned_slots_sha256": audit["planned_slots_sha256"],
        "journal_sha256": audit["journal_sha256"],
        "criteria_document_sha256": canonical_sha256(criteria),
        "mapping_seed_hex": secret.hex(),
        "candidates": sorted(mappings, key=lambda item: item["candidate_id"]),
    }
    return packet, label_map


def _packet_rows(packet):
    _exact_keys(packet, {
        "schema_version", "artifact_kind", "packet_id", "fixture_kind",
        "criteria_document_sha256", "criteria", "paired_preference", "review_instructions",
        "candidates", "limitations",
    }, "packet")
    if (type(packet["schema_version"]) is not int or packet["schema_version"] != SCHEMA_VERSION
            or packet["artifact_kind"] != "constructed_blinded_review_packet"):
        raise BlindedReviewError("Unsupported review packet")
    _identifier(packet["packet_id"], "packet.packet_id")
    if packet["fixture_kind"] != "constructed" or packet["paired_preference"] != "not_implemented":
        raise BlindedReviewError("Packet must be constructed with paired preference not implemented")
    _sha(packet["criteria_document_sha256"], "packet.criteria_document_sha256")
    if canonical_sha256(packet["criteria"]) != packet["criteria_document_sha256"]:
        raise BlindedReviewError("Packet criteria document hash does not match")
    criteria_by_case = _criteria_cases(packet["criteria"])
    _text_list(packet["review_instructions"], "packet.review_instructions", allow_empty=False)
    _text_list(packet["limitations"], "packet.limitations", allow_empty=False)
    if not isinstance(packet["candidates"], list) or not packet["candidates"]:
        raise BlindedReviewError("packet.candidates must be a nonempty list")
    by_id = {}
    for index, row in enumerate(packet["candidates"]):
        label = f"packet.candidates[{index}]"
        _exact_keys(row, {
            "candidate_id", "case_id", "question", "general_control", "scoring_criteria",
            "reviewer_instructions", "criteria_sha256", "answer_status", "stop_reason",
            "answer_text", "answer_sha256", "receipt_sha256",
        }, label)
        _identifier(row["candidate_id"], label + ".candidate_id")
        _identifier(row["case_id"], label + ".case_id")
        if row["candidate_id"] in by_id:
            raise BlindedReviewError(f"Duplicate candidate_id: {row['candidate_id']}")
        _text(row["question"], label + ".question")
        if type(row["general_control"]) is not bool:
            raise BlindedReviewError(label + ".general_control must be boolean")
        _text_list(row["scoring_criteria"], label + ".scoring_criteria", allow_empty=False)
        _text_list(row["reviewer_instructions"], label + ".reviewer_instructions")
        if row["answer_status"] not in {"complete", "partial"}:
            raise BlindedReviewError(label + ".answer_status must be complete or partial")
        if row["stop_reason"] not in {"stop", "output_limit", "incomplete"}:
            raise BlindedReviewError(label + ".stop_reason is invalid")
        if not isinstance(row["answer_text"], str) or not row["answer_text"].strip():
            raise BlindedReviewError(label + ".answer_text must contain final content")
        _sha(row["criteria_sha256"], label + ".criteria_sha256")
        _sha(row["answer_sha256"], label + ".answer_sha256")
        _sha(row["receipt_sha256"], label + ".receipt_sha256")
        if hashlib.sha256(row["answer_text"].encode("utf-8")).hexdigest() != row["answer_sha256"]:
            raise BlindedReviewError(label + ".answer_sha256 does not bind exact answer text")
        criteria_binding = {key: row[key] for key in (
            "case_id", "question", "general_control", "scoring_criteria", "reviewer_instructions"
        )}
        if canonical_sha256(criteria_binding) != row["criteria_sha256"]:
            raise BlindedReviewError(label + ".criteria_sha256 does not match")
        criteria_case = criteria_by_case.get(row["case_id"])
        if criteria_case is None or any(
                row[field] != criteria_case[field] for field in (
                    "question", "general_control", "scoring_criteria", "reviewer_instructions"
                )):
            raise BlindedReviewError(label + " does not match the bound criteria document")
        by_id[row["candidate_id"]] = row
    return by_id


def _validate_packet_against_audit(packet, audit, planned_slots):
    _packet_rows(packet)
    _validate_criteria(packet["criteria"], planned_slots)
    actual = Counter((
        row["case_id"], row["answer_status"], row["stop_reason"], row["answer_text"],
        row["answer_sha256"], row["receipt_sha256"],
    ) for row in packet["candidates"])
    expected = Counter((
        row["case_id"], row["answer_status"], row["stop_reason"], row["final_text"],
        row["final_text_sha256"], row["receipt_sha256"],
    ) for row in audit["reviewable_answers"])
    if actual != expected:
        raise BlindedReviewError("Packet does not exactly cover the recomputed reviewable answers")


def _validate_review(packet, review):
    candidates = _packet_rows(packet)
    _exact_keys(review, {
        "schema_version", "artifact_kind", "review_id", "packet_sha256", "reviewer_kind",
        "reviewer_role", "conflicts", "expert_certified", "assessments", "limitations",
    }, "review")
    if (type(review["schema_version"]) is not int or review["schema_version"] != SCHEMA_VERSION
            or review["artifact_kind"] != "frozen_blinded_review"):
        raise BlindedReviewError("Unsupported review artifact")
    _identifier(review["review_id"], "review.review_id")
    _sha(review["packet_sha256"], "review.packet_sha256")
    if review["packet_sha256"] != canonical_sha256(packet):
        raise BlindedReviewError("Review packet hash does not match")
    if review["reviewer_kind"] not in REVIEWER_KINDS:
        raise BlindedReviewError("review.reviewer_kind is invalid")
    _text(review["reviewer_role"], "review.reviewer_role")
    _text_list(review["conflicts"], "review.conflicts")
    if review["expert_certified"] is not False:
        raise BlindedReviewError("This workflow cannot record expert certification")
    _text_list(review["limitations"], "review.limitations", allow_empty=False)
    if not isinstance(review["assessments"], list):
        raise BlindedReviewError("review.assessments must be a list")
    seen = set()
    for index, assessment in enumerate(review["assessments"]):
        label = f"review.assessments[{index}]"
        _exact_keys(assessment, {
            "candidate_id", "answer_sha256", "receipt_sha256", "critical_errors",
            "requested_content_omissions", "general_semantic_pass", "rationale",
        }, label)
        candidate_id = assessment["candidate_id"]
        _identifier(candidate_id, label + ".candidate_id")
        if candidate_id in seen:
            raise BlindedReviewError(f"Duplicate reviewed candidate_id: {candidate_id}")
        if candidate_id not in candidates:
            raise BlindedReviewError(f"Unknown reviewed candidate_id: {candidate_id}")
        seen.add(candidate_id)
        candidate = candidates[candidate_id]
        for field in ("answer_sha256", "receipt_sha256"):
            _sha(assessment[field], label + "." + field)
            if assessment[field] != candidate[field]:
                raise BlindedReviewError(f"{label}.{field} does not match packet")
        _text_list(assessment["critical_errors"], label + ".critical_errors")
        _text_list(assessment["requested_content_omissions"], label + ".requested_content_omissions")
        expected_semantic = bool if candidate["general_control"] else type(None)
        if type(assessment["general_semantic_pass"]) is not expected_semantic:
            required = "boolean" if candidate["general_control"] else "null"
            raise BlindedReviewError(f"{label}.general_semantic_pass must be {required}")
        _text(assessment["rationale"], label + ".rationale")
    if seen != set(candidates):
        raise BlindedReviewError("Review assessments must exactly cover the packet candidate set")
    return candidates


def _mkdir_private(path, root):
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists():
            if not current.is_dir() or current.is_symlink():
                raise BlindedReviewError(f"Private output ancestor is unsafe: {current}")
        else:
            os.mkdir(current, 0o700)


def _exclusive_json(path, document):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8") as output:
        json.dump(document, output, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")


def write_review_artifacts(packet, label_map, output_directory, root=ROOT):
    """Write a new private packet directory; never overwrite or follow symlinks."""
    root = Path(root).resolve()
    _packet_rows(packet)
    if label_map.get("packet_sha256") != canonical_sha256(packet):
        raise BlindedReviewError("Label map does not bind the packet")
    destination = confined_path(root, output_directory, ("runs",))
    if destination.exists():
        raise FileExistsError(destination)
    _mkdir_private(destination.parent, root)
    os.mkdir(destination, 0o700)
    packet_path = destination / "review-packet.json"
    map_path = destination / "private-label-map.json"
    _exclusive_json(packet_path, packet)
    _exclusive_json(map_path, label_map)
    return {
        "packet_path": packet_path.relative_to(root).as_posix(),
        "packet_file_sha256": sha256(packet_path),
        "label_map_path": map_path.relative_to(root).as_posix(),
        "label_map_file_sha256": sha256(map_path),
    }


def validate_and_freeze_review(packet, review, out_path, root=ROOT):
    """Validate exact coverage and exclusively create a private 0600 review file."""
    _validate_review(packet, review)
    root = Path(root).resolve()
    destination = confined_path(root, out_path, ("runs",))
    if destination.exists():
        raise FileExistsError(destination)
    _mkdir_private(destination.parent, root)
    _exclusive_json(destination, review)
    return {
        "review_path": destination.relative_to(root).as_posix(),
        "review_file_sha256": sha256(destination),
        "packet_sha256": canonical_sha256(packet),
        "candidate_count": len(packet["candidates"]),
    }


def _load_private_json(path, root, label):
    candidate = confined_path(root, path, ("runs",))
    if not candidate.is_file() or candidate.is_symlink():
        raise BlindedReviewError(f"{label} is missing or unsafe")
    return strict_load(candidate)


def _validate_label_map(label_map, packet, audit):
    _exact_keys(label_map, {
        "schema_version", "artifact_kind", "packet_sha256", "planned_slots_sha256",
        "journal_sha256", "criteria_document_sha256", "mapping_seed_hex", "candidates",
    }, "label_map")
    if (type(label_map["schema_version"]) is not int
            or label_map["schema_version"] != SCHEMA_VERSION
            or label_map["artifact_kind"] != "private_blinded_review_label_map"):
        raise BlindedReviewError("Unsupported label map")
    for field in ("packet_sha256", "planned_slots_sha256", "journal_sha256", "criteria_document_sha256"):
        _sha(label_map[field], "label_map." + field)
    if label_map["packet_sha256"] != canonical_sha256(packet):
        raise BlindedReviewError("Label map packet hash does not match")
    if label_map["planned_slots_sha256"] != audit["planned_slots_sha256"]:
        raise BlindedReviewError("Label map planned inventory hash does not match")
    if label_map["journal_sha256"] != audit["journal_sha256"]:
        raise BlindedReviewError("Label map journal hash does not match")
    if label_map["criteria_document_sha256"] != packet["criteria_document_sha256"]:
        raise BlindedReviewError("Label map criteria hash does not match")
    secret = _seed_bytes(label_map["mapping_seed_hex"])
    packet_by_id = _packet_rows(packet)
    if not isinstance(label_map["candidates"], list):
        raise BlindedReviewError("label_map.candidates must be a list")
    by_id = {}
    for index, row in enumerate(label_map["candidates"]):
        label = f"label_map.candidates[{index}]"
        _exact_keys(row, {
            "candidate_id", "slot_id", "case_id", "arm", "answer_status", "stop_reason",
            "answer_sha256", "receipt_sha256",
        }, label)
        for field in ("candidate_id", "case_id", "arm"):
            _identifier(row[field], label + "." + field)
        _text(row["slot_id"], label + ".slot_id")
        if row["candidate_id"] in by_id:
            raise BlindedReviewError(f"Duplicate label-map candidate_id: {row['candidate_id']}")
        for field in ("answer_sha256", "receipt_sha256"):
            _sha(row[field], label + "." + field)
        packet_row = packet_by_id.get(row["candidate_id"])
        if packet_row is None:
            raise BlindedReviewError("Label map contains an unknown candidate")
        for field in ("case_id", "answer_status", "stop_reason", "answer_sha256", "receipt_sha256"):
            if row[field] != packet_row[field]:
                raise BlindedReviewError(f"{label}.{field} does not match packet")
        by_id[row["candidate_id"]] = row
    if set(by_id) != set(packet_by_id):
        raise BlindedReviewError("Label map must exactly cover the packet candidate set")
    expected = {
        (row["slot_id"], row["case_id"], row["arm"], row["answer_status"],
         row["stop_reason"], row["final_text_sha256"], row["receipt_sha256"])
        for row in audit["reviewable_answers"]
    }
    actual = {
        (row["slot_id"], row["case_id"], row["arm"], row["answer_status"],
         row["stop_reason"], row["answer_sha256"], row["receipt_sha256"])
        for row in by_id.values()
    }
    if actual != expected:
        raise BlindedReviewError("Label map does not match the recomputed audit answers")
    for row in by_id.values():
        binding = canonical_sha256({
            "planned_slots_sha256": audit["planned_slots_sha256"],
            "journal_sha256": audit["journal_sha256"],
            "slot_id": row["slot_id"],
            "final_text_sha256": row["answer_sha256"],
            "receipt_sha256": row["receipt_sha256"],
        })
        expected_id = "candidate-" + _opaque(secret, "candidate-id", binding)[:24]
        if row["candidate_id"] != expected_id:
            raise BlindedReviewError("Label map candidate ID does not match its secret slot binding")
    expected_order = sorted(
        packet_by_id, key=lambda candidate_id: _opaque(secret, "packet-order", candidate_id)
    )
    if [row["candidate_id"] for row in packet["candidates"]] != expected_order:
        raise BlindedReviewError("Packet candidate order does not match the private mapping seed")
    expected_packet_id = "packet-" + _opaque(secret, "packet-id", audit["journal_sha256"])[:24]
    if packet["packet_id"] != expected_packet_id:
        raise BlindedReviewError("Packet ID does not match the private mapping seed")
    return by_id


def integrate_frozen_review(
        planned_slots, journal, packet, frozen_review_path, label_map_path, *,
        expected_frozen_review_file_sha256, root=ROOT,
        expected_label_map_file_sha256=None):
    """Integrate only after validating a frozen review, then reading its label map."""
    root = Path(root).resolve()
    audit = audit_collection(planned_slots, journal)
    _validate_packet_against_audit(packet, audit, planned_slots)

    # Ordering is deliberate: invalid review data must fail before label-map access.
    _sha(expected_frozen_review_file_sha256, "expected_frozen_review_file_sha256")
    frozen_path = confined_path(root, frozen_review_path, ("runs",))
    if not frozen_path.is_file() or frozen_path.is_symlink():
        raise BlindedReviewError("frozen review is missing or unsafe")
    if sha256(frozen_path) != expected_frozen_review_file_sha256:
        raise BlindedReviewError("Frozen review file hash does not match its freeze receipt")
    review = _load_private_json(frozen_review_path, root, "frozen review")
    packet_by_id = _validate_review(packet, review)
    if expected_label_map_file_sha256 is not None:
        _sha(expected_label_map_file_sha256, "expected_label_map_file_sha256")
        map_path = confined_path(root, label_map_path, ("runs",))
        if not map_path.is_file() or map_path.is_symlink():
            raise BlindedReviewError("label map is missing or unsafe")
        if sha256(map_path) != expected_label_map_file_sha256:
            raise BlindedReviewError("Label map file hash does not match its write receipt")
    label_map = _load_private_json(label_map_path, root, "label map")
    labels = _validate_label_map(label_map, packet, audit)
    assessments = {item["candidate_id"]: item for item in review["assessments"]}

    by_arm = {}
    for arm, collection_counts in audit["arms"].items():
        by_arm[arm] = {
            **collection_counts,
            "reviewed": 0,
            "critical_error_answers": 0,
            "requested_content_omission_answers": 0,
            "general_controls_planned": sum(
                1 for slot in planned_slots if slot["arm"] == arm and slot["general_control"]
            ),
            "general_controls_reviewed": 0,
            "general_semantic_pass": 0,
            "general_semantic_fail": 0,
        }
    for candidate_id, label in labels.items():
        counts = by_arm[label["arm"]]
        assessment = assessments[candidate_id]
        candidate = packet_by_id[candidate_id]
        counts["reviewed"] += 1
        counts["critical_error_answers"] += bool(assessment["critical_errors"])
        counts["requested_content_omission_answers"] += bool(
            assessment["requested_content_omissions"]
        )
        if candidate["general_control"]:
            counts["general_controls_reviewed"] += 1
            key = "general_semantic_pass" if assessment["general_semantic_pass"] else "general_semantic_fail"
            counts[key] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "constructed_blinded_review_integration",
        "planned_slots_sha256": audit["planned_slots_sha256"],
        "journal_sha256": audit["journal_sha256"],
        "packet_sha256": canonical_sha256(packet),
        "frozen_review_file_sha256": sha256(confined_path(root, frozen_review_path, ("runs",))),
        "label_map_file_sha256": sha256(confined_path(root, label_map_path, ("runs",))),
        "totals": {
            **audit["totals"],
            "reviewed": len(assessments),
            "critical_error_answers": sum(bool(row["critical_errors"]) for row in assessments.values()),
            "requested_content_omission_answers": sum(
                bool(row["requested_content_omissions"]) for row in assessments.values()
            ),
        },
        "arms": by_arm,
        "decision": "not_assessed_or_authorized",
        "expert_certified": False,
        "paired_preference": "not_implemented",
        "limitations": [
            "Counts use every planned slot as the arm denominator; missing output is not a semantic failure.",
            "All returned complete and partial final answers are reviewed; no model promotion is performed.",
            "Reviewer judgments and constructed fixtures do not establish expert certification or production quality.",
        ],
    }
