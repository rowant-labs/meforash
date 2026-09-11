"""Pure masking, review validation, and integration for guidance comparisons.

The functions in this module consume normalized offline data and return JSON
objects.  They do not read or write files, access environment variables or
credentials, contact a provider, run a model, freeze a protocol, or authorize
generation, training, or promotion.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import hmac
import json
import math
import re


SCHEMA_VERSION = 1
CONDITION_IDS = ("B-original", "B-guided")
RESULT_STATUSES = frozenset({"complete", "partial", "uncertain", "unsubmitted"})
REVIEWER_KINDS = frozenset({"ai", "human", "mixed"})
PAIR_PREFERENCES = frozenset({"left", "right", "tie", "unavailable"})
ATTRIBUTION_SCOPE_KINDS = frozenset({"attribution", "scope"})
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")

ACTUAL_EXPECTED_COUNTS = {
    "protocol_kind": "actual",
    "planned_answers": 16,
    "bible_cases": 6,
    "general_control_cases": 2,
}


class GuidanceReviewError(ValueError):
    """Raised when collection, packet, review, map, or freeze data is invalid."""


def _validate_json(value, label):
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GuidanceReviewError(f"{label} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise GuidanceReviewError(f"{label} has a non-string key")
            _validate_json(item, f"{label}.{key}")
        return
    raise GuidanceReviewError(f"{label} is not finite JSON data")


def _canonical_bytes(value):
    _validate_json(value, "value")
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value):
    """Return SHA-256 over canonical finite JSON UTF-8 bytes."""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _text_sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise GuidanceReviewError(f"{label} must be an object")
    actual = set(value)
    expected = set(expected)
    if actual != expected:
        raise GuidanceReviewError(
            f"{label} fields differ; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _required_keys(value, required, label):
    if not isinstance(value, dict):
        raise GuidanceReviewError(f"{label} must be an object")
    missing = set(required) - set(value)
    if missing:
        raise GuidanceReviewError(f"{label} is missing fields: {sorted(missing)}")


def _identifier(value, label):
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise GuidanceReviewError(f"{label} must be a stable identifier")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise GuidanceReviewError(f"{label} must be nonempty text")


def _text_list(value, label, *, allow_empty=True):
    if (not isinstance(value, list) or (not allow_empty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)):
        qualifier = "" if allow_empty else "nonempty "
        raise GuidanceReviewError(f"{label} must be a {qualifier}list of nonempty strings")


def _sha(value, label, *, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise GuidanceReviewError(f"{label} must be a lowercase SHA-256")


def _seed_bytes(secret_seed):
    if isinstance(secret_seed, bytes) and len(secret_seed) >= 32:
        return secret_seed
    if (isinstance(secret_seed, str) and len(secret_seed) >= 64
            and len(secret_seed) % 2 == 0 and re.fullmatch(r"[0-9a-f]+", secret_seed)):
        return bytes.fromhex(secret_seed)
    raise GuidanceReviewError(
        "secret_seed must be at least 32 bytes or 64 lowercase hexadecimal characters"
    )


def _opaque(secret, purpose, binding):
    message = purpose.encode("ascii") + b"\0" + binding.encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def _validate_plan(planned_slots):
    if not isinstance(planned_slots, list) or not planned_slots:
        raise GuidanceReviewError("planned_slots must be a nonempty list")
    _validate_json(planned_slots, "planned_slots")
    slots = {}
    cases = {}
    seen_pairs = set()
    for index, slot in enumerate(planned_slots):
        label = f"planned_slots[{index}]"
        _required_keys(
            slot, {"slot_id", "case_id", "condition_id", "general_control", "question"},
            label,
        )
        _text(slot["slot_id"], label + ".slot_id")
        _identifier(slot["case_id"], label + ".case_id")
        if slot["condition_id"] not in CONDITION_IDS:
            raise GuidanceReviewError(label + ".condition_id is invalid")
        if type(slot["general_control"]) is not bool:
            raise GuidanceReviewError(label + ".general_control must be boolean")
        _text(slot["question"], label + ".question")
        if slot["slot_id"] in slots:
            raise GuidanceReviewError(f"Duplicate planned slot_id: {slot['slot_id']}")
        pair = (slot["case_id"], slot["condition_id"])
        if pair in seen_pairs:
            raise GuidanceReviewError(
                f"Duplicate planned case/condition: {slot['case_id']} / {slot['condition_id']}"
            )
        seen_pairs.add(pair)
        slots[slot["slot_id"]] = slot
        identity = (slot["question"], slot["general_control"])
        prior = cases.setdefault(slot["case_id"], {"identity": identity, "slots": {}})
        if prior["identity"] != identity:
            raise GuidanceReviewError(
                f"Planned case metadata differs within case {slot['case_id']}"
            )
        prior["slots"][slot["condition_id"]] = slot
    for case_id, case in cases.items():
        if set(case["slots"]) != set(CONDITION_IDS):
            raise GuidanceReviewError(
                f"Case {case_id} must contain exactly both guidance conditions"
            )
    return slots, cases


def _validate_results(results, slots):
    if not isinstance(results, list):
        raise GuidanceReviewError("results must be a list")
    _validate_json(results, "results")
    by_slot = {}
    for index, result in enumerate(results):
        label = f"results[{index}]"
        _required_keys(
            result,
            {"slot_id", "status", "final_text", "final_text_sha256", "receipt_sha256"},
            label,
        )
        _text(result["slot_id"], label + ".slot_id")
        if result["slot_id"] in by_slot:
            raise GuidanceReviewError(f"Duplicate result slot_id: {result['slot_id']}")
        if result["slot_id"] not in slots:
            raise GuidanceReviewError(f"Unknown result slot_id: {result['slot_id']}")
        if result["status"] not in RESULT_STATUSES:
            raise GuidanceReviewError(label + ".status is invalid")
        final_text = result["final_text"]
        if final_text is not None and (not isinstance(final_text, str) or not final_text.strip()):
            raise GuidanceReviewError(label + ".final_text must be nonempty text or null")
        _sha(result["final_text_sha256"], label + ".final_text_sha256", nullable=True)
        _sha(result["receipt_sha256"], label + ".receipt_sha256", nullable=True)
        if final_text is None:
            if result["final_text_sha256"] is not None:
                raise GuidanceReviewError(label + ".final_text_sha256 requires final_text")
        elif _text_sha256(final_text) != result["final_text_sha256"]:
            raise GuidanceReviewError(label + ".final_text_sha256 does not match exact text")
        if result["status"] in {"complete", "partial"}:
            if final_text is None or result["receipt_sha256"] is None:
                raise GuidanceReviewError(
                    label + ".complete/partial result requires final text and receipt hash"
                )
        if result["status"] == "unsubmitted" and any(
                result[field] is not None
                for field in ("final_text", "final_text_sha256", "receipt_sha256")):
            raise GuidanceReviewError(label + ".unsubmitted result must have null output bindings")
        by_slot[result["slot_id"]] = result
    if set(by_slot) != set(slots):
        missing = sorted(set(slots) - set(by_slot))
        extra = sorted(set(by_slot) - set(slots))
        raise GuidanceReviewError(
            f"Results must exactly cover planned slots; missing={missing}, extra={extra}"
        )
    return by_slot


def _validate_criteria(criteria_by_case, cases):
    if not isinstance(criteria_by_case, dict):
        raise GuidanceReviewError("criteria_by_case must be an object keyed by case_id")
    if set(criteria_by_case) != set(cases):
        raise GuidanceReviewError("criteria_by_case must exactly cover planned case IDs")
    checked = {}
    for case_id, value in criteria_by_case.items():
        _identifier(case_id, f"criteria_by_case key {case_id!r}")
        label = f"criteria_by_case.{case_id}"
        _exact_keys(value, {
            "question", "general_control", "expected_coverage", "factual_criteria",
            "generic_evaluation_rules",
        }, label)
        _text(value["question"], label + ".question")
        if type(value["general_control"]) is not bool:
            raise GuidanceReviewError(label + ".general_control must be boolean")
        if (value["question"], value["general_control"]) != cases[case_id]["identity"]:
            raise GuidanceReviewError(label + " does not match planned case metadata")
        _text_list(value["expected_coverage"], label + ".expected_coverage", allow_empty=False)
        _text_list(
            value["generic_evaluation_rules"], label + ".generic_evaluation_rules",
            allow_empty=False,
        )
        if not isinstance(value["factual_criteria"], list):
            raise GuidanceReviewError(label + ".factual_criteria must be a list")
        if not value["general_control"] and not value["factual_criteria"]:
            raise GuidanceReviewError(label + ".factual_criteria must be nonempty for Bible cases")
        seen = set()
        for index, criterion in enumerate(value["factual_criteria"]):
            item_label = f"{label}.factual_criteria[{index}]"
            _exact_keys(criterion, {"criterion_id", "statement", "source_refs"}, item_label)
            _identifier(criterion["criterion_id"], item_label + ".criterion_id")
            if criterion["criterion_id"] in seen:
                raise GuidanceReviewError(
                    f"Duplicate criterion_id in {case_id}: {criterion['criterion_id']}"
                )
            seen.add(criterion["criterion_id"])
            _text(criterion["statement"], item_label + ".statement")
            _text_list(
                criterion["source_refs"], item_label + ".source_refs",
                allow_empty=value["general_control"],
            )
        checked[case_id] = copy.deepcopy(value)
    return checked


def _side_record(slot, result, side_code, candidate_id_by_slot):
    reviewable = result["final_text"] is not None
    return {
        "side_code": side_code,
        "candidate_id": candidate_id_by_slot.get(slot["slot_id"]),
        "answer_status": result["status"],
        "reviewable": reviewable,
        "answer_text": result["final_text"],
        "answer_sha256": result["final_text_sha256"],
        "receipt_sha256": result["receipt_sha256"],
    }


def build_masked_packets(
        planned_slots, results, criteria_by_case, secret_seed):
    """Build masked individual and pair packets plus a separate private map.

    The caller supplies the secret; this pure function never creates or stores
    external state.  Every nonempty returned final text, including partial or
    uncertain output, appears in the individual packet and relevant pair row.
    """
    slots, cases = _validate_plan(planned_slots)
    results_by_slot = _validate_results(results, slots)
    criteria = _validate_criteria(criteria_by_case, cases)
    secret = _seed_bytes(secret_seed)
    plan_sha = canonical_sha256(planned_slots)
    results_sha = canonical_sha256(results)
    criteria_sha = canonical_sha256(criteria_by_case)

    candidates = []
    candidate_mappings = []
    candidate_id_by_slot = {}
    for slot_id, slot in slots.items():
        result = results_by_slot[slot_id]
        if result["final_text"] is None:
            continue
        binding = canonical_sha256({
            "planned_slots_sha256": plan_sha,
            "results_sha256": results_sha,
            "slot_id": slot_id,
            "final_text_sha256": result["final_text_sha256"],
            "receipt_sha256": result["receipt_sha256"],
        })
        candidate_id = "candidate-" + _opaque(secret, "candidate-id", binding)[:24]
        if candidate_id in candidate_id_by_slot.values():
            raise GuidanceReviewError("Opaque candidate ID collision")
        candidate_id_by_slot[slot_id] = candidate_id
        case_criteria = criteria[slot["case_id"]]
        candidates.append({
            "candidate_id": candidate_id,
            "case_id": slot["case_id"],
            "question": slot["question"],
            "general_control": slot["general_control"],
            "expected_coverage": copy.deepcopy(case_criteria["expected_coverage"]),
            "factual_criteria": copy.deepcopy(case_criteria["factual_criteria"]),
            "generic_evaluation_rules": copy.deepcopy(
                case_criteria["generic_evaluation_rules"]
            ),
            "answer_status": result["status"],
            "answer_text": result["final_text"],
            "answer_sha256": result["final_text_sha256"],
            "receipt_sha256": result["receipt_sha256"],
        })
        candidate_mappings.append({
            "candidate_id": candidate_id,
            "slot_id": slot_id,
            "case_id": slot["case_id"],
            "condition_id": slot["condition_id"],
            "general_control": slot["general_control"],
            "answer_status": result["status"],
            "answer_sha256": result["final_text_sha256"],
            "receipt_sha256": result["receipt_sha256"],
        })
    candidates.sort(key=lambda row: _opaque(secret, "individual-order", row["candidate_id"]))

    individual_packet = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "masked_guidance_individual_packet_v1",
        "packet_id": "individual-" + _opaque(secret, "individual-packet", results_sha)[:24],
        "planned_slots_sha256": plan_sha,
        "results_sha256": results_sha,
        "criteria_sha256": criteria_sha,
        "review_instructions": [
            "Review every returned final answer independently, including partial and uncertain output.",
            "Record material errors, unsupported or unverified assertions, attribution or scope errors, and requested-content omissions separately, each with a reason and evidence references.",
            "Assess general semantic correctness only for general controls; use null for Bible cases.",
            "Do not infer a condition from answer style; candidate IDs and order are masked, though content can reveal treatment.",
        ],
        "candidates": candidates,
        "limitations": [
            "This packet excludes missing text from semantic review while the integration denominator retains every planned slot.",
            "Masking is procedural; answer content may reveal the treatment.",
            "Reviewer judgments do not establish expert accuracy or authorize promotion.",
        ],
    }

    pairs = []
    pair_mappings = []
    for case_id, case in cases.items():
        pair_binding = canonical_sha256({
            "planned_slots_sha256": plan_sha,
            "results_sha256": results_sha,
            "case_id": case_id,
        })
        pair_id = "pair-" + _opaque(secret, "pair-id", pair_binding)[:24]
        ordered = sorted(
            CONDITION_IDS,
            key=lambda condition: _opaque(
                secret, "side-order", case_id + "\0" + condition
            ),
        )
        sides = {}
        map_sides = {}
        for display_name, condition in zip(("left", "right"), ordered):
            slot = case["slots"][condition]
            result = results_by_slot[slot["slot_id"]]
            side_code = "side-" + _opaque(
                secret, "side-code", case_id + "\0" + condition
            )[:16]
            sides[display_name] = _side_record(
                slot, result, side_code, candidate_id_by_slot
            )
            map_sides[display_name] = {
                "side_code": side_code,
                "slot_id": slot["slot_id"],
                "condition_id": condition,
            }
        case_criteria = criteria[case_id]
        pairs.append({
            "pair_id": pair_id,
            "case_id": case_id,
            "question": case["identity"][0],
            "general_control": case["identity"][1],
            "expected_coverage": copy.deepcopy(case_criteria["expected_coverage"]),
            "factual_criteria": copy.deepcopy(case_criteria["factual_criteria"]),
            "generic_evaluation_rules": copy.deepcopy(
                case_criteria["generic_evaluation_rules"]
            ),
            "left": sides["left"],
            "right": sides["right"],
            "pair_complete": all(
                sides[name]["answer_status"] == "complete" for name in ("left", "right")
            ),
            "reviewable_side_count": sum(
                sides[name]["reviewable"] for name in ("left", "right")
            ),
        })
        pair_mappings.append({
            "pair_id": pair_id,
            "case_id": case_id,
            "general_control": case["identity"][1],
            "left": map_sides["left"],
            "right": map_sides["right"],
        })
    pairs.sort(key=lambda row: _opaque(secret, "pair-order", row["pair_id"]))
    pair_packet = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "masked_guidance_pair_packet_v1",
        "packet_id": "pairs-" + _opaque(secret, "pair-packet", results_sha)[:24],
        "planned_slots_sha256": plan_sha,
        "results_sha256": results_sha,
        "criteria_sha256": criteria_sha,
        "review_instructions": [
            "Compare left and right only after applying the bound case criteria.",
            "Use left, right, tie, or unavailable and give a rationale with evidence references.",
            "Use unavailable for general controls and whenever both sides are not complete; general correctness is judged separately in the individual review.",
        ],
        "pairs": pairs,
        "limitations": [
            "Opaque side assignment conceals condition and plan order, but answer content may reveal treatment.",
            "Partial text remains visible for review but cannot receive a pair preference.",
            "Preferences are development judgments, not expert accuracy scores.",
        ],
    }

    private_map = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "private_guidance_review_map_v1",
        "individual_packet_sha256": canonical_sha256(individual_packet),
        "pair_packet_sha256": canonical_sha256(pair_packet),
        "planned_slots_sha256": plan_sha,
        "results_sha256": results_sha,
        "criteria_sha256": criteria_sha,
        "secret_seed_sha256": hashlib.sha256(secret).hexdigest(),
        "candidates": sorted(candidate_mappings, key=lambda row: row["candidate_id"]),
        "pairs": sorted(pair_mappings, key=lambda row: row["pair_id"]),
    }
    return individual_packet, pair_packet, private_map


def _validate_packet_header(packet, kind, rows_field):
    _exact_keys(packet, {
        "schema_version", "artifact_kind", "packet_id", "planned_slots_sha256",
        "results_sha256", "criteria_sha256", "review_instructions", rows_field,
        "limitations",
    }, "packet")
    if type(packet["schema_version"]) is not int or packet["schema_version"] != SCHEMA_VERSION:
        raise GuidanceReviewError("Unsupported packet schema_version")
    if packet["artifact_kind"] != kind:
        raise GuidanceReviewError("Packet artifact_kind is invalid")
    _identifier(packet["packet_id"], "packet.packet_id")
    for field in ("planned_slots_sha256", "results_sha256", "criteria_sha256"):
        _sha(packet[field], "packet." + field)
    _text_list(packet["review_instructions"], "packet.review_instructions", allow_empty=False)
    _text_list(packet["limitations"], "packet.limitations", allow_empty=False)


def _validate_issue(issue, label, *, with_kind=False):
    expected = {"finding", "reason", "evidence_refs"}
    if with_kind:
        expected.add("error_kind")
    _exact_keys(issue, expected, label)
    if with_kind and issue["error_kind"] not in ATTRIBUTION_SCOPE_KINDS:
        raise GuidanceReviewError(label + ".error_kind is invalid")
    _text(issue["finding"], label + ".finding")
    _text(issue["reason"], label + ".reason")
    _text_list(issue["evidence_refs"], label + ".evidence_refs", allow_empty=False)


def _validate_review_header(review, kind, packet):
    _exact_keys(review, {
        "schema_version", "artifact_kind", "review_id", "packet_sha256",
        "reviewer_kind", "reviewer_role", "conflicts", "expert_certified",
        "assessments", "limitations",
    }, "review")
    if type(review["schema_version"]) is not int or review["schema_version"] != SCHEMA_VERSION:
        raise GuidanceReviewError("Unsupported review schema_version")
    if review["artifact_kind"] != kind:
        raise GuidanceReviewError("Review artifact_kind is invalid")
    _identifier(review["review_id"], "review.review_id")
    _sha(review["packet_sha256"], "review.packet_sha256")
    if review["packet_sha256"] != canonical_sha256(packet):
        raise GuidanceReviewError("Review packet hash does not match")
    if review["reviewer_kind"] not in REVIEWER_KINDS:
        raise GuidanceReviewError("review.reviewer_kind is invalid")
    _text(review["reviewer_role"], "review.reviewer_role")
    _text_list(review["conflicts"], "review.conflicts")
    if review["expert_certified"] is not False:
        raise GuidanceReviewError("This workflow cannot record expert certification")
    _text_list(review["limitations"], "review.limitations", allow_empty=False)
    if not isinstance(review["assessments"], list):
        raise GuidanceReviewError("review.assessments must be a list")


def validate_individual_review(packet, review):
    """Validate strict individual assessments and return them by candidate ID."""
    _validate_packet_header(
        packet, "masked_guidance_individual_packet_v1", "candidates"
    )
    if not isinstance(packet["candidates"], list):
        raise GuidanceReviewError("packet.candidates must be a list")
    candidates = {}
    for index, row in enumerate(packet["candidates"]):
        label = f"packet.candidates[{index}]"
        _exact_keys(row, {
            "candidate_id", "case_id", "question", "general_control",
            "expected_coverage", "factual_criteria", "generic_evaluation_rules",
            "answer_status", "answer_text", "answer_sha256", "receipt_sha256",
        }, label)
        _identifier(row["candidate_id"], label + ".candidate_id")
        if row["candidate_id"] in candidates:
            raise GuidanceReviewError("Duplicate packet candidate_id")
        _identifier(row["case_id"], label + ".case_id")
        _text(row["question"], label + ".question")
        if type(row["general_control"]) is not bool:
            raise GuidanceReviewError(label + ".general_control must be boolean")
        if row["answer_status"] not in {"complete", "partial", "uncertain"}:
            raise GuidanceReviewError(label + ".answer_status is not reviewable")
        _text(row["answer_text"], label + ".answer_text")
        _sha(row["answer_sha256"], label + ".answer_sha256")
        _sha(row["receipt_sha256"], label + ".receipt_sha256", nullable=True)
        if _text_sha256(row["answer_text"]) != row["answer_sha256"]:
            raise GuidanceReviewError(label + ".answer hash does not match")
        candidates[row["candidate_id"]] = row

    _validate_review_header(review, "frozen_guidance_individual_review_v1", packet)
    assessments = {}
    for index, assessment in enumerate(review["assessments"]):
        label = f"review.assessments[{index}]"
        _exact_keys(assessment, {
            "candidate_id", "answer_sha256", "receipt_sha256", "material_errors",
            "unsupported_or_unverified_assertions", "attribution_scope_errors",
            "omissions", "general_correctness", "rationale",
        }, label)
        candidate_id = assessment["candidate_id"]
        _identifier(candidate_id, label + ".candidate_id")
        if candidate_id in assessments:
            raise GuidanceReviewError("Duplicate individual assessment candidate_id")
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise GuidanceReviewError("Individual review contains unknown candidate_id")
        _sha(assessment["answer_sha256"], label + ".answer_sha256")
        _sha(assessment["receipt_sha256"], label + ".receipt_sha256", nullable=True)
        for field in ("answer_sha256", "receipt_sha256"):
            if assessment[field] != candidate[field]:
                raise GuidanceReviewError(f"{label}.{field} does not match packet")
        for field in (
                "material_errors", "unsupported_or_unverified_assertions", "omissions"):
            if not isinstance(assessment[field], list):
                raise GuidanceReviewError(f"{label}.{field} must be a list")
            for issue_index, issue in enumerate(assessment[field]):
                _validate_issue(issue, f"{label}.{field}[{issue_index}]")
        if not isinstance(assessment["attribution_scope_errors"], list):
            raise GuidanceReviewError(label + ".attribution_scope_errors must be a list")
        for issue_index, issue in enumerate(assessment["attribution_scope_errors"]):
            _validate_issue(
                issue, f"{label}.attribution_scope_errors[{issue_index}]", with_kind=True
            )
        correctness = assessment["general_correctness"]
        if candidate["general_control"]:
            _exact_keys(correctness, {"correct", "reason", "evidence_refs"},
                        label + ".general_correctness")
            if type(correctness["correct"]) is not bool:
                raise GuidanceReviewError(label + ".general_correctness.correct must be boolean")
            _text(correctness["reason"], label + ".general_correctness.reason")
            _text_list(
                correctness["evidence_refs"],
                label + ".general_correctness.evidence_refs", allow_empty=False,
            )
        elif correctness is not None:
            raise GuidanceReviewError(label + ".general_correctness must be null for Bible cases")
        _text(assessment["rationale"], label + ".rationale")
        assessments[candidate_id] = assessment
    if set(assessments) != set(candidates):
        raise GuidanceReviewError(
            "Individual review assessments must exactly cover packet candidates"
        )
    return assessments


def validate_pair_review(packet, review):
    """Validate strict pair preferences and return them by opaque pair ID."""
    _validate_packet_header(packet, "masked_guidance_pair_packet_v1", "pairs")
    if not isinstance(packet["pairs"], list) or not packet["pairs"]:
        raise GuidanceReviewError("packet.pairs must be a nonempty list")
    pairs = {}
    for index, pair in enumerate(packet["pairs"]):
        label = f"packet.pairs[{index}]"
        _exact_keys(pair, {
            "pair_id", "case_id", "question", "general_control", "expected_coverage",
            "factual_criteria", "generic_evaluation_rules", "left", "right",
            "pair_complete", "reviewable_side_count",
        }, label)
        _identifier(pair["pair_id"], label + ".pair_id")
        if pair["pair_id"] in pairs:
            raise GuidanceReviewError("Duplicate packet pair_id")
        _identifier(pair["case_id"], label + ".case_id")
        _text(pair["question"], label + ".question")
        if type(pair["general_control"]) is not bool:
            raise GuidanceReviewError(label + ".general_control must be boolean")
        for side_name in ("left", "right"):
            side = pair[side_name]
            side_label = label + "." + side_name
            _exact_keys(side, {
                "side_code", "candidate_id", "answer_status", "reviewable",
                "answer_text", "answer_sha256", "receipt_sha256",
            }, side_label)
            _identifier(side["side_code"], side_label + ".side_code")
            if side["candidate_id"] is not None:
                _identifier(side["candidate_id"], side_label + ".candidate_id")
            if side["answer_status"] not in RESULT_STATUSES:
                raise GuidanceReviewError(side_label + ".answer_status is invalid")
            if type(side["reviewable"]) is not bool:
                raise GuidanceReviewError(side_label + ".reviewable must be boolean")
            expected_reviewable = side["answer_text"] is not None
            if side["reviewable"] is not expected_reviewable:
                raise GuidanceReviewError(side_label + ".reviewable disagrees with answer_text")
            if expected_reviewable:
                _text(side["answer_text"], side_label + ".answer_text")
                _sha(side["answer_sha256"], side_label + ".answer_sha256")
                if _text_sha256(side["answer_text"]) != side["answer_sha256"]:
                    raise GuidanceReviewError(side_label + ".answer hash does not match")
                if side["candidate_id"] is None:
                    raise GuidanceReviewError(side_label + ".reviewable side lacks candidate_id")
            elif any(side[field] is not None for field in ("candidate_id", "answer_sha256")):
                raise GuidanceReviewError(side_label + ".missing side has answer bindings")
            _sha(side["receipt_sha256"], side_label + ".receipt_sha256", nullable=True)
        expected_complete = all(
            pair[name]["answer_status"] == "complete" for name in ("left", "right")
        )
        expected_reviewable_count = sum(pair[name]["reviewable"] for name in ("left", "right"))
        if pair["pair_complete"] is not expected_complete:
            raise GuidanceReviewError(label + ".pair_complete is incorrect")
        if type(pair["reviewable_side_count"]) is not int or (
                pair["reviewable_side_count"] != expected_reviewable_count):
            raise GuidanceReviewError(label + ".reviewable_side_count is incorrect")
        pairs[pair["pair_id"]] = pair

    _validate_review_header(review, "frozen_guidance_pair_review_v1", packet)
    assessments = {}
    for index, assessment in enumerate(review["assessments"]):
        label = f"review.assessments[{index}]"
        _exact_keys(assessment, {
            "pair_id", "left_answer_sha256", "right_answer_sha256", "preference",
            "rationale", "evidence_refs",
        }, label)
        pair_id = assessment["pair_id"]
        _identifier(pair_id, label + ".pair_id")
        if pair_id in assessments:
            raise GuidanceReviewError("Duplicate pair assessment pair_id")
        pair = pairs.get(pair_id)
        if pair is None:
            raise GuidanceReviewError("Pair review contains unknown pair_id")
        for side in ("left", "right"):
            field = side + "_answer_sha256"
            _sha(assessment[field], label + "." + field, nullable=True)
            if assessment[field] != pair[side]["answer_sha256"]:
                raise GuidanceReviewError(f"{label}.{field} does not match packet")
        if assessment["preference"] not in PAIR_PREFERENCES:
            raise GuidanceReviewError(label + ".preference is invalid")
        if (pair["general_control"] or not pair["pair_complete"]):
            if assessment["preference"] != "unavailable":
                raise GuidanceReviewError(
                    label + ".preference must be unavailable for control/incomplete pair"
                )
        _text(assessment["rationale"], label + ".rationale")
        _text_list(assessment["evidence_refs"], label + ".evidence_refs", allow_empty=False)
        assessments[pair_id] = assessment
    if set(assessments) != set(pairs):
        raise GuidanceReviewError("Pair review assessments must exactly cover packet pairs")
    return assessments


def freeze_review(packet, review):
    """Validate a review and return its canonical in-memory freeze binding."""
    if not isinstance(packet, dict):
        raise GuidanceReviewError("packet must be an object")
    kind = packet.get("artifact_kind")
    if kind == "masked_guidance_individual_packet_v1":
        assessments = validate_individual_review(packet, review)
        review_kind = "individual"
    elif kind == "masked_guidance_pair_packet_v1":
        assessments = validate_pair_review(packet, review)
        review_kind = "pair"
    else:
        raise GuidanceReviewError("Unsupported packet for review freeze")
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "guidance_review_canonical_freeze_v1",
        "review_kind": review_kind,
        "packet_sha256": canonical_sha256(packet),
        "review_sha256": canonical_sha256(review),
        "assessment_count": len(assessments),
    }


def _expected_counts(value):
    if value is None:
        return copy.deepcopy(ACTUAL_EXPECTED_COUNTS)
    _exact_keys(value, {
        "protocol_kind", "planned_answers", "bible_cases", "general_control_cases",
    }, "expected_counts")
    if value["protocol_kind"] not in {"actual", "constructed_fixture"}:
        raise GuidanceReviewError("expected_counts.protocol_kind is invalid")
    for field in ("planned_answers", "bible_cases", "general_control_cases"):
        if type(value[field]) is not int or value[field] < 0:
            raise GuidanceReviewError("expected_counts." + field + " must be nonnegative integer")
    if value["protocol_kind"] == "actual" and value != ACTUAL_EXPECTED_COUNTS:
        raise GuidanceReviewError("Actual protocol expected counts cannot weaken the frozen default")
    if value["planned_answers"] != 2 * (
            value["bible_cases"] + value["general_control_cases"]):
        raise GuidanceReviewError("expected_counts do not describe a two-condition inventory")
    if value["planned_answers"] <= 0 or value["bible_cases"] <= 0:
        raise GuidanceReviewError("expected_counts must include planned answers and Bible cases")
    return copy.deepcopy(value)


def _presence(assessment, field, *, kind=None):
    values = assessment[field]
    if kind is None:
        return bool(values)
    return any(item["error_kind"] == kind for item in values)


def integrate_reviews(
        planned_slots, results, criteria_by_case, individual_packet, individual_review,
        pair_packet, pair_review, private_map, secret_seed, *,
        individual_review_sha256, pair_review_sha256, expected_counts=None):
    """Integrate frozen reviews only after all public bindings validate.

    Review structure and caller-supplied freeze hashes are checked before the
    private map is compared or used.  Missing output stays in denominators and
    never becomes a semantic error.
    """
    expected = _expected_counts(expected_counts)
    slots, cases = _validate_plan(planned_slots)
    results_by_slot = _validate_results(results, slots)
    _validate_criteria(criteria_by_case, cases)
    actual_bible_cases = sum(not case["identity"][1] for case in cases.values())
    actual_control_cases = len(cases) - actual_bible_cases
    if (len(planned_slots), actual_bible_cases, actual_control_cases) != (
            expected["planned_answers"], expected["bible_cases"],
            expected["general_control_cases"]):
        raise GuidanceReviewError("Planned inventory does not match declared expected counts")

    rebuilt_individual, rebuilt_pair, rebuilt_map = build_masked_packets(
        planned_slots, results, criteria_by_case, secret_seed
    )
    if _canonical_bytes(individual_packet) != _canonical_bytes(rebuilt_individual):
        raise GuidanceReviewError("Individual packet differs from deterministic regeneration")
    if _canonical_bytes(pair_packet) != _canonical_bytes(rebuilt_pair):
        raise GuidanceReviewError("Pair packet differs from deterministic regeneration")

    # Deliberately validate public review data and freeze bindings before map use.
    individual_assessments = validate_individual_review(individual_packet, individual_review)
    pair_assessments = validate_pair_review(pair_packet, pair_review)
    _sha(individual_review_sha256, "individual_review_sha256")
    _sha(pair_review_sha256, "pair_review_sha256")
    if canonical_sha256(individual_review) != individual_review_sha256:
        raise GuidanceReviewError("Individual review differs from its canonical freeze")
    if canonical_sha256(pair_review) != pair_review_sha256:
        raise GuidanceReviewError("Pair review differs from its canonical freeze")

    if _canonical_bytes(private_map) != _canonical_bytes(rebuilt_map):
        raise GuidanceReviewError("Private map differs from deterministic regeneration")

    candidate_map = {row["candidate_id"]: row for row in private_map["candidates"]}
    pair_map = {row["pair_id"]: row for row in private_map["pairs"]}
    status_counts = Counter(result["status"] for result in results_by_slot.values())
    totals = {
        "planned": len(planned_slots),
        "complete": status_counts["complete"],
        "partial": status_counts["partial"],
        "uncertain": status_counts["uncertain"],
        "unsubmitted": status_counts["unsubmitted"],
        "reviewable": sum(result["final_text"] is not None for result in results_by_slot.values()),
        "reviewed": len(individual_assessments),
    }
    by_condition = {}
    for condition in CONDITION_IDS:
        condition_results = [
            results_by_slot[slot_id] for slot_id, slot in slots.items()
            if slot["condition_id"] == condition
        ]
        counts = Counter(result["status"] for result in condition_results)
        by_condition[condition] = {
            "planned": len(condition_results),
            "complete": counts["complete"],
            "partial": counts["partial"],
            "uncertain": counts["uncertain"],
            "unsubmitted": counts["unsubmitted"],
            "reviewable": sum(result["final_text"] is not None for result in condition_results),
            "reviewed": 0,
            "material_error_answers": 0,
            "unsupported_or_unverified_assertion_answers": 0,
            "attribution_error_answers": 0,
            "scope_error_answers": 0,
            "omission_answers": 0,
            "general_correct": 0,
            "general_incorrect": 0,
        }
    for candidate_id, assessment in individual_assessments.items():
        mapping = candidate_map[candidate_id]
        row = by_condition[mapping["condition_id"]]
        row["reviewed"] += 1
        row["material_error_answers"] += _presence(assessment, "material_errors")
        row["unsupported_or_unverified_assertion_answers"] += _presence(
            assessment, "unsupported_or_unverified_assertions"
        )
        row["attribution_error_answers"] += _presence(
            assessment, "attribution_scope_errors", kind="attribution"
        )
        row["scope_error_answers"] += _presence(
            assessment, "attribution_scope_errors", kind="scope"
        )
        row["omission_answers"] += _presence(assessment, "omissions")
        if assessment["general_correctness"] is not None:
            if assessment["general_correctness"]["correct"]:
                row["general_correct"] += 1
            else:
                row["general_incorrect"] += 1

    complete_bible_pairs = 0
    matched_complete_cases = []
    preferences = {"B-original": 0, "B-guided": 0, "tie": 0, "unavailable": 0}
    regressions = {
        "material_error_pairs": 0,
        "unsupported_or_unverified_assertion_pairs": 0,
        "attribution_error_pairs": 0,
        "scope_error_pairs": 0,
        "omission_pairs": 0,
    }
    shared_findings = {
        "material_error_pairs": 0,
        "unsupported_or_unverified_assertion_pairs": 0,
        "attribution_error_pairs": 0,
        "scope_error_pairs": 0,
        "omission_pairs": 0,
    }
    matched_omission_answers = {"B-original": 0, "B-guided": 0}
    for pair_id, pair_assessment in pair_assessments.items():
        mapping = pair_map[pair_id]
        if mapping["general_control"]:
            continue
        condition_for_side = {
            "left": mapping["left"]["condition_id"],
            "right": mapping["right"]["condition_id"],
        }
        preference = pair_assessment["preference"]
        preferences[
            condition_for_side[preference] if preference in {"left", "right"} else preference
        ] += 1
        case_slots = cases[mapping["case_id"]]["slots"]
        if all(
                results_by_slot[case_slots[condition]["slot_id"]]["status"] == "complete"
                for condition in CONDITION_IDS):
            complete_bible_pairs += 1
            matched_complete_cases.append(mapping["case_id"])
            assessments = {}
            for condition in CONDITION_IDS:
                slot_id = case_slots[condition]["slot_id"]
                candidate_id = next(
                    row["candidate_id"] for row in private_map["candidates"]
                    if row["slot_id"] == slot_id
                )
                assessments[condition] = individual_assessments[candidate_id]
            original = assessments["B-original"]
            guided = assessments["B-guided"]
            comparisons = {
                "material_error_pairs": (
                    _presence(guided, "material_errors"),
                    _presence(original, "material_errors"),
                ),
                "unsupported_or_unverified_assertion_pairs": (
                    _presence(guided, "unsupported_or_unverified_assertions"),
                    _presence(original, "unsupported_or_unverified_assertions"),
                ),
                "attribution_error_pairs": (
                    _presence(guided, "attribution_scope_errors", kind="attribution"),
                    _presence(original, "attribution_scope_errors", kind="attribution"),
                ),
                "scope_error_pairs": (
                    _presence(guided, "attribution_scope_errors", kind="scope"),
                    _presence(original, "attribution_scope_errors", kind="scope"),
                ),
                "omission_pairs": (
                    _presence(guided, "omissions"),
                    _presence(original, "omissions"),
                ),
            }
            for key, (guided_has, original_has) in comparisons.items():
                regressions[key] += guided_has and not original_has
                shared_findings[key] += guided_has and original_has
            for condition, assessment in assessments.items():
                matched_omission_answers[condition] += _presence(assessment, "omissions")

    general = {
        "planned_answers": 2 * actual_control_cases,
        "reviewable_answers": 0,
        "correct_answers": 0,
        "incorrect_answers": 0,
        "missing_or_unreviewable_answers": 0,
    }
    for slot_id, slot in slots.items():
        if not slot["general_control"]:
            continue
        result = results_by_slot[slot_id]
        if result["final_text"] is None:
            general["missing_or_unreviewable_answers"] += 1
            continue
        general["reviewable_answers"] += 1
        candidate_id = next(
            row["candidate_id"] for row in private_map["candidates"]
            if row["slot_id"] == slot_id
        )
        correctness = individual_assessments[candidate_id]["general_correctness"]["correct"]
        if correctness:
            general["correct_answers"] += 1
        else:
            general["incorrect_answers"] += 1

    pair_preferences_complete = (
        preferences["unavailable"] == 0 and
        sum(preferences.values()) == actual_bible_cases
    )
    gates = {
        "actual_protocol_counts_required": expected["protocol_kind"] == "actual",
        "all_expected_answers_complete": (
            totals["planned"] == expected["planned_answers"]
            and totals["complete"] == expected["planned_answers"]
        ),
        "all_expected_bible_pairs_complete": complete_bible_pairs == expected["bible_cases"],
        "all_complete_bible_pairs_have_preference": pair_preferences_complete,
        "no_guided_material_error_answers": (
            by_condition["B-guided"]["material_error_answers"] == 0
        ),
        "no_guided_unresolved_material_assertions": (
            by_condition["B-guided"]["unsupported_or_unverified_assertion_answers"] == 0
        ),
        "no_guided_attribution_or_scope_error_answers": (
            by_condition["B-guided"]["attribution_error_answers"] == 0
            and by_condition["B-guided"]["scope_error_answers"] == 0
        ),
        "no_guided_requested_content_omission_answers": (
            by_condition["B-guided"]["omission_answers"] == 0
        ),
        "guided_bible_pair_wins_exceed_losses": (
            preferences["B-guided"] > preferences["B-original"]
        ),
        "all_general_controls_semantically_correct": (
            general["correct_answers"] == general["planned_answers"]
            and general["incorrect_answers"] == 0
            and general["missing_or_unreviewable_answers"] == 0
        ),
    }
    gate_passed = all(gates.values())
    if expected["protocol_kind"] != "actual":
        recommendation = "constructed_fixture_descriptive_only"
    elif not gates["all_expected_answers_complete"] or not gates[
            "all_expected_bible_pairs_complete"]:
        recommendation = "inconclusive_collection_incomplete"
    elif gate_passed:
        recommendation = "proposed_limited_private_trial_gate_passed"
    else:
        recommendation = "retain_original_guidance_and_diagnose"

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "guidance_review_integration_v1",
        "status": "integrated_development_judgments",
        "expected_counts": expected,
        "totals": totals,
        "conditions": by_condition,
        "bible_pairs": {
            "planned": actual_bible_cases,
            "complete": complete_bible_pairs,
            "incomplete": actual_bible_cases - complete_bible_pairs,
            "matched_complete_case_ids": sorted(matched_complete_cases),
            "preferences": preferences,
            "regressions": regressions,
            "shared_findings": shared_findings,
            "relative_counter_method": "Per-case answer-level presence only; these counters do not match unique semantic findings across answers.",
            "matched_complete_omission_answers": matched_omission_answers,
        },
        "general_controls": general,
        "promotion_gate": {
            "thresholds": gates,
            "passed": gate_passed,
            "recommendation": recommendation,
            "authorization_granted": False,
        },
        "bindings": {
            "planned_slots_sha256": canonical_sha256(planned_slots),
            "results_sha256": canonical_sha256(results),
            "criteria_sha256": canonical_sha256(criteria_by_case),
            "individual_packet_sha256": canonical_sha256(individual_packet),
            "pair_packet_sha256": canonical_sha256(pair_packet),
            "individual_review_sha256": individual_review_sha256,
            "pair_review_sha256": pair_review_sha256,
            "private_map_sha256": canonical_sha256(private_map),
        },
        "expert_certified": False,
        "limitations": [
            "Missing or unreviewable output remains in collection denominators and is not counted as a semantic failure.",
            "All returned final text, including partial and uncertain output, is individually reviewed; pair preferences require two complete answers.",
            "AI or mixed reviewer judgments do not establish expert accuracy, whole-Bible quality, public readiness, or deployment authorization.",
            "The gate is comparative: a finding shared by both conditions is reported separately and still limits absolute readiness even when it is not a newly introduced regression.",
            "The promotion gate is deliberately stricter than the descriptive relative counters: any guided material error, unresolved material assertion, attribution/scope error, or requested-content omission fails it.",
            "A passing proposed gate supports only the separately bounded limited private trial and never performs promotion automatically.",
            "Constructed fixtures exercise validation and counters only; they cannot pass the actual-protocol promotion gate or recommend a trial.",
        ],
    }
