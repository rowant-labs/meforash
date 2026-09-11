"""Offline planning and bounded execution for Candidate G.

The runner starts a fresh optimizer/client from the retained B weights, performs
six fixed updates, and records three before/after validation diagnostics.  Dry
run and protocol construction never load credentials or call a provider.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import re
import uuid

from bibleprep import candidate_g_dataset as dataset
from bibleprep import prepare_instruction as instruction
from bibleprep import train_instruction as v1
from bibleprep import train_inkling as raw


ROOT = raw.ROOT
TRAINING_PROTOCOL = "runs/candidate-g-execution-v1/training-protocol.json"
EVALUATION_PROTOCOL = "runs/candidate-g-execution-v1/evaluation/protocol.json"
RUN_DIRECTORY = "runs/candidate-g-execution-v1/training"
SOURCE_CHECKPOINT_FILE = "runs/inkling-original-text-v1/checkpoints.json"
RAW_PLAN = "runs/inkling-original-text-v1/plan.json"
RAW_MANIFEST = "manifests/preparation-inkling-v1.json"
LEGACY_MANIFEST = "manifests/preparation-instruction-v3.json"
PREFLIGHT = "runs/candidate-g-execution-v1/preflight/preflight-metadata.json"
PRICE_SNAPSHOT = "runs/candidate-g-execution-v1/preflight/official-models.json"
MODEL = "thinkingmachines/Inkling"
SEQUENCE_CAP_NANO = 20 * raw.NANO
SAMPLE_RESERVE_NANO = 3_219_456_000
HOSTING_PROBE_NANO = 100_000_000
TRAIN_RATE = 5.61
TrainingError = raw.TrainingError


@dataclass(frozen=True)
class Config:
    source_checkpoint_file: str = SOURCE_CHECKPOINT_FILE
    training_protocol: str = TRAINING_PROTOCOL
    evaluation_protocol: str = EVALUATION_PROTOCOL
    run_dir: str = RUN_DIRECTORY
    batch_size: int = 16
    seed: int = 20260909
    learning_rate: float = 2e-5
    checkpoint_ttl_seconds: int = 30 * 86400
    timeout_seconds: float = 600.0
    sequence_cap_usd: float = 20.0

    def validate(self):
        if (self.source_checkpoint_file != SOURCE_CHECKPOINT_FILE
                or self.training_protocol != TRAINING_PROTOCOL
                or self.evaluation_protocol != EVALUATION_PROTOCOL
                or self.run_dir != RUN_DIRECTORY or self.batch_size != 16
                or self.seed != 20260909 or self.learning_rate != 2e-5
                or self.checkpoint_ttl_seconds != 30 * 86400
                or self.timeout_seconds != 600.0
                or raw.dollars(self.sequence_cap_usd) != SEQUENCE_CAP_NANO):
            raise TrainingError("Candidate G fixes B, batch 16, six updates, seed, LR, deadlines, retention and the $20 sequence cap.")


def _project_file(root, value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise TrainingError("Frozen paths must be portable and project-relative.")
    unresolved = Path(root) / path
    result = unresolved.resolve()
    if not result.is_relative_to(Path(root).resolve()) or unresolved.is_symlink():
        raise TrainingError("Frozen path escapes the project or is a symlink.")
    return result


def _entry(root, entry):
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
        raise TrainingError("Frozen file entry fields differ.")
    path = _project_file(root, entry["path"])
    data = path.read_bytes()
    if raw.digest(data) != entry["sha256"]:
        raise TrainingError("Frozen file checksum differs.")
    return path, data


def _file_entry(root, path):
    target = _project_file(root, path)
    return {"path": Path(path).as_posix(), "sha256": raw.digest(target.read_bytes())}


def _preflight(root, *, require_fresh=True):
    entry = _file_entry(root, PREFLIGHT)
    metadata = json.loads(_entry(root, entry)[1])
    price_entry = _file_entry(root, PRICE_SNAPSHOT)
    try:
        observed = datetime.fromisoformat(metadata["observed_at_utc"])
        age = datetime.now(timezone.utc) - observed
    except (KeyError, TypeError, ValueError):
        raise TrainingError("Candidate G preflight timestamp is invalid.") from None
    checkpoints = metadata.get("checkpoints", [])
    if (metadata.get("status") != "passed" or metadata.get("same_training_run") is not True
            or metadata.get("operations", {}).get("training_calls") != 0
            or len(checkpoints) != 2
            or {x.get("role") for x in checkpoints} != {"sampler", "training_state"}
            or any(x.get("available") is not True or x.get("unexpired") is not True
                   for x in checkpoints)
            or metadata.get("price") != {
                "cached_input_discount_assumed": False, "context": "64K",
                "input_usd_per_million": "1.87", "model": MODEL,
                "official_url": "https://tinker-docs.thinkingmachines.ai/tinker/models.json",
                "output_usd_per_million": "4.68", "snapshot_path": PRICE_SNAPSHOT,
                "snapshot_sha256": price_entry["sha256"],
                "temporary_discount_note": "Limited-time 50% discount",
                "training_usd_per_million": "5.61",
            }):
        raise TrainingError("Read-only preflight, B checkpoint availability, or official price facts differ.")
    if require_fresh and (age.total_seconds() < 0 or age.total_seconds() >= 24 * 3600):
        raise TrainingError("Candidate G requires a provider preflight observed within 24 hours.")
    if require_fresh:
        try:
            expiries = [datetime.fromisoformat(item["expires_at_utc"]) for item in checkpoints]
        except (KeyError, TypeError, ValueError):
            raise TrainingError("Candidate G checkpoint expiry metadata is invalid.") from None
        if any(expiry <= datetime.now(timezone.utc) for expiry in expiries):
            raise TrainingError("Candidate G requires both B checkpoints to remain unexpired at execution.")
    return {"metadata": entry, "price_snapshot": price_entry,
            "observed_at_utc": metadata["observed_at_utc"],
            "freshness_limit_hours": 24, "checkpoints_available_and_unexpired": True}


def _prepared_rows(root, entry, expected_count):
    path = _project_file(root, entry["path"])
    data = path.read_bytes()
    if raw.digest(data) != entry["sha256"]:
        raise TrainingError("Candidate G prepared bytes differ from the manifest.")
    rows = [json.loads(line) for line in data.splitlines()]
    if len(rows) != expected_count or entry["rows"] != expected_count:
        raise TrainingError("Candidate G prepared split count differs.")
    ids = set()
    for row in rows:
        if set(row) != dataset.PREPARED_FIELDS or row["id"] in ids:
            raise TrainingError("Candidate G prepared schema or row IDs differ.")
        instruction.validate_sequence(row, dataset.MAXIMUM_INPUT_TOKENS)
        ids.add(row["id"])
    if (entry["processed_tokens"] != sum(len(x["input_ids"]) for x in rows)
            or entry["loss_tokens"] != sum(sum(x["weights"]) for x in rows)):
        raise TrainingError("Candidate G prepared token totals differ.")
    return rows


def _load_preparation(root, preparation_manifest_path):
    manifest_entry = _file_entry(root, preparation_manifest_path)
    manifest = json.loads(_entry(root, manifest_entry)[1])
    required = {"schema_version", "artifact_kind", "status", "model", "artifacts",
                "settings", "tokenizer", "input_files", "compiler_summary", "counts",
                "created_at_utc", "expert_certified", "model_calls", "training_calls"}
    if (set(manifest) != required or manifest["schema_version"] != 1
            or manifest["artifact_kind"] != "candidate_g_prepared_dataset_manifest_v1"
            or manifest["status"] != "prepared_offline_not_trained"
            or manifest["model"] != MODEL
            or manifest["expert_certified"] is not False
            or manifest["model_calls"] != 0 or manifest["training_calls"] != 0
            or set(manifest["artifacts"]) != {"train", "validation"}):
        raise TrainingError("Final Candidate G preparation manifest differs from the runner contract.")
    _, summary_bytes = _entry(root, manifest["compiler_summary"])
    summary = json.loads(summary_bytes)
    if (summary.get("artifact_kind") != "candidate_g_prepared_dataset_summary_v1"
            or summary.get("status") != "prepared_offline_not_trained"
            or summary.get("counts") != {"train": 96, "validation": 24, "new": 104, "rehearsal": 16}
            or summary.get("settings", {}).get("thinking_effort_numeric") != 0.7
            or summary.get("settings", {}).get("maximum_input_tokens") != 8192
            or summary.get("settings", {}).get("truncation") != "forbidden"
            or summary.get("settings", {}).get("reasoning_targets") is not False
            or summary.get("settings", {}).get("rejected_guidance_suffix_adopted") is not False
            or summary.get("expert_certified") is not False
            or summary.get("training_authorized") is not False
            or manifest["settings"] != summary.get("settings")
            or manifest["counts"] != summary.get("counts")):
        raise TrainingError("Candidate G prepared summary framing or review status differs.")
    if (not isinstance(manifest["tokenizer"], dict) or not manifest["tokenizer"]
            or not isinstance(manifest["input_files"], list) or not manifest["input_files"]):
        raise TrainingError("Preparation must bind tokenizer identity and every reviewed input file.")
    for frozen in manifest["input_files"]:
        _entry(root, frozen)
    for split, count in (("train", 96), ("validation", 24)):
        artifact = manifest["artifacts"][split]
        required_artifact = {"path", "sha256", "rows", "processed_tokens", "loss_tokens",
                             "maximum_input_tokens", "language_rows"}
        if set(artifact) != required_artifact or artifact["maximum_input_tokens"] > 8192:
            raise TrainingError("Prepared artifact fields differ.")
        rows = _prepared_rows(root, artifact, count)
        summary_artifact = summary["artifacts"][split]
        path = _project_file(root, artifact["path"])
        if (summary_artifact.get("sha256") != artifact["sha256"]
                or summary_artifact.get("rows") != artifact["rows"]
                or summary_artifact.get("bytes") != len(path.read_bytes())
                or set(summary_artifact) != {"sha256", "rows", "bytes"}):
            raise TrainingError("Prepared summary and manifest artifact bindings differ.")
    return manifest_entry, manifest


def _retention_rows(root):
    raw_plan_entry = _file_entry(root, RAW_PLAN)
    raw_plan = json.loads(_entry(root, raw_plan_entry)[1])
    raw_ids = raw_plan.get("recipe", {}).get("holdout_ids")
    if not isinstance(raw_ids, list) or len(raw_ids) != 12 or len(set(raw_ids)) != 12:
        raise TrainingError("The completed B raw holdout IDs differ.")
    raw_manifest_entry = _file_entry(root, RAW_MANIFEST)
    raw_manifest = json.loads(_entry(root, raw_manifest_entry)[1])
    raw_validation_entry = copy.deepcopy(raw_manifest["artifacts"]["validation"])
    raw_validation = raw.read_rows(root, raw_validation_entry, "validation", raw_manifest)
    by_id = {row["id"]: row for row in raw_validation}
    if not set(raw_ids) <= set(by_id):
        raise TrainingError("A retained B raw holdout is absent from the frozen validation split.")
    raw_selected = [by_id[row_id] for row_id in raw_ids]

    legacy_manifest_entry = _file_entry(root, LEGACY_MANIFEST)
    legacy_manifest = json.loads(_entry(root, legacy_manifest_entry)[1])
    legacy_entry = copy.deepcopy(legacy_manifest["artifacts"]["validation"])
    legacy_path = _project_file(root, legacy_entry["path"])
    legacy_data = legacy_path.read_bytes()
    if raw.digest(legacy_data) != legacy_entry["sha256"]:
        raise TrainingError("Legacy v3 English validation bytes changed.")
    legacy_rows = [json.loads(line) for line in legacy_data.splitlines()]
    for row in legacy_rows:
        if set(row) != dataset.PREPARED_FIELDS:
            raise TrainingError("Legacy v3 English validation schema changed.")
        instruction.validate_sequence(row, legacy_manifest["maximum_input_tokens"])
    if (len(legacy_rows) != legacy_entry["sequences"]
            or sum(len(row["input_ids"]) for row in legacy_rows) != legacy_entry["processed_tokens"]
            or sum(sum(row["weights"]) for row in legacy_rows) != legacy_entry["loss_tokens"]):
        raise TrainingError("Legacy v3 English validation totals changed.")
    if len(legacy_rows) != 16 or len({row["id"] for row in legacy_rows}) != 16:
        raise TrainingError("Legacy English validation must retain all exact sixteen rows.")
    return {
        "raw": raw_selected, "legacy": legacy_rows,
        "bindings": {
            "raw_plan": raw_plan_entry, "raw_preparation_manifest": raw_manifest_entry,
            "raw_validation": {"path": raw_validation_entry["path"],
                               "sha256": raw_validation_entry["sha256"]},
            "raw_holdout_ids": raw_ids,
            "legacy_preparation_manifest": legacy_manifest_entry,
            "legacy_validation": {"path": legacy_entry["path"], "sha256": legacy_entry["sha256"]},
            "legacy_validation_ids": [row["id"] for row in legacy_rows],
        },
    }


def build_training_protocol(root=ROOT, preparation_manifest_path="runs/candidate-g-execution-v1/prepared/manifest.json"):
    """Derive exact recipe, file identities and full-sequence reservation offline."""
    root = Path(root).resolve()
    preparation_entry, preparation = _load_preparation(root, preparation_manifest_path)
    train = _prepared_rows(root, preparation["artifacts"]["train"], 96)
    validation = _prepared_rows(root, preparation["artifacts"]["validation"], 24)
    retention = _retention_rows(root)
    selected = sorted(train, key=lambda row: row["id"])
    random.Random(20260909).shuffle(selected)
    batches = [selected[i:i + 16] for i in range(0, len(selected), 16)]
    if len(batches) != 6 or any(len(batch) != 16 for batch in batches):
        raise TrainingError("Candidate G requires exactly six full batches.")
    config = Config()
    source_adapter, _ = v1.source_receipt(config, root)
    recipe = {
        "model": MODEL, "rank": 8, "train_mlp": True, "train_attn": True,
        "train_unembed": True, "parent_arm": "B", "load_method": "load_state",
        "optimizer_initialization": "fresh", "optimizer_restored": False,
        "batch_size": 16, "steps": 6, "epochs": 1, "seed": 20260909,
        "loss_fn": "cross_entropy", "optimization_loss_reduction": "sum",
        "thinking_effort_numeric": 0.7,
        "adam": {"learning_rate": 2e-5, "beta1": 0.9, "beta2": 0.95,
                 "eps": 1e-8, "weight_decay": 0.0, "grad_clip_norm": 0.0},
        "validation_ids": [row["id"] for row in validation],
    }
    counts = {
        "training_sequences": 96, "training_batches": 6,
        "training_processed_tokens": sum(len(row["input_ids"]) for row in selected),
        "training_loss_tokens": int(sum(sum(row["weights"]) for row in selected)),
        "candidate_g_validation_sequences": 24,
        "candidate_g_two_forward_tokens": 2 * sum(len(row["input_ids"]) for row in validation),
        "raw_retention_sequences": 12,
        "raw_two_forward_tokens": 2 * sum(len(row["input_ids"]) for row in retention["raw"]),
        "legacy_english_retention_sequences": 16,
        "legacy_english_two_forward_tokens": 2 * sum(len(row["input_ids"]) for row in retention["legacy"]),
    }
    training_nano = counts["training_processed_tokens"] * raw.TOKEN_NANO
    g_forward_nano = counts["candidate_g_two_forward_tokens"] * raw.TOKEN_NANO
    raw_forward_nano = counts["raw_two_forward_tokens"] * raw.TOKEN_NANO
    legacy_forward_nano = counts["legacy_english_two_forward_tokens"] * raw.TOKEN_NANO
    breakdown = {
        "training": training_nano,
        "candidate_g_validation_before_after": g_forward_nano,
        "raw_12_retention_before_after": raw_forward_nano,
        "legacy_english_16_retention_before_after": legacy_forward_nano,
        "checkpoint_and_storage": 3 * raw.NANO,
        "fresh_b_g_sampling": SAMPLE_RESERVE_NANO,
        "hosting_probe": HOSTING_PROBE_NANO,
    }
    total = sum(breakdown.values())
    if total > SEQUENCE_CAP_NANO:
        raise TrainingError("Candidate G full-sequence reservation exceeds $20.")
    software_names = (
        "bibleprep/train_candidate_g.py", "bibleprep/candidate_g_dataset.py",
        "bibleprep/train_instruction.py", "bibleprep/train_inkling.py",
        "bibleprep/environment.py", "requirements-training.txt",
        "requirements-comparison-large.lock.txt",
    )
    software = {name: raw.digest(_project_file(root, name).read_bytes())
                for name in software_names}
    # Freshness and present checkpoint expiry are execution gates.  The frozen
    # receipt must remain verifiable after the observation window has elapsed.
    preflight = _preflight(root, require_fresh=False)
    immutable_candidates = [
        preparation_entry,
        preparation["compiler_summary"], *preparation["input_files"],
        {"path": preparation["artifacts"]["train"]["path"],
         "sha256": preparation["artifacts"]["train"]["sha256"]},
        {"path": preparation["artifacts"]["validation"]["path"],
         "sha256": preparation["artifacts"]["validation"]["sha256"]},
        preflight["metadata"], preflight["price_snapshot"],
        retention["bindings"]["raw_plan"], retention["bindings"]["raw_preparation_manifest"],
        retention["bindings"]["raw_validation"],
        retention["bindings"]["legacy_preparation_manifest"],
        retention["bindings"]["legacy_validation"],
        _file_entry(root, SOURCE_CHECKPOINT_FILE),
        *({"path": name, "sha256": value} for name, value in software.items()),
    ]
    by_path = {}
    for item in immutable_candidates:
        if item["path"] in by_path and by_path[item["path"]] != item:
            raise TrainingError("Candidate G immutable path has conflicting hashes.")
        by_path[item["path"]] = item
    immutable = [by_path[name] for name in sorted(by_path)]
    return {
        "schema_version": 1, "artifact_kind": "candidate_g_training_protocol_v1",
        "status": "frozen_before_evaluation_authoring",
        "experiment_id": "candidate-g-execution-v1", "arm": "G", "parent_arm": "B",
        "preparation": {"manifest": preparation_entry,
                        "train": copy.deepcopy(preparation["artifacts"]["train"]),
                        "validation": copy.deepcopy(preparation["artifacts"]["validation"])},
        "recipe": recipe, "recipe_sha256": raw.digest(raw.encoded(recipe)),
        "counts": counts,
        "sequence_order_sha256": raw.digest(raw.encoded([row["id"] for row in selected])),
        "source_adapter": source_adapter, "source_checkpoint_file": SOURCE_CHECKPOINT_FILE,
        "retention": retention["bindings"], "software_sha256": software,
        "runtime_versions": {"tinker": raw.SDK_VERSION,
                             "tml-renderers": importlib.metadata.version("tml-renderers")},
        "preflight": preflight,
        "pricing": {"training_usd_per_million": TRAIN_RATE,
                    "input_usd_per_million": 1.87, "output_usd_per_million": 4.68,
                    "snapshot": preflight["price_snapshot"], "invoice_reconciled": False},
        "budget": {"sequence_cap_nano_usd": SEQUENCE_CAP_NANO,
                   "breakdown_nano_usd": breakdown, "total_reserved_nano_usd": total,
                   "headroom_nano_usd": SEQUENCE_CAP_NANO - total,
                   "cost_status": "conservative_all_in_reservation_not_invoice"},
        "checkpoint": {"ttl_seconds": 30 * 86400,
                       "retain_training_state": True, "retain_sampler": True},
        "evaluation_protocol_path": EVALUATION_PROTOCOL,
        "immutable_files": immutable,
        "limitations": [
            "Loss and retention forwards are diagnostics, not translation or production-readiness scores.",
            "The raw, legacy English and Candidate G validation rows never receive updates.",
            "Protocol construction is offline and does not authorize or perform provider operations.",
        ],
    }


def load_training_protocol(root=ROOT, path=TRAINING_PROTOCOL):
    root = Path(root).resolve()
    data = _project_file(root, path).read_bytes()
    protocol = json.loads(data)
    manifest_path = protocol.get("preparation", {}).get("manifest", {}).get("path")
    try:
        expected = build_training_protocol(root, manifest_path)
    except (OSError, ValueError, KeyError, TypeError, importlib.metadata.PackageNotFoundError):
        raise TrainingError("Candidate G frozen training protocol dependencies could not be verified.") from None
    if protocol != expected:
        raise TrainingError("Candidate G training protocol differs from exact data, recipe, source, prices or software.")
    for entry in protocol["immutable_files"]:
        _entry(root, entry)
    return protocol, raw.digest(data)


def verified_rows(root, protocol):
    _, preparation = _load_preparation(root, protocol["preparation"]["manifest"]["path"])
    train = _prepared_rows(root, preparation["artifacts"]["train"], 96)
    validation = _prepared_rows(root, preparation["artifacts"]["validation"], 24)
    selected = sorted(train, key=lambda row: row["id"])
    random.Random(20260909).shuffle(selected)
    batches = [selected[i:i + 16] for i in range(0, 96, 16)]
    retention = _retention_rows(root)
    counts = {
        "training_sequences": len(selected), "training_batches": len(batches),
        "training_processed_tokens": sum(len(x["input_ids"]) for x in selected),
        "training_loss_tokens": int(sum(sum(x["weights"]) for x in selected)),
        "candidate_g_validation_sequences": len(validation),
        "candidate_g_two_forward_tokens": 2 * sum(len(x["input_ids"]) for x in validation),
        "raw_retention_sequences": len(retention["raw"]),
        "raw_two_forward_tokens": 2 * sum(len(x["input_ids"]) for x in retention["raw"]),
        "legacy_english_retention_sequences": len(retention["legacy"]),
        "legacy_english_two_forward_tokens": 2 * sum(len(x["input_ids"]) for x in retention["legacy"]),
    }
    if (counts != protocol["counts"]
            or raw.digest(raw.encoded([row["id"] for row in selected])) != protocol["sequence_order_sha256"]
            or [row["id"] for row in validation] != protocol["recipe"]["validation_ids"]
            or retention["bindings"] != protocol["retention"]):
        raise TrainingError("Candidate G rows, order or retention bindings changed.")
    return batches, validation, retention["raw"], retention["legacy"]


def verify_evaluation_freeze(root, protocol, training_protocol_sha256):
    path = _project_file(root, protocol["evaluation_protocol_path"])
    data = path.read_bytes()
    evaluation = json.loads(data)
    if (evaluation.get("status") != "frozen_before_training_and_generation"
            or evaluation.get("case_count") != 30 or evaluation.get("slot_count") != 60
            or evaluation.get("sampling_reserve_nano_usd") != SAMPLE_RESERVE_NANO):
        raise TrainingError("Candidate G evaluation protocol is not the exact frozen 30-case/60-slot design.")
    expected = {"path": TRAINING_PROTOCOL, "sha256": training_protocol_sha256}
    if expected not in evaluation.get("immutable_files", []):
        raise TrainingError("Evaluation protocol does not bind the exact training protocol.")
    from bibleprep import evaluate_candidate_g
    evaluate_candidate_g.load_protocol(Path(root).resolve(), path)
    return raw.digest(data)


def make_plan(config=Config(), root=ROOT):
    config.validate()
    protocol, protocol_hash = load_training_protocol(root, config.training_protocol)
    batches, validation, raw_holdout, legacy_holdout = verified_rows(root, protocol)
    source, _ = v1.source_receipt(config, Path(root))
    if source != protocol["source_adapter"]:
        raise TrainingError("Candidate G parent is not the exact completed retained B weights.")
    return {
        "schema_version": 1, "phase": "candidate_g_instruction", "arm": "G", "parent_arm": "B",
        "recipe": copy.deepcopy(protocol["recipe"]), "recipe_sha256": protocol["recipe_sha256"],
        "training_protocol_sha256": protocol_hash, "source_adapter": source,
        "source_checkpoint_file": SOURCE_CHECKPOINT_FILE,
        "software_sha256": protocol["software_sha256"], "counts": protocol["counts"],
        "sequence_order_sha256": protocol["sequence_order_sha256"],
        "fresh_training_client": True, "fresh_adapter": False, "optimizer_restored": False,
        "checkpoint_ttl_seconds": 30 * 86400, "budget": protocol["budget"],
        "preflight": protocol["preflight"], "pricing": protocol["pricing"],
        "execution_requires_frozen_evaluation": True,
    }, batches, validation, raw_holdout, legacy_holdout


class CandidateGNativeSession(v1.InstructionNativeSession):
    """Use the exercised D weights-only branch with G's exact recipe."""
    def call(self, operation, rows, settings):
        if (settings.get("arm") != "G" or settings.get("seed") != 20260909
                or settings.get("adam", {}).get("learning_rate") != 2e-5):
            raise TrainingError("Candidate G native settings differ from the frozen recipe.")
        return super().call(operation, rows, {**settings, "arm": "D"})


def candidate_g_worker(connection):
    os.environ["TINKER_TELEMETRY"] = "0"
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        session = CandidateGNativeSession()
        try:
            while True:
                request = connection.recv()
                try:
                    connection.send({"ok": True, "result": session.call(*request)})
                except BaseException as exc:
                    metadata = {"error_type": type(exc).__name__}
                    if type(getattr(exc, "status_code", None)) is int:
                        metadata["http_status"] = exc.status_code
                    connection.send({"ok": False, "error_metadata": metadata})
                    break
        except (EOFError, BrokenPipeError, OSError):
            pass
        finally:
            connection.close()


def _write_reservation(directory, run_id, protocol):
    budget = protocol["budget"]
    raw.write_private(directory / "sequence-reservation.json", {
        "schema_version": 1, "event": "candidate_g_full_sequence_reserved",
        "run_id": run_id, "training_protocol_sha256": protocol["training_protocol_sha256"],
        "evaluation_protocol_sha256": protocol["evaluation_protocol_sha256"],
        **budget, "invoice_reconciled": False,
    })


def run(config=Config(), *, execute=False, root=ROOT, transport=None):
    root = Path(root).resolve()
    plan, batches, validation, raw_holdout, legacy_holdout = make_plan(config, root)
    if not execute:
        return {"status": "dry_run", **plan}
    training_protocol, training_hash = load_training_protocol(root, config.training_protocol)
    evaluation_hash = verify_evaluation_freeze(root, training_protocol, training_hash)
    _preflight(root, require_fresh=True)
    plan["evaluation_protocol_sha256"] = evaluation_hash
    source, source_checkpoint = v1.source_receipt(config, root)
    if source != plan["source_adapter"]:
        raise TrainingError("Retained B receipt changed after planning.")
    directory = raw.private_path(root, config.run_dir)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    run_id = uuid.uuid4().hex
    raw.write_private(directory / "plan.json", {"run_id": run_id, **plan})
    reservation_protocol = {**training_protocol, "training_protocol_sha256": training_hash,
                            "evaluation_protocol_sha256": evaluation_hash}
    _write_reservation(directory, run_id, reservation_protocol)
    journal = directory / "events.jsonl"
    settings = {"timeout_seconds": 600.0, "seed": 20260909, "arm": "G",
                "adam": plan["recipe"]["adam"], "checkpoint_ttl_seconds": 30 * 86400,
                "source_checkpoint": source_checkpoint}
    native = transport
    operation_id = 0
    allocated = 0
    operation_cap = (sum(value for key, value in training_protocol["budget"]["breakdown_nano_usd"].items()
                         if key not in {"fresh_b_g_sampling", "hosting_probe"}))

    def invoke(operation, rows=(), *, stage, step=None, budget=0):
        nonlocal operation_id, allocated
        operation_id += 1
        allocated += budget
        if allocated > operation_cap:
            raise TrainingError("Training operations exceed their durable Candidate G reservation.")
        event = {"operation_id": operation_id, "operation": operation, "stage": stage,
                 "step": step, "reserved_nano_usd": budget,
                 "processed_tokens": sum(len(row["input_ids"]) for row in rows)}
        raw.append_event(journal, {"event": "operation_reserved", **event})
        try:
            sent = [{key: row[key] for key in ("input_ids", "target_ids", "weights")} for row in rows]
            result = native(operation, sent, settings)
            metrics = raw.weighted_nll(rows, result["logprobs"]) if rows else None
            if rows:
                metrics["by_language"] = {}
                for language in sorted({row["language"] for row in rows}):
                    chosen = [(row, values) for row, values in zip(rows, result["logprobs"])
                              if row["language"] == language]
                    metrics["by_language"][language] = raw.weighted_nll(
                        [x[0] for x in chosen], [x[1] for x in chosen])
            if operation in {"state", "sampler"}:
                marker = "/weights/" if operation == "state" else "/sampler_weights/"
                if (not isinstance(result.get("path"), str)
                        or not re.fullmatch(r"tinker://[A-Za-z0-9._:/-]+", result["path"])
                        or marker not in result["path"]):
                    raise TrainingError("Candidate G checkpoint reference is invalid.")
            raw.append_event(journal, {"event": "operation_complete", **event, "metrics": metrics})
            return result, metrics
        except BaseException as exc:
            raw.append_event(journal, {"event": "operation_uncertain", **event,
                "error_metadata": getattr(exc, "error_metadata", {"error_type": type(exc).__name__})})
            raise TrainingError("Candidate G operation is uncertain; stopped without retry or resume.") from None

    try:
        if native is None:
            from bibleprep.environment import load_project_environment
            load_project_environment()
            if not os.environ.get("TINKER_API_KEY"):
                raise TrainingError("TINKER_API_KEY is unavailable.")
            native = raw.BoundedTrainingTransport(worker=candidate_g_worker)
        for operation in ("create", "verify_client", "verify_source", "load_weights"):
            invoke(operation, stage="initialization")
        def forward(rows, stage):
            return invoke("forward", rows, stage=stage,
                          budget=sum(len(row["input_ids"]) for row in rows) * raw.TOKEN_NANO)[1]
        before_g = forward(validation, "baseline_candidate_g_validation")
        before_raw = forward(raw_holdout, "baseline_raw_12_retention")
        before_legacy = forward(legacy_holdout, "baseline_legacy_english_16_retention")
        steps = []
        for index, batch in enumerate(batches, 1):
            _, metrics = invoke("forward_backward", batch, stage="candidate_g_training", step=index,
                                budget=sum(len(row["input_ids"]) for row in batch) * raw.TOKEN_NANO)
            invoke("optim", stage="candidate_g_training", step=index)
            steps.append(metrics)
        after_g = forward(validation, "end_candidate_g_validation")
        after_raw = forward(raw_holdout, "end_raw_12_retention")
        after_legacy = forward(legacy_holdout, "end_legacy_english_16_retention")
        checkpoints = {"training_state_path": None, "sampler_path": None}
        for operation, key in (("state", "training_state_path"), ("sampler", "sampler_path")):
            settings["checkpoint_name"] = "candidate-g-" + operation
            result, _ = invoke(operation, stage="checkpoint", budget=3 * raw.NANO // 2)
            checkpoints[key] = result["path"]
            raw.write_private(directory / "checkpoints.json", checkpoints)
        summary = {
            "schema_version": 1, "status": "complete", "phase": "candidate_g_instruction",
            "arm": "G", "parent_arm": "B", "run_id": run_id,
            "training_protocol_sha256": training_hash,
            "evaluation_protocol_sha256": evaluation_hash,
            "recipe_sha256": plan["recipe_sha256"], "source_adapter": plan["source_adapter"],
            "optimizer_restored": False, "checkpoint_ttl_seconds": 30 * 86400,
            "training_batches": 6,
            "training_processed_tokens": plan["counts"]["training_processed_tokens"],
            "training_loss_tokens": plan["counts"]["training_loss_tokens"],
            "training_weighted_nll": math.fsum(x["weighted_loss_sum"] for x in steps)
                / sum(x["loss_tokens"] for x in steps),
            "baseline_candidate_g_validation": before_g, "end_candidate_g_validation": after_g,
            "baseline_raw_12_retention": before_raw, "end_raw_12_retention": after_raw,
            "baseline_legacy_english_16_retention": before_legacy,
            "end_legacy_english_16_retention": after_legacy,
            "checkpoint_reference_sha256": raw.digest((directory / "checkpoints.json").read_bytes()),
            "full_sequence_reserved_nano_usd": training_protocol["budget"]["total_reserved_nano_usd"],
            "loss_interpretation": "assistant_target_prediction_diagnostic_not_translation_accuracy",
            "accounting_is_invoice": False,
        }
        raw.write_private(directory / "summary.json", summary)
        raw.append_event(journal, {"event": "run_complete", "run_id": run_id})
        return {**summary, "run_directory_name": directory.name}
    except BaseException:
        raw.write_private(directory / "summary.json", {
            "schema_version": 1, "status": "stopped_uncertain",
            "phase": "candidate_g_instruction", "arm": "G", "run_id": run_id,
            "training_protocol_sha256": training_hash,
            "evaluation_protocol_sha256": evaluation_hash, "accounting_is_invoice": False})
        raise TrainingError("Candidate G stopped; no retry or resume is permitted. Inspect the private receipt.") from None
    finally:
        if native is not None:
            native.close()


def _check_metrics(metrics, rows):
    if not isinstance(metrics, dict):
        raise TrainingError("Candidate G journal lacks metrics.")
    expected = raw.weighted_nll(rows, [[-float(metrics["weighted_nll"]) for _ in row["weights"]]
                                       for row in rows])
    if (metrics.get("processed_tokens") != sum(len(row["input_ids"]) for row in rows)
            or metrics.get("loss_tokens") != sum(sum(row["weights"]) for row in rows)
            or not math.isfinite(metrics.get("weighted_nll", math.nan))
            or metrics["weighted_nll"] < 0
            or not math.isclose(metrics["weighted_loss_sum"],
                                metrics["weighted_nll"] * metrics["loss_tokens"],
                                rel_tol=1e-10, abs_tol=1e-10)
            or expected["loss_tokens"] != metrics["loss_tokens"]):
        raise TrainingError("Candidate G saved metrics are internally inconsistent.")


def verify_completed_checkpoint(root, relative_checkpoint_file):
    """Verify exact completion and return (sampler path, checkpoint-file hash)."""
    root = Path(root).resolve()
    checkpoint_path = _project_file(root, relative_checkpoint_file)
    directory = checkpoint_path.parent
    if (checkpoint_path.name != "checkpoints.json"
            or directory != _project_file(root, RUN_DIRECTORY)):
        raise TrainingError("Candidate G checkpoint file is outside the fixed run directory.")
    files = {name: (directory / name).read_bytes()
             for name in ("plan.json", "summary.json", "checkpoints.json",
                          "events.jsonl", "sequence-reservation.json")}
    plan, summary, checkpoints, reservation = (
        json.loads(files[name]) for name in
        ("plan.json", "summary.json", "checkpoints.json", "sequence-reservation.json"))
    protocol, protocol_hash = load_training_protocol(root)
    freeze_hash = verify_evaluation_freeze(root, protocol, protocol_hash)
    checkpoint_hash = raw.digest(files["checkpoints.json"])
    if (summary.get("status") != "complete" or plan.get("run_id") != summary.get("run_id")
            or plan.get("training_protocol_sha256") != protocol_hash
            or summary.get("training_protocol_sha256") != protocol_hash
            or plan.get("evaluation_protocol_sha256") != freeze_hash
            or summary.get("evaluation_protocol_sha256") != freeze_hash
            or plan.get("recipe") != protocol["recipe"]
            or plan.get("recipe_sha256") != protocol["recipe_sha256"]
            or plan.get("source_adapter") != protocol["source_adapter"]
            or summary.get("source_adapter") != protocol["source_adapter"]
            or plan.get("software_sha256") != protocol["software_sha256"]
            or plan.get("sequence_order_sha256") != protocol["sequence_order_sha256"]
            or plan.get("counts") != protocol["counts"]
            or summary.get("training_batches") != protocol["counts"]["training_batches"]
            or summary.get("training_processed_tokens") != protocol["counts"]["training_processed_tokens"]
            or summary.get("training_loss_tokens") != protocol["counts"]["training_loss_tokens"]
            or summary.get("optimizer_restored") is not False
            or summary.get("checkpoint_reference_sha256") != checkpoint_hash
            or reservation.get("event") != "candidate_g_full_sequence_reserved"
            or reservation.get("run_id") != plan["run_id"]
            or reservation.get("training_protocol_sha256") != protocol_hash
            or reservation.get("evaluation_protocol_sha256") != freeze_hash
            or any(reservation.get(key) != value for key, value in protocol["budget"].items())):
        raise TrainingError("Candidate G completion files disagree with the frozen protocol.")
    source, _ = v1.source_receipt(Config(), root)
    if source != protocol["source_adapter"]:
        raise TrainingError("Candidate G completion no longer binds the retained B parent.")
    batches, validation, raw_holdout, legacy_holdout = verified_rows(root, protocol)
    operations = [(name, (), "initialization", None, 0)
                  for name in ("create", "verify_client", "verify_source", "load_weights")]
    for rows, before in ((validation, "baseline_candidate_g_validation"),
                         (raw_holdout, "baseline_raw_12_retention"),
                         (legacy_holdout, "baseline_legacy_english_16_retention")):
        operations.append(("forward", rows, before, None,
                           sum(len(x["input_ids"]) for x in rows) * raw.TOKEN_NANO))
    for index, batch in enumerate(batches, 1):
        operations += [("forward_backward", batch, "candidate_g_training", index,
                        sum(len(x["input_ids"]) for x in batch) * raw.TOKEN_NANO),
                       ("optim", (), "candidate_g_training", index, 0)]
    for rows, after in ((validation, "end_candidate_g_validation"),
                        (raw_holdout, "end_raw_12_retention"),
                        (legacy_holdout, "end_legacy_english_16_retention")):
        operations.append(("forward", rows, after, None,
                           sum(len(x["input_ids"]) for x in rows) * raw.TOKEN_NANO))
    operations += [("state", (), "checkpoint", None, 3 * raw.NANO // 2),
                   ("sampler", (), "checkpoint", None, 3 * raw.NANO // 2)]
    events = [json.loads(line) for line in files["events.jsonl"].splitlines()]
    if (len(events) != 2 * len(operations) + 1
            or {k: v for k, v in events[-1].items() if k != "time_utc"}
            != {"event": "run_complete", "run_id": plan["run_id"]}):
        raise TrainingError("Candidate G journal is incomplete, uncertain, or has extra operations.")
    training_metrics = []
    for index, (operation, rows, stage, step, budget) in enumerate(operations, 1):
        expected = {"operation_id": index, "operation": operation, "stage": stage,
                    "step": step, "reserved_nano_usd": budget,
                    "processed_tokens": sum(len(row["input_ids"]) for row in rows)}
        reserved, completed = events[2 * index - 2:2 * index]
        if ({k: v for k, v in reserved.items() if k != "time_utc"}
                != {"event": "operation_reserved", **expected}
                or completed.get("event") != "operation_complete"
                or any(completed.get(key) != value for key, value in expected.items())):
            raise TrainingError("Candidate G journal does not prove each operation completed once.")
        metrics = completed.get("metrics")
        if rows:
            _check_metrics(metrics, rows)
            languages = {row["language"] for row in rows}
            if set(metrics.get("by_language", {})) != languages:
                raise TrainingError("Candidate G language metrics are incomplete.")
            for language in languages:
                _check_metrics(metrics["by_language"][language],
                               [row for row in rows if row["language"] == language])
            if not math.isclose(
                    sum(value["weighted_loss_sum"] for value in metrics["by_language"].values()),
                    metrics["weighted_loss_sum"], rel_tol=1e-10, abs_tol=1e-10):
                raise TrainingError("Candidate G language losses do not reconcile.")
            if operation == "forward_backward":
                training_metrics.append(metrics)
            elif summary.get(stage) != metrics:
                raise TrainingError("Candidate G saved forward metric differs from its journal.")
        elif metrics is not None:
            raise TrainingError("Non-forward Candidate G operation contains metrics.")
    nll = math.fsum(x["weighted_loss_sum"] for x in training_metrics) / sum(
        x["loss_tokens"] for x in training_metrics)
    if not math.isclose(summary.get("training_weighted_nll"), nll,
                        rel_tol=1e-10, abs_tol=1e-10):
        raise TrainingError("Candidate G training diagnostic differs from its journal.")
    for key, marker in (("training_state_path", "/weights/"),
                        ("sampler_path", "/sampler_weights/")):
        value = checkpoints.get(key)
        if (not isinstance(value, str) or marker not in value
                or not re.fullmatch(r"tinker://[A-Za-z0-9._:/-]+", value)):
            raise TrainingError("Candidate G must retain both private checkpoint kinds.")
    return checkpoints["sampler_path"], checkpoint_hash


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--preparation-manifest")
    options = parser.parse_args(argv)
    try:
        if options.preparation_manifest:
            result = build_training_protocol(ROOT, options.preparation_manifest)
        else:
            result = run(execute=options.execute)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except BaseException:
        print("Candidate G planning or training could not complete; no retry was attempted.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
