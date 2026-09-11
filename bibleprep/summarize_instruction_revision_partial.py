"""Versioned v3 contingency accounting; unavailable requests are not answers.

The frozen full-return collector remains unchanged. This module reuses its
protocol, checkpoint, journal, prompt and native-sidecar checks, then accounts
for every intended slot and requires terminal run summaries before review.
"""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations, permutations
import json
import math
import os
from pathlib import Path

from bibleprep import summarize_instruction_revision as frozen
from bibleprep import evaluate_instruction as previous

ev, aggregate, raw, experiment = frozen.ev, frozen.aggregate, frozen.raw, frozen.experiment
ROOT = frozen.ROOT
CONTINGENCY = "manifests/instruction-target-revision-review-contingency-v3.json"
OUTPUT = "reports/inkling-instruction-target-revision-partial-v3.json"
REVIEW = "runs/inkling-instruction-target-revision-partial-review-v3"
STATUSES = ("returned", "error", "not_started", "unresolved")


def event_sha256(event):
    return None if event is None else ev.digest(aggregate.canonical(event))


def load_contingency(root=ROOT):
    _, data, contingency = previous._read(root, CONTINGENCY, under="manifests")
    reference = contingency.get("original_protocol", {})
    if (contingency.get("schema_version") != 1
            or contingency.get("status") != "frozen_before_answer_review"
            or reference.get("path") != experiment.PROTOCOL):
        aggregate.fail("A separate frozen postprocessing contingency is required.")
    previous._checked(root, reference, under="manifests")
    stopped = contingency.get("stopped_arms")
    if not isinstance(stopped, dict) or not set(stopped) <= set(experiment.STATES):
        aggregate.fail("Stopped conditions must be explicitly recorded in the contingency.")
    for policy in stopped.values():
        if (not isinstance(policy, dict)
                or set(policy) != {"terminal_error_case_id", "policy"}
                or not isinstance(policy["terminal_error_case_id"], str)
                or policy["policy"] != "no_retry_or_further_requests"):
            aggregate.fail("Unsupported stopped-condition policy.")
    software = contingency.get("software_sha256", {})
    if "bibleprep/summarize_instruction_revision_partial.py" not in software:
        aggregate.fail("The contingency must bind its new collector code.")
    for name, expected in software.items():
        if ev.digest(previous._path(root, name).read_bytes()) != expected:
            aggregate.fail("Postprocessing code or schema changed after the contingency freeze.")
    return contingency, ev.digest(data)


def slot_record(arm, case_id, starts, results):
    start, terminal = starts.get(case_id), results.get(case_id)
    status = ("returned" if terminal and terminal["event"] == "completed" else
              "error" if terminal else "unresolved" if start else "not_started")
    reason = {"returned": "native_response_returned", "error": "terminal_error",
              "unresolved": "pending_result", "not_started": "not_started"}[status]
    if status == "not_started" and any(e["event"] == "error" for e in results.values()):
        reason = "not_started_after_terminal_error"
    record = {"arm": arm, "case_id": case_id, "status": status, "reason_code": reason,
              "started_event_sha256": event_sha256(start), "terminal_event_sha256": event_sha256(terminal)}
    if status == "returned":
        record["diagnostic_artifact_sha256"] = aggregate.hash_value(
            terminal["raw_response_redacted"]["native_tinker"]["private_diagnostic_artifact"]["sha256"])
    elif status == "error":
        kind = terminal.get("error", {}).get("kind")
        if kind not in {"http_error", "network_error", "invalid_response_or_request_error"}:
            aggregate.fail("An error lacks a recognized privacy-safe failure kind.")
        record.update(error_kind=kind, elapsed_seconds=aggregate.number(terminal["elapsed_seconds"]),
                      accounted_or_reserved_usd=aggregate.number(terminal["accounted_cost_usd"]))
    return record


def verify_terminal_summary(snap, directory, stopped_policy=None):
    """Read safe summary fields only; counts include error receipts, not answers."""
    starts, results = aggregate.validate_events(snap)
    ids = [case["id"] for case in snap.cases]
    if list(starts) != ids[:len(starts)] or list(results) != ids[:len(results)]:
        aggregate.fail("Native journal does not preserve the frozen request order.")
    pending, errored = None, False
    for event in snap.events:
        if errored:
            aggregate.fail("A native request appears after a terminal error.")
        if event["event"] == "started":
            if pending is not None:
                aggregate.fail("Overlapping requests differ from the frozen sequential runner.")
            pending = event["case_id"]
        else:
            if event["case_id"] != pending:
                aggregate.fail("A native result does not close the immediately preceding request.")
            pending = None
            errored = event["event"] == "error"
    reservation = None
    if snap.manifest is not None:
        settings = snap.manifest["settings"]
        reservation = ev.estimated_cost(settings["max_input_tokens"], settings["max_output_tokens"], settings)
        for start in starts.values():
            if not math.isclose(start["reserved_cost_usd"], reservation, rel_tol=1e-12, abs_tol=1e-12):
                aggregate.fail("A native request reservation differs from the frozen price and bounds.")
        for event in results.values():
            usage = event.get("usage") if event["event"] == "completed" else None
            charge = ev.estimated_cost(usage["input_tokens"], usage["output_tokens"], settings) if usage else reservation
            if (not math.isclose(event["accounted_cost_usd"], charge, rel_tol=1e-12, abs_tol=1e-12)
                    or event["event"] == "error" and event.get("accounting_uncertain") is not True):
                aggregate.fail("Native charge does not match verified usage or its uncertain reservation.")
    path = Path(directory) / "summary.json"
    result = {"terminal_verified": False, "summary_sha256": None,
              "stop_reason": "summary_not_available", "terminal_receipts": len(results),
              "returned_answers": sum(e["event"] == "completed" for e in results.values()),
              "errors": sum(e["event"] == "error" for e in results.values()),
              "not_started": len(ids) - len(starts), "unresolved": len(set(starts) - set(results))}
    if not path.exists():
        return result
    if path.is_symlink():
        aggregate.fail("A terminal summary must not be a symlink.")
    summary, summary_hash = aggregate.read_json(path)
    result["summary_sha256"] = summary_hash
    if summary.get("mode") == "dry_run":
        result["stop_reason"] = "dry_run_summary_only"
        return result
    allowed = {"all_selected_cases_completed", "uncertain_billing_or_provider_limit_breach", "budget_would_be_exceeded"}
    if summary.get("mode") != "execute" or summary.get("stop_reason") not in allowed:
        aggregate.fail("Unrecognized terminal evaluation summary.")
    result["stop_reason"] = summary["stop_reason"]
    for key, expected in (("selected_cases", len(ids)), ("completed_cases", len(results)),
                          ("pending_cases", len(ids) - len(results))):
        if type(summary.get(key)) is not int or summary[key] != expected:
            aggregate.fail("Terminal summary counters disagree with journal receipts.")
    if reservation is None:
        aggregate.fail("Terminal summary lacks a native request manifest.")
    expected_cost = math.fsum(e["accounted_cost_usd"] for e in results.values())
    for key, expected in (("per_request_reservation_usd", reservation), ("accounted_cost_usd", expected_cost),
                          ("remaining_worst_case_usd", reservation * (len(ids) - len(results)))):
        if not math.isclose(aggregate.number(summary.get(key)), expected, rel_tol=1e-10, abs_tol=1e-10):
            aggregate.fail("Terminal summary cost accounting differs from its journal.")
    if result["unresolved"] or snap.provenance["journal_has_incomplete_tail"]:
        return result
    if stopped_policy is not None:
        case_id = stopped_policy["terminal_error_case_id"]
        if (case_id not in ids or not results or list(results)[-1] != case_id
                or results[case_id]["event"] != "error" or result["errors"] != 1
                or snap.events[-1].get("event") != "error"
                or summary["stop_reason"] != "uncertain_billing_or_provider_limit_breach"
                or results[case_id].get("accounting_uncertain") is not True):
            aggregate.fail("The explicitly stopped condition does not end in its recorded terminal error.")
        result["terminal_verified"] = True
    else:
        result["terminal_verified"] = (len(results) == len(ids) and not result["errors"]
                                         and summary["stop_reason"] == "all_selected_cases_completed")
    return result


def collect(root=ROOT):
    root = Path(root)
    contingency, contingency_hash = load_contingency(root)
    result, snapshots, dataset_file = frozen.collect(root)
    if contingency["original_protocol"]["sha256"] != result["provenance"]["experiment_protocol_sha256"]:
        aggregate.fail("Contingency and native results bind different original protocols.")
    protocol, _ = experiment.load_protocol(root)
    slots, summaries, by_arm = [], {}, {}
    for arm, snap in snapshots.items():
        starts, events = aggregate.validate_events(snap)
        own_slots = [slot_record(arm, case["id"], starts, events) for case in snap.cases]
        slots.extend(own_slots)
        counts = Counter({status: 0 for status in STATUSES})
        counts.update(slot["status"] for slot in own_slots)
        by_arm[arm] = {"intended": len(snap.cases), **dict(counts)}
        directory = raw.private_path(root, protocol["run_directories"][arm])
        summaries[arm] = verify_terminal_summary(snap, directory, contingency["stopped_arms"].get(arm))
        result["provenance"]["evaluations"][arm]["summary_sha256"] = summaries[arm]["summary_sha256"]
        retention = result["english_evaluation"][arm]["general_english_retention"]
        own_by_id = {slot["case_id"]: slot for slot in own_slots}
        for item in retention["results"]:
            item["status"] = own_by_id[item["case_id"]]["status"]
            if item["status"] != "returned":
                item["answer_complete"] = item["fixture_checks_passed"] = None
        retention["returned_cases"] = sum(item["status"] == "returned" for item in retention["results"])
        retention["interpretation"] += " Unavailable requests have null check/completion fields and no semantic grade."
    totals = {status: sum(counts[status] for counts in by_arm.values()) for status in STATUSES}
    closed = all(summary["terminal_verified"] for summary in summaries.values())
    unavailable = sum(totals[status] for status in STATUSES if status != "returned")
    result.update(schema_version=1, experiment="instruction-target-revision-v3-partial-accounting",
                  status="collection_in_progress" if not closed else "closed_with_unavailable_slots" if unavailable else "closed_all_returned",
                  collection_closed=closed, availability={"intended_slots": len(slots), **totals, "by_arm": by_arm, "slots": slots},
                  terminal_summaries=summaries)
    result["provenance"]["review_contingency_sha256"] = contingency_hash
    result["comparison_validation"]["available_prompt_groups_verified"] = True
    result["comparison_validation"]["verified_returned_slots"] = totals["returned"]
    if result["comparison_validation"]["verified_diagnostic_sidecar_count"] != totals["returned"]:
        aggregate.fail("Returned slot count differs from verified native sidecars.")
    result["comparison_validation"]["paired_returned_denominators"] = {}
    slot_by_id = {(s["arm"], s["case_id"]): s for s in slots}
    cases = next(iter(snapshots.values())).cases
    for a, b in combinations(experiment.STATES, 2):
        joint = [case for case in cases if all(slot_by_id[(arm, case["id"])]["status"] == "returned" for arm in (a, b))]
        result["comparison_validation"]["paired_returned_denominators"][f"{a}_vs_{b}"] = {
            "intended_bible_cases": 24, "available_bible_cases": sum(c["language"] != "english" for c in joint),
            "intended_general_cases": 6, "available_general_cases": sum(c["language"] == "english" for c in joint)}
    result["limitations"] += [
        "This post-output operational contingency was chosen from execution counts before any candidate-quality review; the original experiment and collector remain unchanged.",
        "Legacy counts.received and terminal summary completed_cases include error receipts. availability.returned counts only native completed-event responses.",
        "Error, not-started and unresolved requests are unavailable slots, not semantic failures or blank model answers. They stay outside answer-preference denominators.",
        "Pairwise preferences must use jointly returned cases and disclose unavailable subsets. A small surviving E subset cannot support the original full-comparison claim.",
        "A network_error near the local deadline is consistent with a timeout, but does not establish the provider-side cause. No unavailable request is retried by this collector."]
    return result, snapshots, dataset_file


def prepare_review(result, snapshots, dataset_file, root=ROOT):
    from bibleprep.native_diagnostics_v1 import final_text_for_review
    root = Path(root)
    contingency, contingency_hash = load_contingency(root)
    protocol, protocol_hash = experiment.load_protocol(root)
    if (result.get("collection_closed") is not True or result["availability"]["unresolved"]
            or result["provenance"]["review_contingency_sha256"] != contingency_hash
            or result["provenance"]["experiment_protocol_sha256"] != protocol_hash):
        aggregate.fail("All conditions must be verifiably terminal before review preparation.")
    supplement = experiment.verified_criteria_review(protocol, root)
    cases, dataset_hash = ev.load_cases(dataset_file)
    if dataset_hash != protocol["evaluation"]["sha256"]:
        aggregate.fail("Frozen evaluation changed before contingency review.")
    starts, events = {}, {}
    for arm, snap in snapshots.items():
        directory = raw.private_path(root, protocol["run_directories"][arm])
        provenance = result["provenance"]["evaluations"][arm]
        for name in ("manifest", "events", "summary"):
            suffix = ".jsonl" if name == "events" else ".json"
            if ev.digest((directory / (name + suffix)).read_bytes()) != provenance[name + "_sha256"]:
                aggregate.fail("Native receipt or terminal summary changed before review.")
        if not verify_terminal_summary(snap, directory, contingency["stopped_arms"].get(arm))["terminal_verified"]:
            aggregate.fail("A condition is no longer terminal.")
        starts[arm], events[arm] = aggregate.validate_events(snap)
    choices, key, packets = list(permutations(experiment.STATES)), {}, []
    supplement_cases = {c["id"]: c for c in supplement["cases"]}
    for case in cases:
        order = choices[int(ev.digest(("target-revision-partial-review-v3:" + case["id"]).encode()), 16) % 24]
        key[case["id"]] = dict(zip("WXYZ", order))
        answers, unavailable = [], []
        for label, arm in zip("WXYZ", order):
            slot = slot_record(arm, case["id"], starts[arm], events[arm])
            receipts = {k: slot[k] for k in ("started_event_sha256", "terminal_event_sha256")}
            if slot["status"] != "returned":
                unavailable.append({"candidate": label, "status": slot["status"], "reason_code": slot["reason_code"], **receipts})
                continue
            event = events[arm][case["id"]]
            response = event["raw_response_redacted"]
            answer, finish = ev.answer_details(response)
            final = final_text_for_review(response, raw.private_path(root, protocol["run_directories"][arm]))
            answers.append({"candidate": label, "status": "returned", **receipts,
                "diagnostic_artifact_sha256": slot["diagnostic_artifact_sha256"],
                "answer": answer or "", "partial_final_text": final["partial_final_text"],
                "answer_complete": event["answer_complete"], "finish_reason": finish,
                **{name: final[name] for name in ("native_turn_complete", "partial_final_status", "final_text_withheld_due_to_malformed_structure")},
                "parse_issues": response["native_tinker"]["parse_issues"], "output_tokens": event["usage"]["output_tokens"]})
        packets.append({"case_id": case["id"], **{name: case.get(name) for name in
            ("prompt", "provided_evidence", "source_refs", "sourceURLs", "expected_behavior", "human_review_criteria", "source_review_caveats", "automatic_checks")},
            "preoutput_criteria_review_sha256": protocol["criteria_review"]["sha256"],
            "global_scoring_supplement": supplement["global_scoring_supplement"], "case_scoring_supplement": supplement_cases[case["id"]],
            "available_candidate_count": len(answers), "unavailable_candidates": unavailable, "answers": answers})
    if sum(len(p["answers"]) for p in packets) != result["availability"]["returned"]:
        aggregate.fail("Review candidate count differs from returned native slots.")
    directory = raw.private_path(root, REVIEW)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    for language in (None, "hebrew", "aramaic", "greek", "mixed", "english"):
        ids = {c["id"] for c in cases if language is None or c["language"] == language}
        data = b"".join(ev.json_bytes(p) + b"\n" for p in packets if p["case_id"] in ids)
        path = directory / ("cases.jsonl" if language is None else language + ".jsonl")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
    raw.write_private(directory / "private-label-key.json", {"case_labels": key, "dataset_sha256": dataset_hash,
        "criteria_review_sha256": protocol["criteria_review"]["sha256"], "review_contingency_sha256": contingency_hash,
        "ordering": "Per-case SHA256 of target-revision-partial-review-v3:case_id selects among 24 permutations of A,B,E,F; missing slots retain identity without answer text or grades."})
    raw.write_private(directory / "packet-receipt.json", {"intended_slots": 120, "available_candidates": result["availability"]["returned"],
        "review_contingency_sha256": contingency_hash, "native_provenance": result["provenance"]["evaluations"],
        "packet_sha256": {p.name: ev.digest(p.read_bytes()) for p in directory.glob("*.jsonl")}})
    return {"private_review_prepared": True, "cases": len(cases), "intended_slots": 120,
            "available_candidates": result["availability"]["returned"], "unavailable_slots": 120 - result["availability"]["returned"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-review", action="store_true")
    options = parser.parse_args(argv)
    try:
        result, snapshots, dataset_file = collect()
        (ROOT / OUTPUT).write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        message = {"status": result["status"], "public_aggregate_written": True}
        if options.prepare_review:
            message.update(prepare_review(result, snapshots, dataset_file))
        print(json.dumps(message))
    except Exception:
        print("Contingency accounting stopped; inspect private receipts and immutable hashes.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
