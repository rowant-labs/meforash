"""Bounded arm F: original-text weights plus reviewed v3 SFT at the unchanged E learning rate.

Planning is offline. Execution additionally requires the fresh evaluation freeze.
All prior preparations, training implementations, and completed runs are preserved.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
from dataclasses import dataclass
import json
import importlib.metadata
import random
import math
import os
from pathlib import Path
import re
import uuid

from bibleprep import train_instruction as v1
from bibleprep import train_inkling as raw
from bibleprep import train_instruction_calibration as v2
from bibleprep import prepare_instruction_revision as preparation

ROOT = raw.ROOT
MANIFEST = "manifests/instruction-target-revision-training-v3.json"
EXPERIMENT = "manifests/instruction-target-revision-experiment-v3.json"
RUN_DIRECTORY = "runs/inkling-instruction-f-v3"
SOURCE_CHECKPOINT_FILE = "runs/inkling-original-text-v1/checkpoints.json"
PREPARATION_SHA256 = "06390023a3c78e88692d73add87a1b7a60c01576b54c265daf68675d653e093c"
REFERENCE_RECIPE_SHA256 = "d05d2b3425783f7e0353b1b4b687ad460ad6dfe6e3ec516ccf3fbd3ec9a49a7f"
ORDER_SHA256 = "1ef94b22549d97edd35116d4f8680c616d38772e1cd4367908ec7ff3e3a8709f"
PLANNED_NANO = 3489455670
PRIOR_RESERVED_NANO = 35435232840
COUNTS = {"training_sequences": 104, "training_batches": 7,
          "training_processed_tokens": 65573, "training_loss_tokens": 16598,
          "holdout_sequences": 16, "two_holdout_forward_tokens": 21674}
EXPERIMENT_BUDGET = {"per_arm_sampling_cap_usd": 1.5, "four_arm_sampling_cap_usd": 6.0,
                     "new_training_reservation_usd": 3.48945567, "incremental_experiment_cap_usd": 10.0}
TrainingError = raw.TrainingError


@dataclass(frozen=True)
class Config:
    arm: str = "F"
    source_checkpoint_file: str = SOURCE_CHECKPOINT_FILE
    batch_size: int = 16
    seed: int = 20260906
    learning_rate: float = 2e-5
    checkpoint_ttl_seconds: int = 30 * 86400
    checkpoint_reserve_usd: float = 3.0
    max_cost_usd: float = 50.0
    timeout_seconds: float = 600.0
    run_dir: str | None = None

    def validate(self):
        if (self.arm != "F" or self.batch_size != 16 or self.seed != 20260906 or self.learning_rate != 2e-5
                or self.checkpoint_ttl_seconds != 30 * 86400 or self.checkpoint_reserve_usd != 3.0
                or self.timeout_seconds != 600.0 or self.source_checkpoint_file != SOURCE_CHECKPOINT_FILE
                or self.run_dir not in (None, RUN_DIRECTORY)):
            raise TrainingError("Arm F fixes the B parent, revised dataset, gentle recipe, single run directory, and deadlines.")
        raw.Config(max_cost_usd=self.max_cost_usd).validate()


def build_training_protocol(root=ROOT):
    """Build portable freeze metadata offline; do not write files or load secrets."""
    root = Path(root)
    reference, reference_hash = v2.load_training_protocol(root)
    if (reference["recipe_sha256"] != REFERENCE_RECIPE_SHA256
            or raw.digest(raw.encoded(reference["recipe"])) != REFERENCE_RECIPE_SHA256
            or reference["sequence_order_sha256"] != ORDER_SHA256):
        raise TrainingError("The fixed E reference recipe or sequence order changed.")
    prep_entry = {"path": preparation.PREPARATION_MANIFEST, "sha256": PREPARATION_SHA256}
    prepared = json.loads(v1.checked_file(root, prep_entry, prefix="manifests"))
    if (prepared.get("schema_version") != 3 or prepared.get("status") != "prepared_not_trained"
            or prepared.get("review_status") != "ai_source_checked" or prepared.get("expert_certified") is not False):
        raise TrainingError("Arm F requires the completed, independently reviewed v3 preparation.")
    recipe = copy.deepcopy(reference["recipe"])
    recipe["manifest_sha256"] = PREPARATION_SHA256
    software = set(reference["software_sha256"]) | {"bibleprep/train_instruction_revision.py",
                "bibleprep/prepare_instruction_revision.py", *prepared["preparation_code_sha256"]}
    compute = (COUNTS["training_processed_tokens"] + COUNTS["two_holdout_forward_tokens"]) * raw.TOKEN_NANO
    if compute != 489455670 or compute + 3 * raw.NANO != PLANNED_NANO:
        raise TrainingError("The exact revised-token reservation differs from the frozen price.")
    return {"schema_version": 3, "status": "frozen_training_recipe",
            "experiment_id": "instruction-target-revision-v3", "arm": "F", "parent_arm": "B",
            "changed_training_parameter": "reviewed_instruction_dataset",
            "reference_training_manifest": {"path": v2.MANIFEST, "sha256": reference_hash},
            "reference_recipe": reference["recipe"], "reference_recipe_sha256": REFERENCE_RECIPE_SHA256,
            "recipe": recipe, "recipe_sha256": raw.digest(raw.encoded(recipe)), "preparation": prep_entry,
            "sequence_order_sha256": ORDER_SHA256, "counts": dict(COUNTS),
            "source_adapter": reference["source_adapter"],
            "software_sha256": {name: raw.digest(v1.project_file(root, name).read_bytes()) for name in sorted(software)},
            "checkpoint_ttl_seconds": 30 * 86400, "checkpoint_reserve_nano_usd": 3 * raw.NANO,
            "compute_reserve_nano_usd": compute, "planned_nano_usd": PLANNED_NANO,
            "shared_training_cap_usd": 50, "incremental_experiment_cap_usd": 10,
            "existing_training_reserved_estimated_usd_at_preparation": raw.money(PRIOR_RESERVED_NANO),
            "expected_total_training_reserved_estimated_usd_after_F": raw.money(PRIOR_RESERVED_NANO + PLANNED_NANO),
            "cost_status": "conservative_reservation_not_invoice",
            "learning_rate_status": "experimental_gentle_recipe_unchanged_from_E_not_official_optimized_rate",
            "primary_source_verification": copy.deepcopy(reference["primary_source_verification"]),
            "execution_gate": "Frozen fresh evaluation, criteria-review hash, execution protocol, and $10 incremental cap are required before provider operations; evaluation contents are never training inputs."}


def load_training_protocol(root=ROOT):
    try:
        data = v1.project_file(root, MANIFEST, prefix="manifests").read_bytes()
        protocol = json.loads(data)
        if protocol != build_training_protocol(root):
            raise TrainingError("Arm F training protocol differs from its fixed recipe, data, or software identities.")
        return protocol, raw.digest(data)
    except (OSError, ValueError, KeyError, TypeError):
        raise TrainingError("The frozen F training protocol could not be verified.") from None


def verified_rows(root, protocol):
    """Fully recheck v3 approvals, source evidence, immutable rows, and native masks."""
    try:
        manifest = json.loads(v1.checked_file(root, protocol["preparation"], prefix="manifests"))
        if importlib.metadata.version("tinker") != raw.SDK_VERSION:
            raise TrainingError("Instruction training requires the pinned Tinker runtime.")
        if any(importlib.metadata.version(name) != version for name, version in manifest["runtime_versions"].items()):
            raise TrainingError("The native renderer runtime changed after preparation.")
        rows = preparation.verify_prepared(root, manifest)
        selected = sorted(rows["train"], key=lambda row: row["id"])
        random.Random(20260906).shuffle(selected)
        holdout = rows["validation"]
        batches = [selected[i:i + 16] for i in range(0, len(selected), 16)]
        counts = {"training_sequences": len(selected), "training_batches": len(batches),
                  "training_processed_tokens": sum(len(row["input_ids"]) for row in selected),
                  "training_loss_tokens": sum(sum(row["weights"]) for row in selected),
                  "holdout_sequences": len(holdout),
                  "two_holdout_forward_tokens": 2 * sum(len(row["input_ids"]) for row in holdout)}
        if (counts != protocol["counts"]
                or raw.digest(raw.encoded([row["id"] for row in selected])) != ORDER_SHA256
                or [row["id"] for row in holdout] != protocol["recipe"]["validation_ids"]):
            raise TrainingError("The revised data counts, order, or unchanged validation differ from the recipe.")
        return batches, holdout
    except (OSError, ValueError, KeyError, TypeError):
        raise TrainingError("Revised instruction data, review, or runtime verification failed.") from None


def make_plan(config, root=ROOT):
    config.validate()
    protocol, protocol_hash = load_training_protocol(root)
    batches, holdout = verified_rows(root, protocol)
    source = v1.source_receipt(config, root)[0]
    if source != protocol["source_adapter"]:
        raise TrainingError("Arm F must initialize from the exact completed B weights, not E or another instruction adapter.")
    existing = v1.reserved_budget(root)
    if existing + PLANNED_NANO > raw.dollars(config.max_cost_usd):
        raise TrainingError("The proposed F run exceeds the existing shared $50 training ledger.")
    plan = {"schema_version": 3, "phase": "instruction_revision", "arm": "F", "parent_arm": "B",
            "recipe": copy.deepcopy(protocol["recipe"]), "recipe_sha256": protocol["recipe_sha256"],
            "source_adapter": source, "source_checkpoint_file": config.source_checkpoint_file,
            "training_protocol_sha256": protocol_hash, "software_sha256": protocol["software_sha256"],
            "reference_instruction_recipe_sha256": REFERENCE_RECIPE_SHA256,
            "changed_training_parameter": "reviewed_instruction_dataset",
            "sdk_version": raw.SDK_VERSION, "epochs": 1, "fresh_training_client": True,
            "fresh_adapter": False, "optimizer_restored": False, "checkpoint_ttl_seconds": 30 * 86400,
            **protocol["counts"], "sequence_order_sha256": ORDER_SHA256, "compute_rate_usd_per_million": 5.61,
            "compute_reserve_nano_usd": protocol["compute_reserve_nano_usd"],
            "checkpoint_reserve_nano_usd": 3 * raw.NANO, "planned_nano_usd": PLANNED_NANO,
            "planned_estimated_usd": raw.money(PLANNED_NANO),
            "existing_reserved_estimated_usd": raw.money(existing),
            "expected_combined_training_reserved_estimated_usd": raw.money(existing + PLANNED_NANO),
            "learning_rate_status": protocol["learning_rate_status"],
            "loss_interpretation": "assistant_target_prediction_not_translation_accuracy",
            "base_revision_status": "provider_does_not_expose_immutable_base_weight_revision",
            "cost_status": "conservative_reservation_not_invoice", "execution_requires_fresh_evaluation_freeze": True}
    return plan, batches, holdout


def verify_evaluation_freeze(root=ROOT):
    """Hash evaluation/criteria bytes; inspect only freeze and budget metadata."""
    try:
        _, training_hash = load_training_protocol(root)
        contents = v1.project_file(root, EXPERIMENT, prefix="manifests").read_bytes()
        experiment = json.loads(contents)
        if (experiment.get("schema_version") != 3
                or experiment.get("status") != "frozen_before_training_and_sampling"
                or experiment.get("experiment_id") != "instruction-target-revision-v3"
                or experiment.get("training_manifest") != {"path": MANIFEST, "sha256": training_hash}
                or experiment.get("arms", {}).get("F") != "original_text_then_revised_instruction_lr_0.00002"):
            raise TrainingError("Fresh v3 evaluation and execution protocol must be frozen before training.")
        budget = experiment.get("budget")
        if budget != EXPERIMENT_BUDGET:
            raise TrainingError("The execution protocol must retain the authorized $10 incremental cap and fixed per-arm allowances.")
        if (raw.dollars(budget["new_training_reservation_usd"]) != PLANNED_NANO
                or 4 * raw.dollars(budget["per_arm_sampling_cap_usd"]) != raw.dollars(budget["four_arm_sampling_cap_usd"])
                or PLANNED_NANO + raw.dollars(budget["four_arm_sampling_cap_usd"]) > raw.dollars(budget["incremental_experiment_cap_usd"])):
            raise TrainingError("Training plus all four sampling allowances exceed the experiment cap.")
        evaluation = experiment["evaluation"]
        if (evaluation.get("path") != "evals/instruction-target-revision-v3.jsonl"
                or evaluation.get("cases") != 30 or not isinstance(evaluation.get("case_ids"), list)
                or len(evaluation["case_ids"]) != 30 or len(set(evaluation["case_ids"])) != 30):
            raise TrainingError("The revision requires the frozen thirty-case evaluation.")
        v1.checked_file(root, evaluation, prefix="evals")
        metadata_entry = experiment["evaluation_manifest"]
        if metadata_entry.get("path") != "manifests/instruction-target-revision-evaluation-v3.json":
            raise TrainingError("Unexpected evaluation freeze metadata version.")
        metadata = json.loads(v1.checked_file(root, metadata_entry, prefix="manifests"))
        if (metadata.get("schema_version") != 3 or metadata.get("status") != "frozen_before_training_and_sampling"
                or metadata.get("dataset") != evaluation):
            raise TrainingError("Evaluation metadata and experiment hashes/counts disagree.")
        review = experiment["criteria_review"]
        if review.get("path") != "manifests/instruction-target-revision-criteria-review-v3.json":
            raise TrainingError("The separate pre-output criteria review must be bound to execution.")
        v1.checked_file(root, review, prefix="manifests")  # Hash only: no criteria parsing.
        return raw.digest(contents)
    except (OSError, ValueError, KeyError, TypeError):
        raise TrainingError("The v3 execution freeze or budget could not be verified.") from None


class RevisionNativeSession(v1.InstructionNativeSession):
    """F uses the exact weights-only initialization already exercised by D/E.

    Translate only the internal branch label on a copied settings dictionary.
    No globals, imported classes, SDK methods, or caller settings are modified.
    """
    def call(self, operation, rows, settings):
        if settings.get("arm") != "F" or settings.get("adam", {}).get("learning_rate") != 2e-5:
            raise TrainingError("The revision transport only accepts the frozen F recipe.")
        return super().call(operation, rows, {**settings, "arm": "D"})


def revision_worker(connection):
    os.environ["TINKER_TELEMETRY"] = "0"
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        session = RevisionNativeSession()
        try:
            while True:
                request = connection.recv()
                try:
                    connection.send({"ok": True, "result": session.call(*request)})
                except BaseException as exc:
                    safe = {"error_type": type(exc).__name__}
                    if type(getattr(exc, "status_code", None)) is int:
                        safe["http_status"] = exc.status_code
                    connection.send({"ok": False, "error_metadata": safe})
                    break
        except (EOFError, BrokenPipeError, OSError):
            pass
        finally:
            connection.close()


def run(config, *, execute=False, root=ROOT, transport=None):
    config.validate()
    plan, batches, holdout = make_plan(config, root)
    if not execute:
        return {"status": "dry_run", **plan}
    plan["evaluation_freeze_sha256"] = verify_evaluation_freeze(root)
    source_checkpoint = None
    if config.arm == "F":
        source, source_checkpoint = v1.source_receipt(config, root)
        if source != plan["source_adapter"]:
            raise TrainingError("The original-text receipt changed after planning.")
    directory = raw.private_path(root, RUN_DIRECTORY)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    run_id = uuid.uuid4().hex
    raw.write_private(directory / "plan.json", {"run_id": run_id, **plan})
    used = raw.reserve_budget(root, run_id, plan["planned_nano_usd"], raw.dollars(config.max_cost_usd))
    journal = directory / "events.jsonl"
    settings = {"timeout_seconds": config.timeout_seconds, "seed": config.seed, "arm": config.arm,
                "adam": plan["recipe"]["adam"], "checkpoint_ttl_seconds": config.checkpoint_ttl_seconds}
    if source_checkpoint is not None:
        settings["source_checkpoint"] = source_checkpoint
    native = transport
    allocated = op_count = 0

    def invoke(operation, rows=(), *, budget=0, stage="", step=None):
        nonlocal allocated, op_count
        op_count += 1
        allocated += budget
        if allocated > plan["planned_nano_usd"]:
            raise TrainingError("Instruction operations exceed the durable run reservation.")
        event = {"operation_id": op_count, "operation": operation, "stage": stage, "step": step,
                 "reserved_nano_usd": budget, "processed_tokens": sum(len(row["input_ids"]) for row in rows)}
        raw.append_event(journal, {"event": "operation_reserved", **event})
        try:
            # Only already shifted arrays leave the trainer, never review notes,
            # chapter metadata, question rubrics, or evaluation answer keys.
            data = [{key: row[key] for key in ("input_ids", "target_ids", "weights")} for row in rows]
            result = native(operation, data, settings)
            metrics = raw.weighted_nll(rows, result["logprobs"]) if rows else None
            if rows:
                languages = sorted({row["language"] for row in rows})
                metrics["by_language"] = {
                    language: raw.weighted_nll(
                        [row for row in rows if row["language"] == language],
                        [values for row, values in zip(rows, result["logprobs"]) if row["language"] == language])
                    for language in languages}
            if operation in {"state", "sampler"} and (not isinstance(result.get("path"), str)
                                                      or not result["path"].startswith("tinker://")):
                raise TrainingError("Checkpoint reply lacks a valid private reference.")
            raw.append_event(journal, {"event": "operation_complete", **event, "metrics": metrics})
            return result, metrics
        except BaseException as exc:
            raw.append_event(journal, {"event": "operation_uncertain", **event,
                                      "error_metadata": getattr(exc, "error_metadata", {"error_type": type(exc).__name__})})
            raise TrainingError("Instruction operation uncertain; stopped without retry or resume.") from None

    try:
        if native is None:
            from bibleprep.environment import load_project_environment
            load_project_environment()
            if not os.environ.get("TINKER_API_KEY"):
                raise TrainingError("TINKER_API_KEY is unavailable.")
            native = raw.BoundedTrainingTransport(worker=revision_worker)
        invoke("create")
        invoke("verify_client")
        if config.arm == "F":
            invoke("verify_source")
            invoke("load_weights")
        forward_budget = sum(len(row["input_ids"]) for row in holdout) * raw.TOKEN_NANO
        before = invoke("forward", holdout, budget=forward_budget, stage="baseline_sft_validation")[1] if holdout else None
        steps = []
        for index, batch in enumerate(batches, 1):
            _, metrics = invoke("forward_backward", batch, budget=sum(len(row["input_ids"]) for row in batch) * raw.TOKEN_NANO,
                                stage="instruction_training", step=index)
            invoke("optim", stage="instruction_training", step=index)
            steps.append(metrics)
        after = invoke("forward", holdout, budget=forward_budget, stage="end_sft_validation")[1] if holdout else None
        checkpoints = {"training_state_path": None, "sampler_path": None}
        for operation, key in (("state", "training_state_path"), ("sampler", "sampler_path")):
            settings["checkpoint_name"] = "instruction-target-revision-" + config.arm.lower() + "-" + operation
            result, _ = invoke(operation, budget=plan["checkpoint_reserve_nano_usd"] // 2, stage="checkpoint")
            checkpoints[key] = result["path"]
            raw.write_private(directory / "checkpoints.json", checkpoints)
        summary = {"status": "complete", "phase": "instruction_revision", "arm": config.arm, "run_id": run_id,
                   "recipe_sha256": plan["recipe_sha256"], "optimizer_restored": False,
                   "training_protocol_sha256": plan["training_protocol_sha256"],
                   "evaluation_freeze_sha256": plan["evaluation_freeze_sha256"],
                   "source_adapter": plan["source_adapter"],
                   "checkpoint_reference_sha256": raw.digest((directory / "checkpoints.json").read_bytes()),
                   "training_batches": len(steps), "training_processed_tokens": plan["training_processed_tokens"],
                   "training_loss_tokens": plan["training_loss_tokens"],
                   "baseline_sft_validation": before, "end_sft_validation": after,
                   "training_weighted_nll": math.fsum(step["weighted_loss_sum"] for step in steps) / sum(step["loss_tokens"] for step in steps),
                   "loss_interpretation": "assistant_target_prediction_not_translation_accuracy",
                   "planned_estimated_usd": plan["planned_estimated_usd"],
                   "combined_reserved_estimated_usd": raw.money(used), "accounting_is_invoice": False,
                   "checkpoint_ttl_seconds": config.checkpoint_ttl_seconds}
        raw.write_private(directory / "summary.json", summary)
        raw.append_event(journal, {"event": "run_complete", "run_id": run_id})
        return {**summary, "run_directory_name": directory.name}
    except BaseException:
        raw.write_private(directory / "summary.json", {"status": "stopped_uncertain", "phase": "instruction_revision", "arm": config.arm,
                          "run_id": run_id, "recipe_sha256": plan["recipe_sha256"], "accounting_is_invoice": False})
        raise TrainingError("Instruction training stopped; reserved costs remain against the shared cap. Inspect private run status.") from None
    finally:
        if native is not None:
            native.close()


def _check_metrics(metrics, rows):
    if not isinstance(metrics, dict):
        raise TrainingError("The completed revision lacks aligned validation metrics.")
    expected_loss = sum(sum(row["weights"]) for row in rows)
    if (metrics.get("processed_tokens") != sum(len(row["input_ids"]) for row in rows)
            or metrics.get("loss_tokens") != expected_loss
            or any(type(metrics.get(key)) not in (int, float) or not math.isfinite(metrics[key])
                   or metrics[key] < 0 for key in ("weighted_loss_sum", "weighted_nll"))
            or not math.isclose(metrics["weighted_loss_sum"] / expected_loss,
                                metrics["weighted_nll"], rel_tol=1e-10, abs_tol=1e-10)):
        raise TrainingError("Completed revision metrics disagree with the exact target counts.")


def verify_completed_checkpoint(root, checkpoint_file):
    """Return (private sampler reference, checkpoint-file hash), without printing.

    This read-only verifier checks the full operation journal and frozen inputs.
    It does not reserve future funds or depend on remaining training budget.
    """
    try:
        return _verify_completed_checkpoint(Path(root), checkpoint_file)
    except (KeyError, ValueError, TypeError, OSError, ZeroDivisionError, TrainingError):
        raise TrainingError("Arm F checkpoint failed its frozen revision receipt verification.") from None


def _verify_completed_checkpoint(root, checkpoint_file):
    protocol, protocol_hash = load_training_protocol(root)
    freeze_hash = verify_evaluation_freeze(root)
    path = raw.private_path(root, checkpoint_file)
    if path != raw.private_path(root, RUN_DIRECTORY + "/checkpoints.json"):
        raise TrainingError("Use the completed revision checkpoints.json file.")
    files = {name: raw.private_path(root, path.parent / name).read_bytes()
             for name in ("checkpoints.json", "plan.json", "summary.json", "events.jsonl")}
    checkpoints, plan, summary = (json.loads(files[name]) for name in
                                  ("checkpoints.json", "plan.json", "summary.json"))
    checkpoint_hash = raw.digest(files["checkpoints.json"])
    run_id = plan.get("run_id")
    if (not isinstance(run_id, str) or not run_id or summary.get("run_id") != run_id
            or summary.get("status") != "complete" or plan.get("schema_version") != 3
            or any(obj.get("phase") != "instruction_revision" or obj.get("arm") != "F"
                   or obj.get("recipe_sha256") != protocol["recipe_sha256"]
                   or obj.get("training_protocol_sha256") != protocol_hash
                   or obj.get("evaluation_freeze_sha256") != freeze_hash
                   or obj.get("source_adapter") != protocol["source_adapter"]
                   or obj.get("optimizer_restored") is not False
                   or obj.get("checkpoint_ttl_seconds") != 30 * 86400 for obj in (plan, summary))
            or plan.get("recipe") != protocol["recipe"]
            or plan.get("software_sha256") != protocol["software_sha256"]
            or plan.get("sequence_order_sha256") != ORDER_SHA256
            or plan.get("parent_arm") != "B" or plan.get("fresh_adapter") is not False
            or plan.get("fresh_training_client") is not True
            or summary.get("checkpoint_reference_sha256") != checkpoint_hash
            or plan.get("planned_nano_usd") != PLANNED_NANO
            or any(plan.get(key) != value for key, value in protocol["counts"].items())
            or any(summary.get(key) != plan[key] for key in
                   ("training_batches", "training_processed_tokens", "training_loss_tokens"))):
        raise TrainingError("Completed revision plan and summary disagree with the frozen recipe.")
    source_config = Config(source_checkpoint_file=plan["source_checkpoint_file"])
    source_config.validate()
    source = v1.source_receipt(source_config, root)[0]
    if source != protocol["source_adapter"]:
        raise TrainingError("The completed revision did not initialize from the exact B parent.")
    for key, marker in (("training_state_path", "/weights/"), ("sampler_path", "/sampler_weights/")):
        value = checkpoints.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"tinker://[A-Za-z0-9._:/-]+", value) or marker not in value:
            raise TrainingError("The completed revision must retain both checkpoint kinds.")
    batches, holdout = verified_rows(root, protocol)
    operations = [(name, (), "", None, 0) for name in ("create", "verify_client", "verify_source", "load_weights")]
    forward_budget = sum(len(row["input_ids"]) for row in holdout) * raw.TOKEN_NANO
    operations.append(("forward", holdout, "baseline_sft_validation", None, forward_budget))
    for index, batch in enumerate(batches, 1):
        operations.extend([("forward_backward", batch, "instruction_training", index,
                            sum(len(row["input_ids"]) for row in batch) * raw.TOKEN_NANO),
                           ("optim", (), "instruction_training", index, 0)])
    operations.extend([("forward", holdout, "end_sft_validation", None, forward_budget),
                       ("state", (), "checkpoint", None, 3 * raw.NANO // 2),
                       ("sampler", (), "checkpoint", None, 3 * raw.NANO // 2)])
    events = [json.loads(line) for line in files["events.jsonl"].splitlines()]
    if (len(events) != 2 * len(operations) + 1
            or {key: value for key, value in events[-1].items() if key != "time_utc"}
            != {"event": "run_complete", "run_id": run_id}):
        raise TrainingError("The revision journal is missing, uncertain, or contains extra operations.")
    losses = []
    for index, (operation, batch, stage, step, budget) in enumerate(operations, 1):
        expected = {"operation_id": index, "operation": operation, "stage": stage,
                    "step": step, "reserved_nano_usd": budget,
                    "processed_tokens": sum(len(row["input_ids"]) for row in batch)}
        reserve, complete = events[2 * index - 2:2 * index]
        if ({key: value for key, value in reserve.items() if key != "time_utc"}
                != {"event": "operation_reserved", **expected}
                or complete.get("event") != "operation_complete"
                or any(complete.get(key) != value for key, value in expected.items())):
            raise TrainingError("The revision journal does not prove every planned operation completed once.")
        metrics = complete.get("metrics")
        if batch:
            _check_metrics(metrics, batch)
            languages = {row["language"] for row in batch}
            if set(metrics.get("by_language", {})) != languages:
                raise TrainingError("Revision language metrics are incomplete.")
            for language in languages:
                _check_metrics(metrics["by_language"][language], [row for row in batch if row["language"] == language])
            if not math.isclose(sum(v["weighted_loss_sum"] for v in metrics["by_language"].values()),
                                metrics["weighted_loss_sum"], rel_tol=1e-10, abs_tol=1e-10):
                raise TrainingError("Revision language losses do not reconcile.")
            if operation == "forward" and summary.get(stage) != metrics:
                raise TrainingError("Saved revision validation metrics differ from their journal.")
            if operation == "forward_backward":
                losses.append(metrics)
        elif metrics is not None:
            raise TrainingError("A non-forward revision operation unexpectedly contains loss metrics.")
    nll = math.fsum(m["weighted_loss_sum"] for m in losses) / sum(m["loss_tokens"] for m in losses)
    if not math.isclose(summary["training_weighted_nll"], nll, rel_tol=1e-10, abs_tol=1e-10):
        raise TrainingError("Revision training diagnostic differs from its journal.")
    v1.reserved_budget(root)  # Validate the shared ledger without reserving again.
    ledger = [json.loads(line) for line in (root / "runs/inkling-training-budget.jsonl").read_bytes().splitlines()]
    reservations = [entry for entry in ledger if entry.get("run_id") == run_id]
    if len(reservations) != 1 or reservations[0]["amount_nano_usd"] != PLANNED_NANO:
        raise TrainingError("The revision has no unique matching shared-budget reservation.")
    return checkpoints["sampler_path"], checkpoint_hash


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--source-checkpoint-file", default=Config().source_checkpoint_file)
    parser.add_argument("--run-dir")
    parser.add_argument("--max-cost-usd", type=float, default=50.0)
    options = vars(parser.parse_args(argv))
    execute = options.pop("execute")
    try:
        result = run(Config(**options), execute=execute)
        print(json.dumps({key: value for key, value in result.items() if key != "run_id"},
                         ensure_ascii=False, indent=2, allow_nan=False))
    except BaseException:
        print("Revision planning or training could not complete; no automatic retry was attempted. Inspect the private receipt if execution began.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
