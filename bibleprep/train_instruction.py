"""Plan matched Inkling instruction-training arms; no paid calls without --execute.

C starts a fresh adapter. D loads only the completed original-text adapter's
weights into a fresh client, so both arms start instruction training with a new
optimizer. Evaluation questions and scoring criteria are not training inputs.
"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import uuid

from bibleprep import train_inkling as raw

ROOT = raw.ROOT
MANIFEST = "manifests/preparation-instruction-v1.json"
PAIR_CAP_NANO = 15 * raw.NANO
RAW_RECIPE_SHA256 = "7efef6738f803b48a8759e707ccd2a1e11879975223c422ca7fe05c8683286e7"
TrainingError = raw.TrainingError


@dataclass(frozen=True)
class Config:
    arm: str = "C"
    manifest: str = MANIFEST
    source_checkpoint_file: str = "runs/inkling-original-text-v1/checkpoints.json"
    batch_size: int = 16
    seed: int = 20260906
    learning_rate: float = 1e-4
    checkpoint_ttl_seconds: int = 30 * 86400
    checkpoint_reserve_usd: float = 3.0
    max_cost_usd: float = 50.0
    max_pair_cost_usd: float = 15.0
    timeout_seconds: float = 600.0
    run_dir: str | None = None

    def validate(self):
        if self.arm not in {"C", "D"}:
            raise TrainingError("Instruction arm must be C or D.")
        if (self.batch_size != 16 or self.seed != 20260906 or self.learning_rate != 1e-4):
            raise TrainingError("The matched instruction recipe fixes batch 16, seed 20260906, and LR 0.0001.")
        raw.Config(batch_size=self.batch_size, seed=self.seed, learning_rate=self.learning_rate,
                   checkpoint_ttl_seconds=self.checkpoint_ttl_seconds,
                   checkpoint_reserve_usd=self.checkpoint_reserve_usd,
                   max_cost_usd=self.max_cost_usd, timeout_seconds=self.timeout_seconds).validate()
        if not 0 < raw.dollars(self.max_pair_cost_usd) <= PAIR_CAP_NANO:
            raise TrainingError("The paired instruction estimate cannot exceed $15.")


def project_file(root, value, *, prefix=None):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise TrainingError("Preparation paths must be portable project-relative paths.")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise TrainingError("Preparation artifact escapes the project.")
    if prefix and not resolved.is_relative_to((root / prefix).resolve()):
        raise TrainingError("Preparation artifact is outside its expected directory.")
    return resolved


def checked_file(root, entry, *, prefix=None):
    path = project_file(root, entry["path"], prefix=prefix)
    contents = path.read_bytes()
    if raw.digest(contents) != entry["sha256"]:
        raise TrainingError("Frozen instruction artifact checksum mismatch.")
    return contents


def read_rows(root, entry, manifest):
    data = checked_file(root, entry, prefix="data/prepared/instruction-v1")
    rows = [json.loads(line) for line in data.splitlines()]
    ids = set()
    for row in rows:
        inp, target, weights = (row[k] for k in ("input_ids", "target_ids", "weights"))
        if not inp or len(inp) != len(target) or len(inp) != len(weights):
            raise TrainingError("Instruction arrays must be nonempty and aligned.")
        if any(type(t) is not int or not 0 <= t < 200058 for t in inp + target):
            raise TrainingError("Invalid native instruction token ID.")
        if inp[1:] != target[:-1]:
            raise TrainingError("Instruction inputs and targets must be shifted exactly once.")
        if (inp[0] != manifest["native_start_token_id"]
                or target[-1] != manifest["native_end_token_id"]):
            raise TrainingError("Native message or model-turn boundary differs from preparation.")
        prompt_count = row["prompt_token_count"]
        if type(prompt_count) is not int or not 1 < prompt_count <= len(inp):
            raise TrainingError("Instruction prompt boundary is invalid.")
        if (any(type(w) not in (int, float) or w not in (0, 1) for w in weights)
                or weights != [0] * (prompt_count - 1) + [1] * (len(inp) - prompt_count + 1)):
            raise TrainingError("Only the full native assistant turn may contribute instruction loss.")
        if (row["processed_token_count"] != len(inp)
                or row["loss_token_count"] != sum(weights)
                or len(inp) > manifest["maximum_input_tokens"]):
            raise TrainingError("Instruction counts or maximum length disagree.")
        if (not isinstance(row.get("id"), str) or row["id"] in ids
                or not isinstance(row.get("chapter_keys"), list) or not row["chapter_keys"]
                or any(not isinstance(key, str) or not key for key in row["chapter_keys"])):
            raise TrainingError("Instruction IDs and chapter families must be explicit and unique.")
        ids.add(row["id"])
    if (len(rows) != entry["sequences"]
            or sum(len(r["input_ids"]) for r in rows) != entry["processed_tokens"]
            or sum(sum(r["weights"]) for r in rows) != entry["loss_tokens"]):
        raise TrainingError("Instruction artifact totals disagree with the frozen manifest.")
    return rows


def source_receipt(config, root):
    """Return fingerprints and a private reference, never print checkpoint values."""
    path = raw.private_path(root, config.source_checkpoint_file)
    if path.name != "checkpoints.json":
        raise TrainingError("D requires the original run's private checkpoints.json file.")
    files = {name: (path.parent / name).read_bytes()
             for name in ("plan.json", "summary.json", "checkpoints.json", "events.jsonl")}
    plan, summary, checkpoints = (json.loads(files[name])
                                  for name in ("plan.json", "summary.json", "checkpoints.json"))
    recipe = plan["recipe"]
    if (summary.get("status") != "complete" or summary.get("phase") != "full"
            or plan.get("phase") != "full" or plan.get("fresh_adapter") is not True
            or plan.get("run_id") != summary.get("run_id")
            or summary.get("recipe_sha256") != RAW_RECIPE_SHA256
            or plan.get("recipe_sha256") != RAW_RECIPE_SHA256
            or raw.digest(raw.encoded(recipe)) != RAW_RECIPE_SHA256
            or recipe.get("model") != raw.MODEL or recipe.get("rank") != 8
            or any(recipe.get(k) is not True for k in ("train_mlp", "train_attn", "train_unembed"))
            or summary.get("training_batches") != 136
            or summary.get("training_processed_tokens") != 3280433
            or summary.get("training_loss_tokens") != 3229825):
        raise TrainingError("D requires the completed, matching original-text development adapter.")
    if recipe.get("manifest_sha256") != raw.digest((root / raw.MANIFEST).read_bytes()):
        raise TrainingError("Original-text preparation identity differs from the completed receipt.")
    events = [json.loads(line) for line in files["events.jsonl"].splitlines()]
    if not events or events[-1].get("event") != "run_complete":
        raise TrainingError("Original-text journal does not certify completion.")
    checkpoint = checkpoints.get("training_state_path")
    if (not isinstance(checkpoint, str) or not checkpoint.startswith("tinker://")
            or "/weights/" not in checkpoint or any(ch.isspace() for ch in checkpoint)
            or not isinstance(checkpoints.get("sampler_path"), str)
            or not checkpoints["sampler_path"].startswith("tinker://")):
        raise TrainingError("Original-text training and sampler checkpoints must both be retained.")
    return {"raw_recipe_sha256": RAW_RECIPE_SHA256,
            "receipt_sha256": {name: raw.digest(data) for name, data in files.items()},
            "load_method": "load_state", "restore_optimizer": False}, checkpoint


def reserved_budget(root):
    path = root / "runs/inkling-training-budget.jsonl"
    entries = [json.loads(line) for line in path.read_bytes().splitlines()] if path.exists() else []
    if any(e.get("event") != "run_budget_reserved" or type(e.get("amount_nano_usd")) is not int
           or e["amount_nano_usd"] < 0 for e in entries):
        raise TrainingError("The existing shared training ledger needs manual inspection.")
    return sum(e["amount_nano_usd"] for e in entries)


def make_plan(config, root=ROOT):
    config.validate()
    manifest_bytes = project_file(root, config.manifest, prefix="manifests").read_bytes()
    manifest = json.loads(manifest_bytes)
    if (manifest.get("schema_version") != 1 or manifest.get("status") != "prepared_not_trained"
            or manifest.get("objective") != "reviewed_english_instruction_sft"
            or manifest.get("review_status") != "ai_source_checked"
            or manifest.get("expert_certified") is not False
            or manifest.get("model") != raw.MODEL
            or manifest.get("thinking_effort_numeric") != 0.7
            or manifest.get("native_start_token_id") != 200002
            or manifest.get("native_end_token_id") != 200006
            or manifest.get("maximum_input_tokens") != 8192):
        raise TrainingError("Instruction preparation is not a reviewed, matching native snapshot.")
    code = manifest.get("preparation_code_sha256", {})
    if not code or "bibleprep/prepare_instruction.py" not in code:
        raise TrainingError("Frozen instruction preparation code is required.")
    for name, expected in code.items():
        if raw.digest(project_file(root, name).read_bytes()) != expected:
            raise TrainingError("Instruction preparation code differs from its frozen snapshot.")
    versions = manifest.get("runtime_versions", {})
    if not versions or importlib.metadata.version("tinker") != raw.SDK_VERSION:
        raise TrainingError("Instruction training requires the pinned native runtime.")
    if any(importlib.metadata.version(name) != expected for name, expected in versions.items()):
        raise TrainingError("Instruction renderer runtime differs from preparation.")
    try:
        from bibleprep.prepare_instruction import verify_prepared
        verify_prepared(root, manifest)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise TrainingError("Instruction source review, freeze, or exclusion verification failed.") from None
    reviewed = manifest["reviewed_dataset"]
    checked_file(root, reviewed)
    if not 100 <= reviewed["examples"] <= 300:
        raise TrainingError("This comparison requires 100–300 separately reviewed examples.")
    exclusion_entry = manifest["evaluation_exclusion"]
    exclusion = json.loads(checked_file(root, exclusion_entry))
    if (exclusion_entry.get("overlap_count") != 0
            or manifest.get("split", {}).get("chapter_disjoint") is not True):
        raise TrainingError("Instruction and evaluation chapter exclusions must be disjoint.")
    train = read_rows(root, manifest["artifacts"]["train"], manifest)
    holdout = read_rows(root, manifest["artifacts"]["validation"], manifest)
    if not train or len(train) + len(holdout) != reviewed["examples"]:
        raise TrainingError("All reviewed examples must occur exactly once in the SFT split.")
    chapters = lambda rows: {key for row in rows for key in row["chapter_keys"]}
    if (chapters(train) & chapters(holdout)
            or {r["id"] for r in train} & {r["id"] for r in holdout}):
        raise TrainingError("Instruction training and validation overlap.")
    forbidden = set(exclusion["chapter_keys"])
    if not forbidden or (chapters(train) | chapters(holdout)) & forbidden:
        raise TrainingError("Instruction examples overlap the frozen evaluation chapter exclusion.")
    selected = sorted(train, key=lambda row: row["id"])
    random.Random(config.seed).shuffle(selected)
    batches = [selected[i:i + config.batch_size] for i in range(0, len(selected), config.batch_size)]
    source = source_receipt(config, root)[0] if config.arm == "D" else None
    recipe = {"model": raw.MODEL, "manifest_sha256": raw.digest(manifest_bytes), "rank": 8,
              "train_mlp": True, "train_attn": True, "train_unembed": True,
              "seed": config.seed, "batch_size": config.batch_size, "epochs": 1,
              "loss_fn": "cross_entropy", "optimization_loss_reduction": "sum",
              "thinking_effort_numeric": 0.7, "optimizer_initialization": "fresh",
              "adam": {"learning_rate": config.learning_rate, "beta1": 0.9, "beta2": 0.95,
                       "eps": 1e-8, "weight_decay": 0.0, "grad_clip_norm": 0.0},
              "validation_ids": [row["id"] for row in holdout]}
    training_tokens = sum(len(row["input_ids"]) for row in selected)
    forward_tokens = 2 * sum(len(row["input_ids"]) for row in holdout)
    checkpoint_nano = raw.dollars(config.checkpoint_reserve_usd)
    planned = (training_tokens + forward_tokens) * raw.TOKEN_NANO + checkpoint_nano
    if 2 * planned > raw.dollars(config.max_pair_cost_usd):
        raise TrainingError("Both matched instruction arms together exceed the $15 incremental estimate.")
    existing = reserved_budget(root)
    if existing + planned > raw.dollars(config.max_cost_usd):
        raise TrainingError("The proposed arm exceeds the existing shared $50 training ledger.")
    software = ("bibleprep/train_instruction.py", "bibleprep/train_inkling.py",
                "bibleprep/environment.py", "requirements-training.txt", "requirements-comparison-large.lock.txt")
    plan = {"schema_version": 1, "phase": "instruction", "arm": config.arm, "recipe": recipe,
            "recipe_sha256": raw.digest(raw.encoded(recipe)), "source_adapter": source,
            "software_sha256": {name: raw.digest((root / name).read_bytes()) for name in software},
            "sdk_version": raw.SDK_VERSION, "epochs": 1,
            "fresh_training_client": True, "fresh_adapter": config.arm == "C",
            "optimizer_restored": False, "checkpoint_ttl_seconds": config.checkpoint_ttl_seconds,
            "training_sequences": len(selected), "training_batches": len(batches),
            "training_processed_tokens": training_tokens,
            "training_loss_tokens": sum(sum(row["weights"]) for row in selected),
            "holdout_sequences": len(holdout), "two_holdout_forward_tokens": forward_tokens,
            "sequence_order_sha256": raw.digest(raw.encoded([row["id"] for row in selected])),
            "compute_rate_usd_per_million": 5.61,
            "compute_reserve_nano_usd": (training_tokens + forward_tokens) * raw.TOKEN_NANO,
            "checkpoint_reserve_nano_usd": checkpoint_nano,
            "planned_nano_usd": planned, "planned_estimated_usd": raw.money(planned),
            "pair_planned_estimated_usd": raw.money(2 * planned),
            "existing_training_reserved_estimated_usd": raw.money(existing),
            "learning_rate_status": "generic_recipe_not_Inkling_calibrated",
            "loss_interpretation": "assistant_target_prediction_not_translation_accuracy",
            "base_revision": "provider_revision_unpinned",
            "cost_status": "conservative_estimate_not_invoice_or_guaranteed_provider_cap"}
    return plan, batches, holdout


class InstructionNativeSession(raw.NativeSession):
    """Use the established SDK transport, with an explicit weights-only branch."""
    def __init__(self):
        super().__init__()
        self.ready = False
        self.source_verified = False
        self.used = False

    def call(self, operation, rows, settings):
        if operation == "create":
            result = super().call(operation, rows, settings)
            self.ready = settings["arm"] == "C"
            return result
        if self.client is None:
            raise TrainingError("Instruction training client has not been created.")
        if operation == "verify_client":
            info = self.client.get_info()
            names = [name for name in (info.model_name, info.model_data.model_name) if name is not None]
            if not names or any(name != raw.MODEL for name in names) or info.is_lora is not True or info.lora_rank != 8:
                raise TrainingError("Provider client configuration differs from the frozen Inkling recipe.")
            return {}
        if operation == "verify_source":
            if settings["arm"] != "D" or self.used or self.ready:
                raise TrainingError("Source weights may only be inspected before D instruction training.")
            rest = self.service.create_rest_client()
            info = rest.get_weights_info_by_tinker_path(settings["source_checkpoint"]).result(timeout=settings["timeout_seconds"])
            if (info.base_model != raw.MODEL or info.is_lora is not True or info.lora_rank != 8
                    or any(getattr(info, key) is not True for key in ("train_mlp", "train_attn", "train_unembed"))):
                raise TrainingError("Provider checkpoint configuration differs from the original adapter receipt.")
            self.source_verified = True
            return {}
        if operation == "load_weights":
            if settings["arm"] != "D" or not self.source_verified or self.used or self.ready:
                raise TrainingError("Original-text weights must load once, before any instruction operation.")
            # Pinned SDK 0.27.1 sends optimizer=False. Never restore old moments.
            self.client.load_state(settings["source_checkpoint"]).result(timeout=settings["timeout_seconds"])
            self.ready = True
            return {}
        if not self.ready:
            raise TrainingError("D requires verified original-text weights before instruction operations.")
        self.used = True
        return super().call(operation, rows, settings)


def instruction_worker(connection):
    os.environ["TINKER_TELEMETRY"] = "0"
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        session = InstructionNativeSession()
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
    plan, batches, holdout = make_plan(config, root)
    if not execute:
        return {"status": "dry_run", **plan}
    source_checkpoint = None
    if config.arm == "D":
        source, source_checkpoint = source_receipt(config, root)
        if source != plan["source_adapter"]:
            raise TrainingError("The original-text receipt changed after planning.")
    slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    directory = raw.private_path(root, config.run_dir or "runs/inkling-instruction-" + config.arm.lower() + "-" + slug)
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
            native = raw.BoundedTrainingTransport(worker=instruction_worker)
        invoke("create")
        invoke("verify_client")
        if config.arm == "D":
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
            settings["checkpoint_name"] = "instruction-" + config.arm.lower() + "-" + operation
            result, _ = invoke(operation, budget=plan["checkpoint_reserve_nano_usd"] // 2, stage="checkpoint")
            checkpoints[key] = result["path"]
            raw.write_private(directory / "checkpoints.json", checkpoints)
        summary = {"status": "complete", "phase": "instruction", "arm": config.arm, "run_id": run_id,
                   "recipe_sha256": plan["recipe_sha256"], "optimizer_restored": False,
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
        raw.write_private(directory / "summary.json", {"status": "stopped_uncertain", "phase": "instruction", "arm": config.arm,
                          "run_id": run_id, "recipe_sha256": plan["recipe_sha256"], "accounting_is_invoice": False})
        raise TrainingError("Instruction training stopped; reserved costs remain against the shared cap. Inspect private run status.") from None
    finally:
        if native is not None:
            native.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--arm", choices=("C", "D"), default="C")
    parser.add_argument("--manifest", default=MANIFEST)
    parser.add_argument("--source-checkpoint-file", default=Config().source_checkpoint_file)
    parser.add_argument("--run-dir")
    parser.add_argument("--max-cost-usd", type=float, default=50.0)
    parser.add_argument("--max-pair-cost-usd", type=float, default=15.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    options = vars(parser.parse_args(argv))
    execute = options.pop("execute")
    try:
        print(json.dumps(run(Config(**options), execute=execute), ensure_ascii=False, indent=2, allow_nan=False))
    except TrainingError as exc:
        print(str(exc))
        return 1
    except BaseException:
        print("Instruction preparation or training could not complete; no automatic retry was attempted.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
