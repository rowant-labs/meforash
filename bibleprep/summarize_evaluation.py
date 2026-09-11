"""Create publishable aggregate evaluation reports from local journals only."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from bibleprep import evaluate as ev


ROOT = Path(__file__).resolve().parents[1]
REPORTS_ROOT = ROOT / "reports"
CATEGORIES = {"comparison", "grammar", "historical_context", "instruction_retention", "life_reflection",
              "metadata_lookup", "source_boundary", "translation"}
LANGUAGES = {"aramaic", "greek", "hebrew", "mixed"}
MODELS = {"openai/gpt-oss-120b", "openai/gpt-oss-20b", "Qwen/Qwen3.8-27B",
          "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16", "thinkingmachines/Inkling-Small", "thinkingmachines/Inkling",
          "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16", "moonshotai/Kimi-K2.6"}
COUNTS = ("selected_cases", "started_requests", "received_results", "completed_responses", "successful_answers", "incomplete_answers",
          "errors", "unresolved_requests", "not_started", "pending_results", "scholarly_reviews_pending")


def inside(path, root):
    path = Path(path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ev.EvaluationError("The selected path is outside the permitted project artifact directory.") from exc
    return path


def number(value, *, integer=False):
    if not ev.finite_nonnegative(value) or (integer and not isinstance(value, int)):
        raise ev.EvaluationError("A journal contains an invalid numeric aggregate field.")
    return value


def safe_hash(value):
    return value if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) else None


def public_settings(settings):
    """Allowlist settings; do not copy provider endpoints, arbitrary metadata, or identities."""
    result = {
        "model": settings.get("model") if settings.get("model") in MODELS else "other",
        "model_revision": "provider_revision_unpinned",
        "evidence_mode": settings.get("evidence_mode") if settings.get("evidence_mode") in {"none", "provided"} else "unknown",
        "reasoning_effort": settings.get("reasoning_effort") if settings.get("reasoning_effort") in {"low", "medium", "high", "xhigh", "on", "off"} else "unspecified",
    }
    for key in ("max_input_tokens", "max_output_tokens", "temperature", "seed"):
        if key in settings:
            result[key] = number(settings[key])
    if isinstance(settings.get("prompt_date"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", settings["prompt_date"]):
        result["prompt_date"] = settings["prompt_date"]
    for key in ("chat_template_sha256", "tokenizer_sha256"):
        if safe_hash(settings.get(key)):
            result[key] = settings[key]
    return result


def grouped_counts(selected, starts, finished, case_metadata, field, allowed):
    groups = {}
    for case_id in selected:
        group = case_metadata.get(case_id, {}).get(field)
        group = group if group in allowed else "unknown"
        counts = groups.setdefault(group, Counter())
        counts["selected"] += 1
        event = finished.get(case_id)
        if case_id in starts:
            counts["started"] += 1
        if event is None:
            counts["pending"] += 1
        elif event["event"] == "error":
            counts["errors"] += 1
        elif event.get("answer_complete") is True:
            counts["successful_answers"] += 1
        else:
            counts["incomplete_answers"] += 1
    keys = ("selected", "started", "successful_answers", "incomplete_answers", "errors", "pending")
    return {group: {key: counts[key] for key in keys} for group, counts in sorted(groups.items())}


def summarize_run(run_dir, cases, dataset_hash, *, case_filter=None, subset_hash=None):
    run_dir = inside(run_dir, ev.RUNS_ROOT)
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,120}", run_dir.name):
        raise ev.EvaluationError("Run directory name is not suitable for a public aggregate label.")
    manifest_data = (run_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_data)
    selected = manifest["case_ids"]
    if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected) or len(selected) != len(set(selected)):
        raise ev.EvaluationError("Run manifest has invalid or duplicate case identifiers.")
    journal_path = run_dir / "events.jsonl"
    journal_data = journal_path.read_bytes() if journal_path.exists() else b""
    incomplete_tail = bool(journal_data and not journal_data.endswith(b"\n"))
    committed = journal_data[:journal_data.rfind(b"\n") + 1] if incomplete_tail else journal_data
    events = [json.loads(line) for line in committed.decode("utf-8").splitlines() if line.strip()]
    # Validate the full journal before selecting observations; never alter source artifacts.
    ev.ledger(events)
    original_selected_count = len(selected)
    if case_filter is not None:
        if not case_filter <= set(selected):
            raise ev.EvaluationError("A run did not select every requested comparison case.")
        selected = [case_id for case_id in selected if case_id in case_filter]
        events = [event for event in events if event.get("case_id") in case_filter]
    accounted, _, uncertain = ev.ledger(events)
    starts = {event["case_id"]: event for event in events if event["event"] == "started"}
    finished = {event["case_id"]: event for event in events if event["event"] in {"completed", "error"}}
    if any(event.get("event") not in {"started", "completed", "error"} for event in events) or not set(starts) <= set(selected):
        raise ev.EvaluationError("Journal and manifest request identities do not match.")
    for event in starts.values():
        number(event["reserved_cost_usd"])
    for event in finished.values():
        number(event["accounted_cost_usd"])
    completed = [event for event in finished.values() if event["event"] == "completed"]
    errors = sum(event["event"] == "error" for event in finished.values())
    counts = {
        "selected_cases": len(selected), "started_requests": len(starts), "received_results": len(finished),
        "completed_responses": len(completed),
        "successful_answers": sum(event.get("answer_complete") is True for event in completed),
        "incomplete_answers": sum(event.get("answer_complete") is not True for event in completed),
        "errors": errors, "unresolved_requests": len(set(starts) - set(finished)),
        "not_started": len(selected) - len(starts), "pending_results": len(selected) - len(finished),
        # The journals provide no scholarly scoring workflow. All received answers need review.
        "scholarly_reviews_pending": len(completed),
    }
    settings = manifest["settings"]
    input_price, output_price = settings.get("input_price_per_million"), settings.get("output_price_per_million")
    prices_known = all(ev.finite_nonnegative(value) for value in (input_price, output_price))
    tokens = {"input": 0, "output": 0, "successful_answer_input": 0, "successful_answer_output": 0,
              "results_with_usage": 0, "results_missing_usage": 0}
    formats = Counter()
    for event in completed:
        usage = event.get("usage")
        if isinstance(usage, dict) and all(isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool)
                                           and usage[key] >= 0 for key in ("input_tokens", "output_tokens")):
            tokens["input"] += usage["input_tokens"]
            tokens["output"] += usage["output_tokens"]
            tokens["results_with_usage"] += 1
            if event.get("answer_complete") is True:
                tokens["successful_answer_input"] += usage["input_tokens"]
                tokens["successful_answer_output"] += usage["output_tokens"]
        else:
            tokens["results_missing_usage"] += 1
        for check in event.get("format_checks", []):
            status = check.get("status")
            formats[status if status in {"pass", "fail", "not_implemented"} else "unknown"] += 1
    metadata_matches = manifest.get("dataset_sha256") == dataset_hash
    metadata = {case["id"]: case for case in cases} if metadata_matches else {}
    return {
        "run": run_dir.name,
        "source_hashes": {"manifest_sha256": ev.digest(manifest_data),
                          "events_sha256": ev.digest(journal_data) if journal_path.exists() else None,
                          "dataset_sha256": safe_hash(manifest.get("dataset_sha256")),
                          "subset_dataset_sha256": subset_hash},
        "observation_scope": "verified_subset" if case_filter is not None else "entire_run",
        "original_selected_cases": original_selected_count,
        "status": "partial" if incomplete_tail else "dry_run" if not starts else "partial" if counts["pending_results"] else "complete",
        "partial": bool(counts["pending_results"] or incomplete_tail), "journal_has_incomplete_tail": incomplete_tail,
        "settings": public_settings(settings),
        "counts": counts, "tokens": tokens,
        "cost": {"known_token_estimate_usd": (tokens["input"] * input_price + tokens["output"] * output_price) / 1_000_000 if prices_known else None,
                 "successful_answer_token_estimate_usd": (tokens["successful_answer_input"] * input_price + tokens["successful_answer_output"] * output_price) / 1_000_000 if prices_known else None,
                 "input_price_per_million": input_price if prices_known else None,
                 "output_price_per_million": output_price if prices_known else None,
                 "journal_accounted_or_reserved_usd": number(accounted),
                 "uncertain_accounted_or_reserved_usd": sum(finished.get(case_id, {}).get("accounted_cost_usd", starts[case_id]["reserved_cost_usd"]) for case_id in uncertain),
                 "uncertain_requests": len(uncertain), "provider_invoice_verified": False,
                 "token_estimate_covers_all_started_requests": prices_known and not uncertain and not tokens["results_missing_usage"] and not errors},
        "format_checks": dict(sorted(formats.items())), "format_checks_are_scholarly_scores": False,
        "category_metadata_matches_dataset": metadata_matches,
        "by_category": grouped_counts(selected, starts, finished, metadata, "category", CATEGORIES),
        "by_language": grouped_counts(selected, starts, finished, metadata, "language", LANGUAGES),
        "scholarly_review": "pending; no biblical accuracy or training improvement score assigned",
    }


def summarize(run_dirs, *, dataset=ev.DEFAULT_DATASET, subset_dataset=None):
    resolved = [inside(path, ev.RUNS_ROOT) for path in run_dirs]
    if not resolved or len(resolved) != len(set(resolved)):
        raise ev.EvaluationError("Select at least one distinct run directory; duplicates would double-count results.")
    cases, dataset_hash = ev.load_cases(dataset)
    if subset_dataset is None:
        runs = [summarize_run(path, cases, dataset_hash) for path in resolved]
    else:
        subset, subset_hash = ev.load_cases(subset_dataset)
        source_by_id = {case["id"]: case for case in cases}
        if any(source_by_id.get(case["id"]) != case for case in subset):
            raise ev.EvaluationError("Comparison cases must be unchanged rows of the source dataset.")
        case_filter = {case["id"] for case in subset}
        runs = []
        for path in resolved:
            recorded_hash = json.loads((path / "manifest.json").read_text()).get("dataset_sha256")
            if recorded_hash == dataset_hash:
                run_cases, run_hash = cases, dataset_hash
            elif recorded_hash == subset_hash:
                run_cases, run_hash = subset, subset_hash
            else:
                raise ev.EvaluationError("Run dataset does not match either verified comparison dataset.")
            runs.append(summarize_run(path, run_cases, run_hash, case_filter=case_filter, subset_hash=subset_hash))
    known_estimates = [run["cost"]["known_token_estimate_usd"] for run in runs]
    return {
        "schema_version": 1, "generated_at": ev.now(),
        "scope": "aggregate observations across specified development runs; repeated questions count once per run",
        "contains_answer_text": False, "provider_invoice_verified": False,
        "partial": any(run["partial"] for run in runs),
        "totals": {"runs": len(runs), **{key: sum(run["counts"][key] for run in runs) for key in COUNTS},
                   "input_tokens": sum(run["tokens"]["input"] for run in runs),
                   "output_tokens": sum(run["tokens"]["output"] for run in runs),
                   "known_token_estimate_usd": sum(known_estimates) if all(value is not None for value in known_estimates) else None,
                   "uncertain_accounted_or_reserved_usd": sum(run["cost"]["uncertain_accounted_or_reserved_usd"] for run in runs),
                   "journal_accounted_or_reserved_usd": sum(run["cost"]["journal_accounted_or_reserved_usd"] for run in runs)},
        "runs": runs,
        "limitations": ["Completion and format counts do not establish historical correctness.",
                        "Scholarly review remains pending for all received answers.",
                        "Token-price estimates and journal reservations are not reconciled provider invoices.",
                        "Partial journals describe only the snapshot read; rerun after completion for final totals."],
    }


def write_report(report, output):
    output = inside(output, REPORTS_ROOT)
    if output.suffix != ".json":
        raise ev.EvaluationError("Aggregate reports must be JSON files inside reports/.")
    output.parent.mkdir(parents=True, exist_ok=True)
    ev.write_json(output, report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+")
    parser.add_argument("--dataset", default=str(ev.DEFAULT_DATASET))
    parser.add_argument("--subset-dataset", help="Compare unchanged subset rows across original and subset runs.")
    parser.add_argument("--output", default=str(REPORTS_ROOT / "evaluation-summary.json"))
    args = parser.parse_args(argv)
    try:
        report = summarize(args.run_dirs, dataset=args.dataset, subset_dataset=args.subset_dataset)
        write_report(report, args.output)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ev.EvaluationError) else "Local evaluation artifacts could not be summarized safely."
        print("Summary stopped: " + message, file=sys.stderr)
        return 2
    print(json.dumps({"report": Path(args.output).name, "partial": report["partial"], "totals": report["totals"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
