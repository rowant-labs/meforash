"""Summarize a repeated unchanged-model control without exposing answer text.

The first control run selects a prefix of the original dataset; the second uses
an exact tail dataset. Their union must reproduce every frozen question once.
This records variation under matching requests, without assigning its cause.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from bibleprep import evaluate as ev
from bibleprep import summarize_adaptation as shared


ROOT = Path(__file__).resolve().parents[1]


def compare_repeats(baseline, repeats):
    if baseline.manifest is None:
        shared.fail("The original baseline manifest is required.")
    reference = {case["id"]: case for case in baseline.cases}
    if len(reference) != len(baseline.cases):
        shared.fail("The frozen baseline contains duplicate questions.")
    settings = baseline.manifest["settings"]
    protocol = shared.public_protocol(settings)
    for run in [baseline, *repeats]:
        if run.manifest is None:
            continue
        other = run.manifest["settings"]
        if (other.get("transport") != "native_tinker_comparison"
                or other.get("model_state") is not None
                or other.get("adapter_sampler_path") is not None
                or other.get("checkpoint_reference_sha256") is not None):
            shared.fail("The repeat control must use the unchanged base model.")
        if (run.manifest["system_prompt_sha256"] != baseline.manifest["system_prompt_sha256"]
                or any(key not in other or other[key] != settings[key] for key in shared.SAMPLING_KEYS)):
            shared.fail("The repeat control changed system prompts or generation settings.")
    selected = set()
    for run in repeats:
        for case in run.cases:
            if case["id"] in selected or reference.get(case["id"]) != case:
                shared.fail("Repeat-control selections overlap or change a frozen question.")
            selected.add(case["id"])
    if selected != set(reference):
        shared.fail("The repeat controls do not cover every frozen question exactly once.")
    _, old_results = shared.validate_events(baseline)
    counts = Counter({key: 0 for key in (
        "paired_returned_responses", "pairs_with_both_answers_complete",
        "identical_generated_token_streams", "different_generated_token_streams",
        "exact_final_text_matches", "different_final_texts",
        "exact_nonempty_final_text_matches", "both_final_texts_empty")})
    evidence = []
    for run in repeats:
        _, results = shared.validate_events(run)
        for case_id, event in results.items():
            if event["event"] != "completed":
                continue
            previous = old_results.get(case_id)
            if previous is None or previous["event"] != "completed":
                shared.fail("A returned control response lacks a comparable baseline response.")
            old_raw, new_raw = (item["raw_response_redacted"] for item in (previous, event))
            old_native, new_native = old_raw["native_tinker"], new_raw["native_tinker"]
            prompt_hash = shared.hash_value(old_native["prompt_sha256"])
            if shared.hash_value(new_native["prompt_sha256"]) != prompt_hash:
                shared.fail("Repeat-control prompt token hashes differ from the baseline.")
            old_output = shared.hash_value(old_native.get("output_tokens_sha256"))
            new_output = shared.hash_value(new_native.get("output_tokens_sha256"))
            old_text, _ = ev.answer_details(old_raw)
            new_text, _ = ev.answer_details(new_raw)
            if not isinstance(old_text, str) or not isinstance(new_text, str):
                shared.fail("A returned final-text comparison value is not a string.")
            same_tokens, same_text = old_output == new_output, old_text == new_text
            counts["paired_returned_responses"] += 1
            counts["pairs_with_both_answers_complete"] += previous["answer_complete"] and event["answer_complete"]
            counts["identical_generated_token_streams" if same_tokens else "different_generated_token_streams"] += 1
            counts["exact_final_text_matches" if same_text else "different_final_texts"] += 1
            counts["exact_nonempty_final_text_matches"] += same_text and bool(old_text)
            counts["both_final_texts_empty"] += not old_text and not new_text
            evidence.append([case_id, prompt_hash, old_output, new_output,
                             ev.digest(old_text.encode("utf-8")), ev.digest(new_text.encode("utf-8"))])
    evidence.sort(key=lambda item: item[0])
    return protocol, {
        "selected_question_pairs": len(reference), **dict(counts),
        "question_pairs_without_returned_prompt_verification": len(reference) - counts["paired_returned_responses"],
        "all_question_prompt_hashes_verified": counts["paired_returned_responses"] == len(reference),
        "frozen_question_rows_and_complete_union_verified": True,
        "system_prompt_sha256": baseline.manifest["system_prompt_sha256"],
        "generation_settings_match_for_initialized_controls": True,
        "paired_comparison_evidence_sha256": ev.digest(shared.canonical(evidence)),
        "token_stream_comparison": "Equality of hashes of every generated token, including protocol and reasoning tokens; reasoning text is not retained or published.",
        "final_text_comparison": "Exact equality of parsed final-answer strings, without trimming or Unicode normalization; empty-string matches are counted separately.",
    }


def summarize(*, dataset, tail_dataset, control_manifest, baseline_run,
              prefix_run, tail_run, root=ROOT):
    root = Path(root).resolve()
    cases, dataset_hash = ev.load_cases(shared.inside(dataset, root / "evals"))
    tail, tail_hash = ev.load_cases(shared.inside(tail_dataset, root / "runs"))
    control, control_hash = shared.read_json(shared.inside(control_manifest, root / "manifests"))
    prefix_ids = control.get("first_four_case_ids")
    if not isinstance(prefix_ids, list) or not prefix_ids or len(prefix_ids) >= len(cases):
        shared.fail("The control prefix does not identify a proper nonempty dataset prefix.")
    prefix = cases[:len(prefix_ids)]
    if (control.get("frozen_dataset_sha256") != dataset_hash
            or control.get("remaining_dataset_sha256") != tail_hash
            or prefix_ids != [case["id"] for case in prefix]
            or control.get("remaining_twenty_case_ids") != [case["id"] for case in tail]
            or tail != cases[len(prefix):]):
        shared.fail("The recorded control split does not match the exact frozen prefix and tail.")
    directories = [shared.inside(path, root / "runs") for path in (baseline_run, prefix_run, tail_run)]
    if len(set(directories)) != len(directories):
        shared.fail("The baseline and two repeat controls must use distinct run directories.")
    baseline = shared.snapshot(directories[0], cases, dataset_hash)
    # This is intentionally the FULL source hash: the first run selected the
    # first four rows of that file, rather than reading a separate four-row file.
    prefix_snapshot = shared.snapshot(directories[1], prefix, dataset_hash)
    tail_snapshot = shared.snapshot(directories[2], tail, tail_hash)
    repeats = [prefix_snapshot, tail_snapshot]
    protocol, comparison = compare_repeats(baseline, repeats)
    prior, current = shared.aggregate([baseline]), shared.aggregate(repeats)
    return {
        "schema_version": 1, "experiment": "unchanged_inkling_repeat_control",
        "generated_at": ev.now(), "contains_answer_text": False,
        "provider_invoice_verified": False, "accuracy_or_improvement_score_assigned": False,
        "partial": prior["partial"] or current["partial"],
        "protocol": protocol, "comparison": comparison,
        "observations": {"original_baseline": prior, "repeat_control": current},
        "repeat_control_additional_estimated_or_reserved_usd": current["cost"]["journal_accounted_or_reserved_usd"],
        "planned_control_budget_usd": shared.number(control["total_control_budget_usd"]),
        "provenance": {"control_manifest_sha256": control_hash,
                       "frozen_question_dataset_sha256": dataset_hash,
                       "tail_question_dataset_sha256": tail_hash,
                       "baseline": baseline.provenance,
                       "prefix_control": prefix_snapshot.provenance,
                       "tail_control": tail_snapshot.provenance},
        "limitations": [
            "This is a repeated unchanged-model control, separate from the adapter evaluation; the original baseline remains preserved.",
            "Matching request settings and prompt hashes do not establish identical provider weights or backend execution. The provider weight revision is unpinned, so this report does not assign a cause to observed variation.",
            "Token-stream equality and final-text equality are different observations. Neither agreement nor disagreement measures biblical accuracy.",
            "These are diagnostic development questions. Completion and response variation do not establish adaptation improvement or regression.",
            "The control was expanded after variation appeared in the initial prefix. This is a diagnostic comparison, not a preregistered estimate of variation across all possible questions.",
            "Token-price estimates and local reservations are not reconciled invoices. Latency also depends on service load and concurrent training.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(ROOT / "evals/comparison-large-v1.jsonl"))
    parser.add_argument("--tail-dataset", default=str(ROOT / "runs/inkling-training-control-v2/base-repeat-tail.jsonl"))
    parser.add_argument("--control-manifest", default=str(ROOT / "manifests/inkling-repeat-control-v1.json"))
    parser.add_argument("--baseline-run", default=str(ROOT / "runs/comparison-large-inkling-v1"))
    parser.add_argument("--prefix-run", default=str(ROOT / "runs/inkling-base-repeat-control-v1"))
    parser.add_argument("--tail-run", default=str(ROOT / "runs/inkling-base-repeat-tail-control-v1"))
    parser.add_argument("--output", default=str(ROOT / "reports/inkling-repeat-control-v1.json"))
    arguments = vars(parser.parse_args(argv))
    try:
        output = shared.inside(arguments.pop("output"), ROOT / "reports")
        if output.suffix != ".json":
            shared.fail("Public repeat-control reports must be JSON files inside reports.")
        result = summarize(**arguments)
        output.parent.mkdir(parents=True, exist_ok=True)
        ev.write_json(output, result)
    except Exception:
        print("Repeat-control summary stopped: local comparison evidence did not validate.", file=sys.stderr)
        return 2
    print(json.dumps({"partial": result["partial"], "comparison": result["comparison"],
                      "repeat_control_additional_estimated_or_reserved_usd": result["repeat_control_additional_estimated_or_reserved_usd"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
