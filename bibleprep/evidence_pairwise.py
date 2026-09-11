"""Constructed, offline pairwise review and collection-sufficiency tooling."""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
import hashlib
import os
from pathlib import Path

from bibleprep.evidence import ROOT, confined_path, sha256
from bibleprep.evidence_collection import audit_collection, canonical_sha256
import bibleprep.evidence_blinded_review as blinded


SCHEMA_VERSION = 1
ARMS = ("B-memory", "B-packet", "B-lookup")
CONTRASTS = (
    ("packet_vs_memory", "B-packet", "B-memory"),
    ("lookup_vs_packet", "B-lookup", "B-packet"),
)


class PairwiseReviewError(ValueError):
    """Raised when a gate, pair packet, review, or private map is invalid."""


def _schema(value, kind):
    if type(value) is not int or value != SCHEMA_VERSION:
        raise PairwiseReviewError(f"Unsupported {kind} schema_version")


def _plan_cases(planned_slots, criteria):
    criteria_by_case = blinded._validate_criteria(criteria, planned_slots)
    grouped = defaultdict(dict)
    order = []
    for slot in planned_slots:
        case_id = slot["case_id"]
        if case_id not in grouped:
            order.append(case_id)
        grouped[case_id][slot["arm"]] = slot
    for case_id, rows in grouped.items():
        if set(rows) != set(ARMS):
            raise PairwiseReviewError(
                f"Case {case_id} must have exactly the three core evidence arms"
            )
    if set(grouped) != set(criteria_by_case):
        raise PairwiseReviewError("Criteria and planned cases differ")
    return order, grouped, criteria_by_case


def _validate_gate(planned_slots, criteria, gate):
    blinded._exact_keys(gate, {
        "schema_version", "artifact_kind", "gate_id", "fixture_kind",
        "planned_slots_sha256", "minimum_complete_slots_by_arm",
        "minimum_matched_complete_bible_pairs_by_contrast", "limitations",
    }, "gate")
    _schema(gate["schema_version"], "gate")
    if gate["artifact_kind"] != "constructed_collection_gate":
        raise PairwiseReviewError("Unsupported gate artifact_kind")
    blinded._identifier(gate["gate_id"], "gate.gate_id")
    if gate["fixture_kind"] != "constructed":
        raise PairwiseReviewError("Only constructed collection gates are accepted")
    blinded._sha(gate["planned_slots_sha256"], "gate.planned_slots_sha256")
    if gate["planned_slots_sha256"] != canonical_sha256(planned_slots):
        raise PairwiseReviewError("Gate does not bind the exact planned inventory")
    blinded._text_list(gate["limitations"], "gate.limitations", allow_empty=False)
    _, grouped, criteria_by_case = _plan_cases(planned_slots, criteria)
    planned_by_arm = Counter(slot["arm"] for slot in planned_slots)
    thresholds = gate["minimum_complete_slots_by_arm"]
    if not isinstance(thresholds, dict) or set(thresholds) != set(ARMS):
        raise PairwiseReviewError("Gate complete thresholds must exactly cover core arms")
    for arm, threshold in thresholds.items():
        if type(threshold) is not int or not 0 <= threshold <= planned_by_arm[arm]:
            raise PairwiseReviewError(f"Invalid complete threshold for {arm}")
    bible_cases = sum(not criteria_by_case[case_id]["general_control"] for case_id in grouped)
    if bible_cases == 0:
        raise PairwiseReviewError("A pairwise gate requires at least one constructed Bible case")
    pair_thresholds = gate["minimum_matched_complete_bible_pairs_by_contrast"]
    contrast_ids = {item[0] for item in CONTRASTS}
    if not isinstance(pair_thresholds, dict) or set(pair_thresholds) != contrast_ids:
        raise PairwiseReviewError("Gate pair thresholds must exactly cover primary contrasts")
    for contrast_id, threshold in pair_thresholds.items():
        if type(threshold) is not int or not 1 <= threshold <= bible_cases:
            raise PairwiseReviewError(f"Invalid matched-complete threshold for {contrast_id}")
    return criteria_by_case


def freeze_collection_gate(planned_slots, criteria, gate, out_path, root=ROOT):
    """Validate and exclusively freeze a private pre-collection gate."""
    audit_collection(planned_slots, [])
    _validate_gate(planned_slots, criteria, gate)
    root = Path(root).resolve()
    destination = confined_path(root, out_path, ("runs",))
    if destination.exists():
        raise FileExistsError(destination)
    blinded._mkdir_private(destination.parent, root)
    blinded._exclusive_json(destination, gate)
    return {
        "gate_path": destination.relative_to(root).as_posix(),
        "gate_file_sha256": sha256(destination),
        "planned_slots_sha256": canonical_sha256(planned_slots),
    }


def _load_bound(path, expected_sha256, root, label):
    blinded._sha(expected_sha256, "expected_" + label.replace(" ", "_") + "_file_sha256")
    candidate = confined_path(root, path, ("runs",))
    if not candidate.is_file() or candidate.is_symlink():
        raise PairwiseReviewError(f"{label} is missing or unsafe")
    if sha256(candidate) != expected_sha256:
        raise PairwiseReviewError(f"{label} file hash does not match its freeze receipt")
    return blinded._load_private_json(candidate, root, label)


def _answer_index(audit):
    return {(row["case_id"], row["arm"]): row for row in audit["reviewable_answers"]}


def _side(answer):
    return {
        "answer_status": answer["answer_status"],
        "stop_reason": answer["stop_reason"],
        "answer_text": answer["final_text"],
        "answer_sha256": answer["final_text_sha256"],
        "receipt_sha256": answer["receipt_sha256"],
    }


def _construct_pair_artifacts(planned_slots, audit, criteria, gate_sha, secret):
    order, grouped, criteria_by_case = _plan_cases(planned_slots, criteria)
    answers = _answer_index(audit)
    inventory, reviewable, mappings = [], [], []
    for case_id in order:
        case = criteria_by_case[case_id]
        criteria_binding = {key: case[key] for key in (
            "case_id", "question", "general_control", "scoring_criteria",
            "reviewer_instructions",
        )}
        criteria_sha = canonical_sha256(criteria_binding)
        for contrast_id, first_arm, second_arm in CONTRASTS:
            binding = canonical_sha256({
                "planned_slots_sha256": audit["planned_slots_sha256"],
                "journal_sha256": audit["journal_sha256"],
                "case_id": case_id,
                "contrast_id": contrast_id,
            })
            pair_id = "pair-" + blinded._opaque(secret, "pair-id", binding)[:24]
            first_answer = answers.get((case_id, first_arm))
            second_answer = answers.get((case_id, second_arm))
            available = first_answer is not None and second_answer is not None
            matched_complete = bool(
                available and first_answer["answer_status"] == "complete"
                and second_answer["answer_status"] == "complete"
            )
            swap = int(blinded._opaque(secret, "left-right", binding)[0], 16) % 2 == 1
            left_arm, right_arm = (
                (second_arm, first_arm) if swap else (first_arm, second_arm)
            )
            left_answer = answers.get((case_id, left_arm))
            right_answer = answers.get((case_id, right_arm))
            inventory.append({
                "pair_id": pair_id,
                "case_id": case_id,
                "general_control": case["general_control"],
                "criteria_sha256": criteria_sha,
                "availability": "reviewable" if available else "unavailable",
                "matched_complete": matched_complete,
            })
            if available:
                reviewable.append({
                    "pair_id": pair_id,
                    "case_id": case_id,
                    "question": case["question"],
                    "general_control": case["general_control"],
                    "scoring_criteria": copy.deepcopy(case["scoring_criteria"]),
                    "reviewer_instructions": copy.deepcopy(case["reviewer_instructions"]),
                    "criteria_sha256": criteria_sha,
                    "matched_complete": matched_complete,
                    "left": _side(left_answer),
                    "right": _side(right_answer),
                })
            mappings.append({
                "pair_id": pair_id,
                "case_id": case_id,
                "contrast_id": contrast_id,
                "first_arm": first_arm,
                "second_arm": second_arm,
                "first_slot_id": grouped[case_id][first_arm]["slot_id"],
                "second_slot_id": grouped[case_id][second_arm]["slot_id"],
                "left_arm": left_arm,
                "right_arm": right_arm,
                "availability": "reviewable" if available else "unavailable",
                "matched_complete": matched_complete,
                "left_answer_sha256": left_answer["final_text_sha256"] if left_answer else None,
                "left_receipt_sha256": left_answer["receipt_sha256"] if left_answer else None,
                "right_answer_sha256": right_answer["final_text_sha256"] if right_answer else None,
                "right_receipt_sha256": right_answer["receipt_sha256"] if right_answer else None,
            })
    rank = lambda row: blinded._opaque(secret, "pair-order", row["pair_id"])
    inventory.sort(key=rank)
    reviewable.sort(key=rank)
    packet = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "constructed_pair_review_packet",
        "packet_id": "pair-packet-" + blinded._opaque(
            secret, "pair-packet-id", audit["journal_sha256"]
        )[:24],
        "fixture_kind": "constructed",
        "criteria": copy.deepcopy(criteria),
        "criteria_document_sha256": canonical_sha256(criteria),
        "gate_file_sha256": gate_sha,
        "planned_pairs": inventory,
        "reviewable_pairs": reviewable,
        "limitations": [
            "Opaque pair IDs, order, and left/right placement conceal arm labels procedurally.",
            "Answer content can reveal evidence treatment; unavailable pairs are not losses.",
            "Constructed pair judgments cannot establish expert certification or model quality.",
        ],
    }
    pair_map = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "private_constructed_pair_map",
        "packet_sha256": canonical_sha256(packet),
        "planned_slots_sha256": audit["planned_slots_sha256"],
        "journal_sha256": audit["journal_sha256"],
        "criteria_document_sha256": canonical_sha256(criteria),
        "gate_file_sha256": gate_sha,
        "mapping_seed_hex": secret.hex(),
        "pairs": sorted(mappings, key=lambda row: row["pair_id"]),
    }
    return packet, pair_map


def build_pair_artifacts(
        planned_slots, journal, criteria, gate_path, *, expected_gate_file_sha256,
        seed=None, root=ROOT):
    """Build an arm-free pair packet and a secret map for every planned contrast."""
    root = Path(root).resolve()
    audit = audit_collection(planned_slots, journal)
    gate = _load_bound(gate_path, expected_gate_file_sha256, root, "gate")
    _validate_gate(planned_slots, criteria, gate)
    return _construct_pair_artifacts(
        planned_slots, audit, criteria, expected_gate_file_sha256,
        blinded._seed_bytes(seed),
    )


def _validate_side(side, label):
    blinded._exact_keys(side, {
        "answer_status", "stop_reason", "answer_text", "answer_sha256", "receipt_sha256"
    }, label)
    if side["answer_status"] not in {"complete", "partial"}:
        raise PairwiseReviewError(label + ".answer_status is invalid")
    if side["stop_reason"] not in {"stop", "output_limit", "incomplete"}:
        raise PairwiseReviewError(label + ".stop_reason is invalid")
    if not isinstance(side["answer_text"], str) or not side["answer_text"].strip():
        raise PairwiseReviewError(label + ".answer_text must contain final content")
    blinded._sha(side["answer_sha256"], label + ".answer_sha256")
    blinded._sha(side["receipt_sha256"], label + ".receipt_sha256")
    if hashlib.sha256(side["answer_text"].encode("utf-8")).hexdigest() != side["answer_sha256"]:
        raise PairwiseReviewError(label + ".answer_sha256 does not match exact text")


def _validate_packet(packet):
    blinded._exact_keys(packet, {
        "schema_version", "artifact_kind", "packet_id", "fixture_kind", "criteria",
        "criteria_document_sha256", "gate_file_sha256", "planned_pairs",
        "reviewable_pairs", "limitations",
    }, "pair_packet")
    _schema(packet["schema_version"], "pair packet")
    if (packet["artifact_kind"] != "constructed_pair_review_packet"
            or packet["fixture_kind"] != "constructed"):
        raise PairwiseReviewError("Unsupported pair packet")
    blinded._identifier(packet["packet_id"], "pair_packet.packet_id")
    for field in ("criteria_document_sha256", "gate_file_sha256"):
        blinded._sha(packet[field], "pair_packet." + field)
    if canonical_sha256(packet["criteria"]) != packet["criteria_document_sha256"]:
        raise PairwiseReviewError("Pair packet criteria hash does not match")
    criteria_by_case = blinded._criteria_cases(packet["criteria"])
    blinded._text_list(packet["limitations"], "pair_packet.limitations", allow_empty=False)
    if not isinstance(packet["planned_pairs"], list) or not packet["planned_pairs"]:
        raise PairwiseReviewError("pair_packet.planned_pairs must be nonempty")
    planned = {}
    for index, row in enumerate(packet["planned_pairs"]):
        label = f"pair_packet.planned_pairs[{index}]"
        blinded._exact_keys(row, {
            "pair_id", "case_id", "general_control", "criteria_sha256", "availability",
            "matched_complete",
        }, label)
        blinded._identifier(row["pair_id"], label + ".pair_id")
        blinded._identifier(row["case_id"], label + ".case_id")
        if row["pair_id"] in planned:
            raise PairwiseReviewError("Duplicate planned pair_id")
        if type(row["general_control"]) is not bool or type(row["matched_complete"]) is not bool:
            raise PairwiseReviewError(label + " Boolean fields are invalid")
        if row["availability"] not in {"reviewable", "unavailable"}:
            raise PairwiseReviewError(label + ".availability is invalid")
        if row["matched_complete"] and row["availability"] != "reviewable":
            raise PairwiseReviewError(label + " unavailable pair cannot be matched complete")
        blinded._sha(row["criteria_sha256"], label + ".criteria_sha256")
        case = criteria_by_case.get(row["case_id"])
        if case is None or case["general_control"] is not row["general_control"]:
            raise PairwiseReviewError(label + " does not match criteria")
        planned[row["pair_id"]] = row
    if not isinstance(packet["reviewable_pairs"], list):
        raise PairwiseReviewError("pair_packet.reviewable_pairs must be a list")
    reviewable = {}
    for index, row in enumerate(packet["reviewable_pairs"]):
        label = f"pair_packet.reviewable_pairs[{index}]"
        blinded._exact_keys(row, {
            "pair_id", "case_id", "question", "general_control", "scoring_criteria",
            "reviewer_instructions", "criteria_sha256", "matched_complete", "left", "right",
        }, label)
        if row["pair_id"] in reviewable or row["pair_id"] not in planned:
            raise PairwiseReviewError(label + ".pair_id is duplicate or unplanned")
        plan_row = planned[row["pair_id"]]
        if plan_row["availability"] != "reviewable":
            raise PairwiseReviewError(label + " is not marked reviewable")
        case = criteria_by_case.get(row["case_id"])
        if case is None or any(row[field] != case[field] for field in (
                "question", "general_control", "scoring_criteria", "reviewer_instructions")):
            raise PairwiseReviewError(label + " does not match criteria")
        if any(row[field] != plan_row[field] for field in (
                "case_id", "general_control", "criteria_sha256", "matched_complete")):
            raise PairwiseReviewError(label + " does not match planned pair")
        _validate_side(row["left"], label + ".left")
        _validate_side(row["right"], label + ".right")
        if row["matched_complete"] != (
                row["left"]["answer_status"] == row["right"]["answer_status"] == "complete"):
            raise PairwiseReviewError(label + ".matched_complete is inconsistent")
        reviewable[row["pair_id"]] = row
    expected = {pair_id for pair_id, row in planned.items() if row["availability"] == "reviewable"}
    if set(reviewable) != expected:
        raise PairwiseReviewError("Reviewable pair details must exactly cover reviewable inventory")
    return planned, reviewable


def _validate_review(packet, review):
    _, pairs = _validate_packet(packet)
    blinded._exact_keys(review, {
        "schema_version", "artifact_kind", "review_id", "packet_sha256", "reviewer_kind",
        "reviewer_role", "conflicts", "expert_certified", "assessments", "limitations",
    }, "pair_review")
    _schema(review["schema_version"], "pair review")
    if review["artifact_kind"] != "frozen_constructed_pair_review":
        raise PairwiseReviewError("Unsupported pair review")
    blinded._identifier(review["review_id"], "pair_review.review_id")
    blinded._sha(review["packet_sha256"], "pair_review.packet_sha256")
    if review["packet_sha256"] != canonical_sha256(packet):
        raise PairwiseReviewError("Pair review packet hash does not match")
    if review["reviewer_kind"] not in blinded.REVIEWER_KINDS:
        raise PairwiseReviewError("pair_review.reviewer_kind is invalid")
    blinded._text(review["reviewer_role"], "pair_review.reviewer_role")
    blinded._text_list(review["conflicts"], "pair_review.conflicts")
    if review["expert_certified"] is not False:
        raise PairwiseReviewError("This workflow cannot record expert certification")
    blinded._text_list(review["limitations"], "pair_review.limitations", allow_empty=False)
    if not isinstance(review["assessments"], list):
        raise PairwiseReviewError("pair_review.assessments must be a list")
    seen = set()
    for index, row in enumerate(review["assessments"]):
        label = f"pair_review.assessments[{index}]"
        blinded._exact_keys(row, {
            "pair_id", "left_answer_sha256", "left_receipt_sha256", "right_answer_sha256",
            "right_receipt_sha256", "preference", "rationale",
        }, label)
        pair_id = row["pair_id"]
        if pair_id in seen or pair_id not in pairs:
            raise PairwiseReviewError(label + ".pair_id is duplicate or unknown")
        seen.add(pair_id)
        pair = pairs[pair_id]
        for side in ("left", "right"):
            for kind in ("answer_sha256", "receipt_sha256"):
                field = side + "_" + kind
                blinded._sha(row[field], label + "." + field)
                if row[field] != pair[side][kind]:
                    raise PairwiseReviewError(label + "." + field + " does not match packet")
        if row["preference"] not in {"left", "right", "tie"}:
            raise PairwiseReviewError(label + ".preference is invalid")
        blinded._text(row["rationale"], label + ".rationale")
    if seen != set(pairs):
        raise PairwiseReviewError("Pair assessments must exactly cover reviewable pairs")
    return pairs


def validate_and_freeze_pair_review(packet, review, out_path, root=ROOT):
    """Strictly validate and exclusively freeze a private pair review."""
    pairs = _validate_review(packet, review)
    root = Path(root).resolve()
    destination = confined_path(root, out_path, ("runs",))
    if destination.exists():
        raise FileExistsError(destination)
    blinded._mkdir_private(destination.parent, root)
    blinded._exclusive_json(destination, review)
    return {
        "review_path": destination.relative_to(root).as_posix(),
        "review_file_sha256": sha256(destination),
        "packet_sha256": canonical_sha256(packet),
        "reviewable_pair_count": len(pairs),
    }


def write_pair_artifacts(packet, pair_map, output_directory, root=ROOT):
    """Write a new private pair packet/map directory with exclusive 0600 files."""
    _validate_packet(packet)
    if pair_map.get("packet_sha256") != canonical_sha256(packet):
        raise PairwiseReviewError("Pair map does not bind packet")
    root = Path(root).resolve()
    destination = confined_path(root, output_directory, ("runs",))
    if destination.exists():
        raise FileExistsError(destination)
    blinded._mkdir_private(destination.parent, root)
    os.mkdir(destination, 0o700)
    packet_path, map_path = destination / "pair-packet.json", destination / "private-pair-map.json"
    blinded._exclusive_json(packet_path, packet)
    blinded._exclusive_json(map_path, pair_map)
    return {
        "packet_path": packet_path.relative_to(root).as_posix(),
        "packet_file_sha256": sha256(packet_path),
        "pair_map_path": map_path.relative_to(root).as_posix(),
        "pair_map_file_sha256": sha256(map_path),
    }


def _expected_pair_facts(planned_slots, audit, criteria):
    order, grouped, criteria_by_case = _plan_cases(planned_slots, criteria)
    answers = _answer_index(audit)
    facts = {}
    for case_id in order:
        for contrast_id, first_arm, second_arm in CONTRASTS:
            first, second = answers.get((case_id, first_arm)), answers.get((case_id, second_arm))
            facts[(case_id, contrast_id)] = {
                "general_control": criteria_by_case[case_id]["general_control"],
                "first_slot_id": grouped[case_id][first_arm]["slot_id"],
                "second_slot_id": grouped[case_id][second_arm]["slot_id"],
                "first": first, "second": second,
                "availability": "reviewable" if first and second else "unavailable",
                "matched_complete": bool(first and second and
                    first["answer_status"] == second["answer_status"] == "complete"),
            }
    return facts


def _validate_packet_against_inputs(packet, planned_slots, audit, criteria, gate_sha):
    planned, reviewable = _validate_packet(packet)
    blinded._validate_criteria(packet["criteria"], planned_slots)
    if canonical_sha256(criteria) != packet["criteria_document_sha256"]:
        raise PairwiseReviewError("Pair packet does not bind supplied criteria")
    if packet["gate_file_sha256"] != gate_sha:
        raise PairwiseReviewError("Pair packet does not bind frozen gate")
    facts = _expected_pair_facts(planned_slots, audit, criteria)
    if len(planned) != len(facts):
        raise PairwiseReviewError("Pair packet does not cover every planned contrast")
    expected_reviewable = Counter()
    for (case_id, _), fact in facts.items():
        if fact["availability"] == "reviewable":
            sides = sorted((
                (fact["first"]["final_text"], fact["first"]["final_text_sha256"],
                 fact["first"]["receipt_sha256"], fact["first"]["answer_status"]),
                (fact["second"]["final_text"], fact["second"]["final_text_sha256"],
                 fact["second"]["receipt_sha256"], fact["second"]["answer_status"]),
            ))
            expected_reviewable[(
                case_id, fact["general_control"], fact["matched_complete"], tuple(sides)
            )] += 1
    actual_reviewable = Counter()
    for row in reviewable.values():
        sides = sorted((
            (row["left"]["answer_text"], row["left"]["answer_sha256"],
             row["left"]["receipt_sha256"], row["left"]["answer_status"]),
            (row["right"]["answer_text"], row["right"]["answer_sha256"],
             row["right"]["receipt_sha256"], row["right"]["answer_status"]),
        ))
        actual_reviewable[(
            row["case_id"], row["general_control"], row["matched_complete"], tuple(sides)
        )] += 1
    if actual_reviewable != expected_reviewable:
        raise PairwiseReviewError("Pair packet answers do not match the recomputed collection")


def _validate_pair_map(pair_map, packet, planned_slots, audit, criteria, gate_sha):
    blinded._exact_keys(pair_map, {
        "schema_version", "artifact_kind", "packet_sha256", "planned_slots_sha256",
        "journal_sha256", "criteria_document_sha256", "gate_file_sha256",
        "mapping_seed_hex", "pairs",
    }, "pair_map")
    _schema(pair_map["schema_version"], "pair map")
    if pair_map["artifact_kind"] != "private_constructed_pair_map":
        raise PairwiseReviewError("Unsupported pair map")
    expected_bindings = {
        "packet_sha256": canonical_sha256(packet),
        "planned_slots_sha256": audit["planned_slots_sha256"],
        "journal_sha256": audit["journal_sha256"],
        "criteria_document_sha256": canonical_sha256(criteria),
        "gate_file_sha256": gate_sha,
    }
    for field, expected in expected_bindings.items():
        blinded._sha(pair_map[field], "pair_map." + field)
        if pair_map[field] != expected:
            raise PairwiseReviewError("Pair map " + field + " does not match")
    secret = blinded._seed_bytes(pair_map["mapping_seed_hex"])
    expected_packet, expected_map = _construct_pair_artifacts(
        planned_slots, audit, criteria, gate_sha, secret
    )
    if canonical_sha256(packet) != canonical_sha256(expected_packet):
        raise PairwiseReviewError("Pair packet does not match the secret deterministic mapping")
    if canonical_sha256(pair_map) != canonical_sha256(expected_map):
        raise PairwiseReviewError("Pair map does not match the secret deterministic mapping")
    return {row["pair_id"]: row for row in pair_map["pairs"]}, _expected_pair_facts(
        planned_slots, audit, criteria
    )


def _preference_counts():
    return {"denominator": 0, "first_arm_preferred": 0, "second_arm_preferred": 0, "ties": 0}


def integrate_frozen_pair_review(
        planned_slots, journal, criteria, packet, gate_path, review_path, pair_map_path, *,
        expected_gate_file_sha256, expected_review_file_sha256,
        expected_pair_map_file_sha256=None, root=ROOT):
    """Integrate a frozen review; the private map is loaded only after review validation."""
    root = Path(root).resolve()
    audit = audit_collection(planned_slots, journal)
    gate = _load_bound(gate_path, expected_gate_file_sha256, root, "gate")
    _validate_gate(planned_slots, criteria, gate)
    _validate_packet_against_inputs(
        packet, planned_slots, audit, criteria, expected_gate_file_sha256
    )
    review = _load_bound(review_path, expected_review_file_sha256, root, "pair review")
    reviewable = _validate_review(packet, review)
    if expected_pair_map_file_sha256 is not None:
        pair_map = _load_bound(
            pair_map_path, expected_pair_map_file_sha256, root, "pair map"
        )
    else:
        pair_map = blinded._load_private_json(pair_map_path, root, "pair map")
    actual_pair_map_sha256 = sha256(confined_path(root, pair_map_path, ("runs",)))
    labels, facts = _validate_pair_map(
        pair_map, packet, planned_slots, audit, criteria, expected_gate_file_sha256
    )
    judgments = {row["pair_id"]: row for row in review["assessments"]}

    contrast_results = {}
    for contrast_id, first_arm, second_arm in CONTRASTS:
        all_counts, complete_counts = _preference_counts(), _preference_counts()
        general = {"planned": 0, "reviewable": 0, "matched_complete": 0, "unavailable": 0}
        for pair_id, label in labels.items():
            if label["contrast_id"] != contrast_id:
                continue
            fact = facts[(label["case_id"], contrast_id)]
            if fact["general_control"]:
                general["planned"] += 1
                general[fact["availability"]] += 1
                general["matched_complete"] += fact["matched_complete"]
                continue
            if fact["availability"] != "reviewable":
                continue
            judgment = judgments[pair_id]
            preferred = None if judgment["preference"] == "tie" else label[
                judgment["preference"] + "_arm"
            ]
            key = (
                "ties" if preferred is None else
                "first_arm_preferred" if preferred == first_arm else "second_arm_preferred"
            )
            all_counts["denominator"] += 1
            all_counts[key] += 1
            if fact["matched_complete"]:
                complete_counts["denominator"] += 1
                complete_counts[key] += 1
        planned_bible = sum(
            1 for (case_id, cid), fact in facts.items()
            if cid == contrast_id and not fact["general_control"]
        )
        contrast_results[contrast_id] = {
            "first_arm": first_arm,
            "second_arm": second_arm,
            "planned_bible_pairs": planned_bible,
            "unavailable_bible_pairs": planned_bible - all_counts["denominator"],
            "all_reviewable_bible_pairs": all_counts,
            "matched_complete_bible_pairs": complete_counts,
            "general_controls": general,
        }
    arm_checks = {
        arm: {
            **audit["arms"][arm],
            "minimum_complete_required": gate["minimum_complete_slots_by_arm"][arm],
            "threshold_met": audit["arms"][arm]["complete"]
                >= gate["minimum_complete_slots_by_arm"][arm],
        }
        for arm in ARMS
    }
    pair_checks = {
        contrast_id: {
            "matched_complete_bible_pairs": contrast_results[contrast_id][
                "matched_complete_bible_pairs"
            ]["denominator"],
            "minimum_required": gate[
                "minimum_matched_complete_bible_pairs_by_contrast"
            ][contrast_id],
        }
        for contrast_id, _, _ in CONTRASTS
    }
    for row in pair_checks.values():
        row["threshold_met"] = row["matched_complete_bible_pairs"] >= row["minimum_required"]
    sufficient = all(row["threshold_met"] for row in arm_checks.values()) and all(
        row["threshold_met"] for row in pair_checks.values()
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "constructed_pair_review_integration",
        "planned_slots_sha256": audit["planned_slots_sha256"],
        "journal_sha256": audit["journal_sha256"],
        "packet_sha256": canonical_sha256(packet),
        "gate_file_sha256": expected_gate_file_sha256,
        "review_file_sha256": expected_review_file_sha256,
        "pair_map_file_sha256": actual_pair_map_sha256,
        "collection_gate_status": "collection_sufficient" if sufficient else "inconclusive",
        "arm_collection": arm_checks,
        "pair_collection": pair_checks,
        "contrasts": contrast_results,
        "model_promotion": "not_assessed_or_performed",
        "expert_certified": False,
        "limitations": [
            "The gate reports collection sufficiency only; it is not a model quality or promotion gate.",
            "Reviewable partial pairs count only in all-reviewable preferences, never matched-complete preferences.",
            "Unavailable pairs remain unavailable and are not counted as losses.",
            "A freeze hash binds gate bytes but does not independently prove when they were frozen.",
        ],
    }
