"""Verify and summarize one original-text adaptation experiment without model calls.

Only allowlisted aggregates and content hashes leave private run files. Dataset
rows, answers, provider identifiers, checkpoint references, and paths never do.
Missing results stay missing; response completion is not an accuracy score.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import statistics
import sys

from bibleprep import evaluate as ev


ROOT = Path(__file__).resolve().parents[1]
MODEL = "thinkingmachines/Inkling"
SAMPLING_KEYS = (
    "model", "model_version", "max_input_tokens", "max_output_tokens",
    "output_limit_field", "reasoning_effort", "evidence_mode", "temperature", "seed",
    "comparison_manifest_sha256", "tokenizer_revision", "tokenizer_sha256",
    "chat_template_sha256", "renderer_profile", "renderer_reference_revision",
    "renderer", "tinker_version", "transformers_version", "tokenizers_version",
    "jinja2_version", "native_renderer_packages", "torch_version",
    "thinking_effort_numeric", "hf_chat_template_used",
)
COUNTS = ("selected", "started", "received", "complete_answers", "incomplete_answers",
          "errors", "unresolved", "not_started", "missing_results", "missing_usage")
LANGUAGES = {"hebrew", "aramaic", "greek", "mixed"}


def fail(message):
    raise ev.EvaluationError(message)


def number(value, *, integer=False):
    if (type(value) not in (int, float) or not math.isfinite(value) or value < 0
            or (integer and type(value) is not int)):
        fail("An aggregate contains an invalid numeric field.")
    return value


def hash_value(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        fail("A required provenance hash is missing or invalid.")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode()


def inside(path, root):
    result = Path(path).resolve()
    if not result.is_relative_to(Path(root).resolve()):
        fail("An artifact is outside its permitted project directory.")
    return result


def read_json(path):
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        fail("An experiment artifact is not a JSON object.")
    return value, ev.digest(raw)


def read_journal(path):
    raw = path.read_bytes() if path.exists() else b""
    incomplete = bool(raw and not raw.endswith(b"\n"))
    committed = raw[:raw.rfind(b"\n") + 1] if incomplete else raw
    return [json.loads(line) for line in committed.splitlines() if line.strip()], {
        "events_sha256": ev.digest(raw), "journal_has_incomplete_tail": incomplete}


@dataclass
class Snapshot:
    cases: list[dict]
    dataset_hash: str
    manifest: dict | None
    events: list[dict]
    provenance: dict


def snapshot(run_dir, cases, dataset_hash):
    manifest_file = run_dir / "manifest.json"
    if not manifest_file.exists():
        if run_dir.exists() and any(run_dir.iterdir()):
            fail("An evaluation directory has artifacts without a manifest.")
        return Snapshot(cases, dataset_hash, None, [], {
            "dataset_sha256": dataset_hash, "manifest_sha256": None,
            "events_sha256": None, "journal_has_incomplete_tail": False})
    manifest, manifest_hash = read_json(manifest_file)
    if manifest.get("dataset_sha256") != dataset_hash:
        fail("An evaluation manifest does not match the exact dataset bytes.")
    if manifest.get("case_ids") != [case["id"] for case in cases]:
        fail("An evaluation manifest does not select its complete dataset in order.")
    identity = {key: manifest[key] for key in (
        "dataset_sha256", "system_prompt_sha256", "settings", "case_ids", "schema_version")}
    if manifest.get("fingerprint") != ev.digest(ev.json_bytes(identity)):
        fail("An evaluation manifest fingerprint is inconsistent.")
    hash_value(manifest["system_prompt_sha256"])
    events, provenance = read_journal(run_dir / "events.jsonl")
    provenance.update(dataset_sha256=dataset_hash, manifest_sha256=manifest_hash)
    return Snapshot(cases, dataset_hash, manifest, events, provenance)


def validate_events(snap):
    """Require a single reservation/result pair per question, retaining uncertainty."""
    selected = {case["id"] for case in snap.cases}
    starts, results = {}, {}
    for event in snap.events:
        if not isinstance(event, dict) or event.get("case_id") not in selected:
            fail("A journal contains an unknown question identity.")
        case_id, kind = event["case_id"], event.get("event")
        if kind == "started":
            if case_id in starts:
                fail("A question was reserved more than once.")
            number(event["reserved_cost_usd"])
            starts[case_id] = event
        elif kind in {"completed", "error"}:
            if case_id not in starts or case_id in results:
                fail("A result lacks one preceding reservation or is duplicated.")
            number(event["accounted_cost_usd"])
            number(event["elapsed_seconds"])
            if kind == "completed":
                raw = event.get("raw_response_redacted")
                if not isinstance(raw, dict):
                    fail("A received answer lacks the native response evidence.")
                hash_value(raw.get("native_tinker", {}).get("prompt_sha256"))
                answer, finish = ev.answer_details(raw)
                observed_complete = bool(isinstance(answer, str) and answer.strip()
                                         and finish == "stop" and not event.get("truncated"))
                if (type(event.get("answer_complete")) is not bool
                        or event["answer_complete"] != observed_complete
                        or event.get("finish_reason") != finish):
                    fail("Response completion fields disagree with the received answer.")
                usage = event.get("usage")
                if usage is not None:
                    if not isinstance(usage, dict):
                        fail("A received result has invalid token usage.")
                    for key in ("input_tokens", "output_tokens"):
                        number(usage.get(key), integer=True)
                    native_usage = ev.usage_details(raw)
                    if native_usage is None or any(usage[key] != native_usage[key]
                                                  for key in ("input_tokens", "output_tokens")):
                        fail("Journal and native response token counts disagree.")
            results[case_id] = event
        else:
            fail("An evaluation journal contains an unsupported event.")
    return starts, results


def public_protocol(settings):
    """All output strings are known categories; arbitrary manifest text is excluded."""
    if (settings.get("model") != MODEL or settings.get("renderer_profile") != "tml_v0"
            or settings.get("renderer") != "official_tml_renderers"
            or settings.get("model_version") != "provider_revision_unpinned"
            or settings.get("evidence_mode") not in {"none", "provided"}
            or settings.get("reasoning_effort") not in {"low", "medium", "high"}):
        fail("The comparison is not using the supported native Inkling protocol.")
    out = {"model": MODEL, "provider_weight_revision": "unpinned",
           "renderer": "official native TML v0", "evidence_mode": settings["evidence_mode"],
           "reasoning_effort": settings["reasoning_effort"]}
    for key in ("max_input_tokens", "max_output_tokens", "seed"):
        out[key] = number(settings[key], integer=True)
    for key in ("temperature", "thinking_effort_numeric"):
        out[key] = number(settings[key])
    for key in ("tokenizer_sha256", "chat_template_sha256", "comparison_manifest_sha256"):
        out[key] = hash_value(settings[key])
    out["settings_sha256"] = ev.digest(canonical({key: settings[key] for key in SAMPLING_KEYS}))
    return out


def compare_snapshots(baseline, shards, *, sampler_path=None, checkpoint_hash=None):
    """Validate all case content, settings, checkpoint identity, and returned prompts."""
    if baseline.manifest is None:
        fail("The unchanged-model baseline manifest is required.")
    reference = {case["id"]: case for case in baseline.cases}
    if len(reference) != len(baseline.cases):
        fail("The baseline contains duplicate question identities.")
    seen = set()
    for shard in shards:
        for case in shard.cases:
            if case["id"] in seen or reference.get(case["id"]) != case:
                fail("Evaluation shards overlap or change a frozen question row.")
            seen.add(case["id"])
    if seen != set(reference):
        fail("Evaluation shards do not cover exactly the complete frozen dataset.")
    settings = baseline.manifest["settings"]
    protocol = public_protocol(settings)
    if any(key not in settings for key in SAMPLING_KEYS):
        fail("The baseline is missing an essential sampling setting.")
    if settings.get("transport") != "native_tinker_comparison":
        fail("The baseline is not an unchanged-model comparison run.")
    baseline_starts, baseline_results = validate_events(baseline)
    matched = 0
    initialized = 0
    for shard in shards:
        _, results = validate_events(shard)
        if shard.manifest is None:
            continue
        initialized += 1
        other = shard.manifest["settings"]
        if (shard.manifest["system_prompt_sha256"] != baseline.manifest["system_prompt_sha256"]
                or any(key not in other or other[key] != settings[key] for key in SAMPLING_KEYS)):
            fail("Before/after system prompts or generation settings differ.")
        if (other.get("transport") != "native_tinker_inkling_adapter"
                or other.get("model_state") != "original_text_lora_adapter"
                or sampler_path is None or checkpoint_hash is None
                or other.get("adapter_sampler_path") != sampler_path
                or other.get("checkpoint_reference_sha256") != checkpoint_hash):
            fail("An adapter evaluation does not reference the completed training checkpoint.")
        for case_id, event in results.items():
            if event["event"] != "completed":
                continue
            prior = baseline_results.get(case_id)
            if prior is None or prior["event"] != "completed":
                fail("A received adapter answer lacks a corresponding baseline prompt hash.")
            prompt_hash = event["raw_response_redacted"]["native_tinker"]["prompt_sha256"]
            prior_hash = prior["raw_response_redacted"]["native_tinker"]["prompt_sha256"]
            if prompt_hash != prior_hash:
                fail("A returned answer used different prompt tokens from the baseline.")
            matched += 1
    return protocol, {
        "frozen_question_rows_and_complete_shard_union_verified": True,
        "initialized_adapter_shards": initialized, "planned_adapter_shards": len(shards),
        "generation_settings_match_for_initialized_shards": True,
        "checkpoint_identity_matches_for_initialized_shards": True,
        "paired_prompt_hashes_verified": matched,
        "question_pairs_without_returned_prompt_verification": len(reference) - matched,
        "all_question_prompt_hashes_verified": matched == len(reference),
    }


def aggregate(snapshots):
    counts = Counter({key: 0 for key in COUNTS})
    tokens = Counter(input=0, output=0)
    latencies, deadlines, languages = [], set(), {}
    accounted = known = uncertain = 0.0
    tail = False
    for snap in snapshots:
        starts, results = validate_events(snap)
        settings = snap.manifest["settings"] if snap.manifest else None
        if settings is not None:
            input_price = number(settings["input_price_per_million"])
            output_price = number(settings["output_price_per_million"])
            deadlines.add(number(settings["timeout_seconds"]))
        counts.update(selected=len(snap.cases), started=len(starts), received=len(results),
                      unresolved=len(set(starts) - set(results)),
                      not_started=len(snap.cases) - len(starts),
                      missing_results=len(snap.cases) - len(results))
        tail |= snap.provenance["journal_has_incomplete_tail"]
        for case in snap.cases:
            language = case.get("language") if case.get("language") in LANGUAGES else "unknown"
            group = languages.setdefault(language, Counter(selected=0, complete_answers=0,
                                                         incomplete_answers=0, errors=0, missing_results=0))
            group["selected"] += 1
            case_id = case["id"]
            event = results.get(case_id)
            if event is None:
                group["missing_results"] += 1
                if case_id in starts:
                    reserved = number(starts[case_id]["reserved_cost_usd"])
                    accounted += reserved
                    uncertain += reserved
                continue
            charged = number(event["accounted_cost_usd"])
            accounted += charged
            if (event.get("accounting_uncertain") or event.get("limit_breach")
                    or event["event"] == "error" or event.get("usage") is None):
                uncertain += charged
            if event["event"] == "error":
                counts["errors"] += 1
                group["errors"] += 1
                continue
            label = "complete_answers" if event["answer_complete"] else "incomplete_answers"
            counts[label] += 1
            group[label] += 1
            latencies.append(number(event["elapsed_seconds"]))
            usage = event.get("usage")
            if usage is None:
                counts["missing_usage"] += 1
            else:
                tokens["input"] += usage["input_tokens"]
                tokens["output"] += usage["output_tokens"]
                known += (usage["input_tokens"] * input_price + usage["output_tokens"] * output_price) / 1e6
    return {
        "counts": dict(counts), "tokens": dict(tokens),
        "partial": bool(counts["missing_results"] or tail),
        "journal_has_incomplete_tail": tail,
        "latency_seconds": {"returned_responses": len(latencies),
                            "median": statistics.median(latencies) if latencies else None,
                            "mean": statistics.mean(latencies) if latencies else None,
                            "minimum": min(latencies) if latencies else None,
                            "maximum": max(latencies) if latencies else None},
        "request_deadline_seconds": sorted(deadlines),
        "cost": {"known_token_estimate_usd": known,
                 "journal_accounted_or_reserved_usd": accounted,
                 "uncertain_accounted_or_reserved_usd": uncertain,
                 "provider_invoice_verified": False},
        "by_language": {key: dict(value) for key, value in sorted(languages.items())},
    }


def nll_metric(value):
    if not isinstance(value, dict):
        fail("A training NLL metric is missing.")
    result = {key: number(value[key], integer=key.endswith("tokens")) for key in (
        "weighted_nll", "weighted_loss_sum", "loss_tokens", "processed_tokens")}
    if (not result["loss_tokens"] or result["loss_tokens"] > result["processed_tokens"]
            or not math.isclose(result["weighted_nll"] * result["loss_tokens"],
                                result["weighted_loss_sum"], rel_tol=1e-8, abs_tol=1e-8)):
        fail("A reported NLL disagrees with its loss sum or token denominator.")
    return result


def training_record(directory, phase):
    plan, plan_hash = read_json(directory / "plan.json")
    recipe = plan["recipe"]
    if (plan.get("phase") != phase or recipe.get("model") != MODEL
            or plan.get("recipe_sha256") != ev.digest(canonical(recipe))
            or recipe.get("loss_fn") != "cross_entropy"
            or recipe.get("optimization_loss_reduction") != "sum"):
        fail("A training plan has an incompatible or inconsistent recipe.")
    summary_path = directory / "summary.json"
    summary, summary_hash = read_json(summary_path) if summary_path.exists() else ({}, None)
    status = summary.get("status", "in_progress")
    if status not in {"complete", "stopped_uncertain", "in_progress"}:
        fail("Unsupported training completion status.")
    if summary and (summary.get("recipe_sha256") != plan["recipe_sha256"] or summary.get("phase") != phase):
        fail("Training summary and plan have different experiment identities.")
    result = {"status": status, "recipe_sha256": hash_value(plan["recipe_sha256"]),
              "prepared_corpus_manifest_sha256": hash_value(recipe["manifest_sha256"]),
              "sequence_order_sha256": hash_value(plan["sequence_order_sha256"]),
              "training_sequences": number(plan["training_sequences"], integer=True),
              "training_batches": number(plan["training_batches"], integer=True),
              "training_processed_tokens": number(plan["training_processed_tokens"], integer=True),
              "training_loss_tokens": number(plan["training_loss_tokens"], integer=True),
              "planned_estimated_or_reserved_usd": number(plan["planned_estimated_usd"]),
              "compute_reserve_usd": number(plan["compute_reserve_nano_usd"], integer=True) / 1e9,
              "checkpoint_contingency_usd": number(plan["checkpoint_reserve_nano_usd"], integer=True) / 1e9,
              "checkpoint_ttl_seconds": number(plan["checkpoint_ttl_seconds"], integer=True),
              "baseline_holdout": None, "end_holdout": None, "holdout_nll_change": None,
              "training_weighted_nll": None,
              "provenance": {"plan_sha256": plan_hash, "summary_sha256": summary_hash,
                             "software_manifest_content_sha256": ev.digest(canonical(plan["software_sha256"]))}}
    if not math.isclose(result["planned_estimated_or_reserved_usd"],
                        result["compute_reserve_usd"] + result["checkpoint_contingency_usd"],
                        abs_tol=1e-8, rel_tol=1e-8):
        fail("Training cost estimates disagree with their components.")
    if status == "complete":
        for key in ("training_batches", "training_processed_tokens", "training_loss_tokens"):
            if summary[key] != result[key]:
                fail("Completed training counts disagree with the planned pass.")
        before, after = nll_metric(summary["baseline_holdout"]), nll_metric(summary["end_holdout"])
        if any(before[key] != after[key] for key in ("loss_tokens", "processed_tokens")):
            fail("Before/after NLL denominators differ.")
        result.update(baseline_holdout=before, end_holdout=after,
                      holdout_nll_change=after["weighted_nll"] - before["weighted_nll"],
                      training_weighted_nll=number(summary["training_weighted_nll"]))
    return result, plan


def summarize(*, calibration_run, training_run, baseline_run, dataset, shards, root=ROOT):
    """Shards are ordered (dataset_path, run_directory) pairs; missing runs are allowed."""
    root = Path(root).resolve()
    runs = root / "runs"
    cases, dataset_hash = ev.load_cases(inside(dataset, root / "evals"))
    calibration_dir, training_dir, baseline_dir = [inside(path, runs) for path in
                                                   (calibration_run, training_run, baseline_run)]
    calibration, calibration_plan = training_record(calibration_dir, "calibration")
    training, training_plan = training_record(training_dir, "full")
    if calibration["status"] != "complete" or calibration_plan["recipe"] != training_plan["recipe"]:
        fail("The full pass does not match a completed calibration recipe.")
    sampler_path = checkpoint_hash = None
    if training["status"] == "complete":
        checkpoint, checkpoint_hash = read_json(training_dir / "checkpoints.json")
        sampler_path = checkpoint.get("sampler_path")
        if not isinstance(sampler_path, str) or not re.fullmatch(r"tinker://[A-Za-z0-9._:/-]+", sampler_path):
            fail("The completed training run lacks a valid sampler checkpoint.")
    baseline = snapshot(baseline_dir, cases, dataset_hash)
    snapshots = []
    directories = {calibration_dir, training_dir, baseline_dir}
    if not shards:
        fail("At least one evaluation shard is required.")
    for dataset_path, run_path in shards:
        shard_path = inside(dataset_path, runs)
        run_dir = inside(run_path, runs)
        if run_dir in directories:
            fail("Distinct experiment and evaluation directories are required.")
        directories.add(run_dir)
        shard_cases, shard_hash = ev.load_cases(shard_path)
        snapshots.append(snapshot(run_dir, shard_cases, shard_hash))
    protocol, checks = compare_snapshots(baseline, snapshots,
                                         sampler_path=sampler_path, checkpoint_hash=checkpoint_hash)
    prior, adapted = aggregate([baseline]), aggregate(snapshots)
    checks["system_prompt_sha256"] = baseline.manifest["system_prompt_sha256"]
    return {
        "schema_version": 1, "experiment": "original_text_inkling_adaptation",
        "generated_at": ev.now(), "contains_answer_text": False,
        "provider_invoice_verified": False, "accuracy_or_improvement_score_assigned": False,
        "partial": training["status"] != "complete" or prior["partial"] or adapted["partial"],
        "protocol": protocol, "comparison_validation": checks,
        "training": {"calibration": calibration, "development_pass": training},
        "english_evaluation": {"unchanged_model": prior, "adapted_model": adapted},
        "provenance": {"frozen_question_dataset_sha256": dataset_hash,
                       "baseline": baseline.provenance,
                       "adapter_shards": [item.provenance for item in snapshots]},
        "cost_scope": "Calibration and development training reservations plus the specified baseline and final English evaluations. Earlier model comparisons and calibration retention sampling are excluded.",
        "selected_scope_estimated_or_reserved_usd": (
            calibration["planned_estimated_or_reserved_usd"] + training["planned_estimated_or_reserved_usd"]
            + prior["cost"]["journal_accounted_or_reserved_usd"]
            + adapted["cost"]["journal_accounted_or_reserved_usd"]),
        "limitations": [
            "Response completion and lower next-token loss do not establish better biblical interpretation or English answers.",
            "These are diagnostic development questions, not an unbiased final benchmark; base-model pretraining exposure is unknown.",
            "The frozen NLL validation corpus contains Hebrew and Greek, with no Aramaic chapters. Aramaic is assessed in the English questions.",
            "Checkpoint charges and provider metering remain unreconciled; local estimates are not a provider-enforced spending cap.",
            "Latency includes observed request overhead and depends on service load and shard concurrency; request deadlines are reported separately.",
            "No scholarly accuracy score is computed here. Missing and incomplete results remain explicit.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--calibration-run", default=str(ROOT / "runs/inkling-calibration-v1"))
    p.add_argument("--training-run", default=str(ROOT / "runs/inkling-original-text-v1"))
    p.add_argument("--baseline-run", default=str(ROOT / "runs/comparison-large-inkling-v1"))
    p.add_argument("--dataset", default=str(ROOT / "evals/comparison-large-v1.jsonl"))
    p.add_argument("--shard", nargs=2, action="append", metavar=("DATASET", "RUN"))
    p.add_argument("--output", default=str(ROOT / "reports/inkling-adaptation-v1.json"))
    args = vars(p.parse_args(argv))
    try:
        output = inside(args.pop("output"), ROOT / "reports")
        if output.suffix != ".json":
            fail("Public adaptation reports must be JSON files inside reports.")
        args["shards"] = args.pop("shard") or [
            (ROOT / f"runs/inkling-training-control-v2/eval-shards/{label}.jsonl",
             ROOT / f"runs/inkling-adapted-eval-{label}-v1") for label in ("a", "b", "c")]
        report = summarize(**args)
        output.parent.mkdir(parents=True, exist_ok=True)
        ev.write_json(output, report)
    except Exception:
        print("Adaptation summary stopped: local experiment evidence did not validate.", file=sys.stderr)
        return 2
    print(json.dumps({"partial": report["partial"],
                      "english_evaluation": report["english_evaluation"],
                      "selected_scope_estimated_or_reserved_usd": report["selected_scope_estimated_or_reserved_usd"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
