"""One raw-text Inkling adaptation pass; offline planning unless --execute is supplied.

Prepared arrays are already shifted. Cross entropy is summed for optimization;
reported NLL is independently weighted by the original token mask. Checkpoint
references and durable reservations live only under ignored runs/. No resume.
"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import importlib.metadata
import json
import math
import multiprocessing
import os
from pathlib import Path
import random
import threading
import uuid


ROOT = Path(__file__).resolve().parents[1]
MODEL = "thinkingmachines/Inkling"
SDK_VERSION = "0.27.1"
NANO = 1_000_000_000
TOKEN_NANO = 5610  # $5.61 per million processed positions, including forwards.
HARD_CAP_NANO = 50 * NANO
MANIFEST = "manifests/preparation-inkling-v1.json"


class TrainingError(RuntimeError):
    """Only authored, account-independent messages may leave this runner."""


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def money(value):
    return float(Decimal(value) / NANO)


def dollars(value):
    amount = Decimal(str(value)) * NANO
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise TrainingError("Invalid dollar limit.")
    return int(amount)


@dataclass(frozen=True)
class Config:
    phase: str = "calibration"
    calibration_batches: int = 1
    batch_size: int = 16
    holdout_sequences: int = 12
    seed: int = 20260906
    learning_rate: float = 1e-4
    checkpoint_ttl_seconds: int = 30 * 86400
    checkpoint_reserve_usd: float = 3.0
    max_cost_usd: float = 50.0
    timeout_seconds: float = 600.0
    run_dir: str | None = None
    calibration_run: str | None = None

    def validate(self):
        if self.phase not in {"calibration", "full"}:
            raise TrainingError("Phase must be calibration or full.")
        if not 1 <= self.calibration_batches <= 2 or not 1 <= self.batch_size <= 16:
            raise TrainingError("Calibration permits one or two batches of at most sixteen sequences.")
        if not 1 <= self.holdout_sequences <= 12:
            raise TrainingError("The frozen holdout must contain at most twelve sequences.")
        if type(self.seed) is not int or not 0 <= self.seed < 2**31:
            raise TrainingError("Seed must be a nonnegative 31-bit integer.")
        if not math.isfinite(self.learning_rate) or not 0 < self.learning_rate <= 1e-3:
            raise TrainingError("Learning rate must be positive and at most 0.001.")
        if not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 3600:
            raise TrainingError("Operation deadline must be positive and at most one hour.")
        if not 1 <= self.checkpoint_ttl_seconds <= 30 * 86400:
            raise TrainingError("Checkpoint expiry must be within thirty days.")
        if not 0 < dollars(self.max_cost_usd) <= HARD_CAP_NANO:
            raise TrainingError("The combined estimated cost limit cannot exceed $50.")
        if dollars(self.checkpoint_reserve_usd) < 3 * NANO:
            raise TrainingError("Reserve at least $3 per run for checkpoints and storage.")


def private_path(root, value):
    runs = (root / "runs").resolve()
    path = Path(value)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(runs) or path == runs:
        raise TrainingError("Run artifacts must remain under the private runs directory.")
    return path


def read_rows(root, entry, split, manifest):
    path = (root / entry["path"]).resolve()
    if not path.is_relative_to((root / "data/prepared/inkling-v1").resolve()):
        raise TrainingError("Prepared artifact is outside the Inkling data directory.")
    raw = path.read_bytes()
    if digest(raw) != entry["sha256"]:
        raise TrainingError("Prepared artifact checksum mismatch.")
    rows = [json.loads(line) for line in raw.splitlines()]
    ids = set()
    for row in rows:
        inp, target, weights = (row[k] for k in ("input_ids", "target_ids", "weights"))
        if not inp or len(inp) != len(target) or len(inp) != len(weights):
            raise TrainingError("Prepared token arrays must be nonempty and aligned.")
        if any(type(t) is not int or t < 0 for t in inp + target):
            raise TrainingError("Invalid prepared token ID.")
        if any(type(w) not in (int, float) or w not in (0, 1) for w in weights):
            raise TrainingError("Only the original binary loss mask is supported.")
        if inp[1:] != target[:-1]:
            raise TrainingError("Prepared arrays are not shifted exactly once.")
        if inp[0] != manifest["bos_token_id"] or target[-1] != manifest["eos_token_id"]:
            raise TrainingError("Prepared native BOS/EOS differs from the manifest.")
        if weights[0] != 0 or weights[-1] != 1 or weights != sorted(weights):
            raise TrainingError("Metadata must be masked and the complete body/EOS scored.")
        if (len(inp) != row["processed_token_count"] or sum(weights) != row["loss_token_count"]
                or sum(weights) != row["body_token_count"] + 1
                or len(inp) > manifest["maximum_input_tokens"]):
            raise TrainingError("Prepared token counts or window length disagree.")
        if row["id"] in ids or row["split"] != split or not row.get("split_family"):
            raise TrainingError("Duplicate sequence or invalid development split.")
        if not isinstance(row.get("language"), str):
            raise TrainingError("A language label is required for stratification.")
        ids.add(row["id"])
    if (len(rows) != entry["sequences"] or sum(len(r["input_ids"]) for r in rows) != entry["processed_tokens"]
            or sum(sum(r["weights"]) for r in rows) != entry["loss_tokens"]):
        raise TrainingError("Artifact totals disagree with the preparation manifest.")
    return rows


def stratified(rows, count, seed):
    """Stable round-robin sampling across every available language, without replacement."""
    groups = {}
    for row in rows:
        groups.setdefault(row["language"], []).append(row)
    if count < len(groups):
        raise TrainingError("The selected sample is too small to cover its language strata.")
    rng = random.Random(seed)
    for language in sorted(groups):
        groups[language].sort(key=lambda r: r["id"])
        rng.shuffle(groups[language])
    result = []
    while len(result) < min(count, len(rows)):
        for language in sorted(groups):
            if groups[language] and len(result) < count:
                result.append(groups[language].pop())
    return result


def make_plan(config, root=ROOT):
    config.validate()
    raw = (root / MANIFEST).read_bytes()
    manifest = json.loads(raw)
    if (manifest.get("model") != MODEL or manifest.get("bos_token_id") != 200028 or manifest.get("eos_token_id") != 199999
            or manifest.get("unicode_normalization") != "none"):
        raise TrainingError("Unexpected native tokenizer or normalization settings.")
    for name, expected in manifest["preparation_code_sha256"].items():
        if digest((root / name).read_bytes()) != expected:
            raise TrainingError("Preparation code differs from the frozen corpus recipe.")
    if importlib.metadata.version("tinker") != SDK_VERSION:
        raise TrainingError("Training requires the pinned SDK version.")
    from bibleprep.prepare_inkling import load_tokenizer
    _, _, _, tokenizer_identity = load_tokenizer()
    if tokenizer_identity != manifest["tokenizer"]:
        raise TrainingError("Native tokenizer assets differ from the prepared corpus.")
    train = read_rows(root, manifest["artifacts"]["train"], "train", manifest)
    validation = read_rows(root, manifest["artifacts"]["validation"], "validation", manifest)
    families = lambda rows: {encoded(r["split_family"]) for r in rows}
    if (families(train) & families(validation)
            or {r["id"] for r in train} & {r["id"] for r in validation}):
        raise TrainingError("Training and validation overlap.")
    holdout = stratified(validation, config.holdout_sequences, config.seed)
    if config.phase == "calibration":
        selected = stratified(train, config.calibration_batches * config.batch_size, config.seed)
    else:
        selected = sorted(train, key=lambda r: r["id"])
        random.Random(config.seed).shuffle(selected)
    batches = [selected[i:i + config.batch_size] for i in range(0, len(selected), config.batch_size)]
    recipe = {"model": MODEL, "manifest_sha256": digest(raw), "rank": 8,
              "train_mlp": True, "train_attn": True, "train_unembed": True,
              "seed": config.seed, "batch_size": config.batch_size,
              "loss_fn": "cross_entropy", "optimization_loss_reduction": "sum",
              "adam": {"learning_rate": config.learning_rate, "beta1": 0.9, "beta2": 0.95,
                       "eps": 1e-8, "weight_decay": 0.0, "grad_clip_norm": 0.0},
              "holdout_ids": [r["id"] for r in holdout]}
    training_tokens = sum(len(r["input_ids"]) for r in selected)
    forward_tokens = 2 * sum(len(r["input_ids"]) for r in holdout)
    checkpoint_nano = dollars(config.checkpoint_reserve_usd)
    planned_nano = (training_tokens + forward_tokens) * TOKEN_NANO + checkpoint_nano
    full_nano = (sum(len(r["input_ids"]) for r in train) + forward_tokens) * TOKEN_NANO + checkpoint_nano
    if planned_nano > dollars(config.max_cost_usd):
        raise TrainingError("The complete planned run exceeds the estimated cost cap.")
    software_files = ("bibleprep/train_inkling.py", "bibleprep/prepare_inkling.py",
                      "bibleprep/environment.py", "bibleprep/evaluate_adapter.py",
                      "requirements-training.txt", "requirements-comparison-large.lock.txt")
    plan = {"schema_version": 1, "phase": config.phase, "recipe": recipe,
            "software_sha256": {name: digest((root / name).read_bytes()) for name in software_files},
            "recipe_sha256": digest(encoded(recipe)), "sdk_version": SDK_VERSION,
            "training_sequences": len(selected), "training_batches": len(batches),
            "training_processed_tokens": training_tokens,
            "training_loss_tokens": sum(sum(r["weights"]) for r in selected),
            "holdout_sequences": len(holdout), "two_holdout_forward_tokens": forward_tokens,
            "sequence_order_sha256": digest(encoded([r["id"] for r in selected])),
            "epochs": 1 if config.phase == "full" else None,
            "fresh_adapter": True, "learning_rate_status": "generic_recipe_not_Inkling_calibrated",
            "compute_rate_usd_per_million": 5.61,
            "compute_reserve_nano_usd": (training_tokens + forward_tokens) * TOKEN_NANO,
            "checkpoint_reserve_nano_usd": checkpoint_nano, "planned_nano_usd": planned_nano,
            "planned_estimated_usd": money(planned_nano),
            "calibration_plus_fresh_full_estimated_usd": money(planned_nano + full_nano)
            if config.phase == "calibration" else None,
            "checkpoint_ttl_seconds": config.checkpoint_ttl_seconds,
            "cost_status": "conservative_estimate_not_invoice_or_guaranteed_provider_cap",
            "checkpoint_cost_status": "storage_and_operation_contingency_not_verified_unit_charge",
            "adapter_parameter_estimate": 1266698752, "base_revision": "provider_revision_unpinned"}
    return plan, batches, holdout


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_private(path, value):
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(encoded(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    sync_directory(path.parent)


def append_event(path, event):
    event = {"time_utc": datetime.now(timezone.utc).isoformat(), **event}
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "ab") as handle:
        handle.write(encoded(event) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    sync_directory(path.parent)


def reserve_budget(root, run_id, amount, cap):
    """The complete planned cost stays reserved even after failure or uncertainty."""
    runs = root / "runs"
    ledger = runs / "inkling-training-budget.jsonl"
    lock_fd = os.open(runs / "inkling-training-budget.lock", os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(lock_fd, "rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = [json.loads(x) for x in ledger.read_bytes().splitlines()] if ledger.exists() else []
        if any(e.get("event") != "run_budget_reserved" or type(e.get("amount_nano_usd")) is not int
               or e["amount_nano_usd"] < 0 for e in entries):
            raise TrainingError("The private budget ledger needs manual inspection.")
        used = sum(e["amount_nano_usd"] for e in entries)
        if used + amount > min(cap, HARD_CAP_NANO):
            raise TrainingError("Combined calibration/training reservations exceed the cost cap.")
        append_event(ledger, {"event": "run_budget_reserved", "run_id": run_id,
                              "amount_nano_usd": amount})
        return used + amount


def weighted_nll(rows, logprobs):
    if not isinstance(logprobs, list) or len(logprobs) != len(rows):
        raise TrainingError("Training output does not align with submitted sequences.")
    terms = []
    for row, values in zip(rows, logprobs):
        if not isinstance(values, list) or len(values) != len(row["weights"]):
            raise TrainingError("Training log probabilities do not align with target positions.")
        for value, weight in zip(values, row["weights"]):
            if type(value) not in (float, int) or not math.isfinite(value) or value > 1e-5:
                raise TrainingError("Training returned invalid log probabilities.")
            if weight:
                terms.append(-float(value) * weight)
    denominator = sum(sum(r["weights"]) for r in rows)
    total = math.fsum(terms)
    if not denominator or not math.isfinite(total) or total < 0:
        raise TrainingError("Weighted training NLL is not finite and nonnegative.")
    return {"weighted_nll": total / denominator, "weighted_loss_sum": total,
            "loss_tokens": denominator, "processed_tokens": sum(len(r["input_ids"]) for r in rows)}


async def single_attempt(function, *args, **kwargs):
    return await function(*args, **kwargs)


def disable_submission_retries(holder):
    """Pinned private SDK hook, scoped to this worker's holder, never global."""
    if not callable(getattr(holder, "execute_with_retries", None)):
        raise TrainingError("Pinned SDK retry hook is unavailable.")
    holder.execute_with_retries = single_attempt


class NativeSession:
    def __init__(self):
        self.client = self.service = self.types = None

    def call(self, operation, rows, settings):
        if operation == "create":
            if self.client is not None or importlib.metadata.version("tinker") != SDK_VERSION:
                raise TrainingError("A fresh client and the pinned SDK version are required.")
            import tinker
            secret = os.environ.get("TINKER_API_KEY")
            if not secret:
                raise TrainingError("TINKER_API_KEY is unavailable.")
            self.types = tinker.types
            self.service = tinker.ServiceClient(api_key=secret, base_url="https://tinker.thinkingmachines.dev/services/tinker-prod",
                                                max_retries=0, timeout=settings["timeout_seconds"])
            holder = self.service.holder
            disable_submission_retries(holder)
            self.client = self.service.create_lora_training_client(
                base_model=MODEL, rank=8, seed=settings["seed"],
                train_mlp=True, train_attn=True, train_unembed=True)
            if self.client.holder is not holder:
                raise TrainingError("Training client did not retain the bounded submission holder.")
            return {}
        if self.client is None:
            raise TrainingError("Training client has not been created.")
        if operation in {"forward", "forward_backward"}:
            data = [self.types.Datum(model_input=self.types.ModelInput.from_ints(r["input_ids"]),
                    loss_fn_inputs={"target_tokens": self.types.TensorData(data=r["target_ids"], dtype="int64", shape=[len(r["target_ids"])]),
                                    "weights": self.types.TensorData(data=r["weights"], dtype="float32", shape=[len(r["weights"])])}) for r in rows]
            result = getattr(self.client, operation)(data, loss_fn="cross_entropy").result(timeout=settings["timeout_seconds"])
            return {"logprobs": [list(output["logprobs"].data) for output in result.loss_fn_outputs]}
        if operation == "optim":
            self.client.optim_step(self.types.AdamParams(**settings["adam"])).result(timeout=settings["timeout_seconds"])
            return {}
        method = {"state": "save_state", "sampler": "save_weights_for_sampler"}.get(operation)
        if method is None:
            raise TrainingError("Unknown training operation.")
        result = getattr(self.client, method)(settings["checkpoint_name"], ttl_seconds=settings["checkpoint_ttl_seconds"]).result(timeout=settings["timeout_seconds"])
        return {"path": result.path}


def training_worker(connection):
    os.environ["TINKER_TELEMETRY"] = "0"
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        session = NativeSession()
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


class BoundedTrainingTransport:
    """Persistent client with a deadline covering pipe send, SDK work, and reply."""
    def __init__(self, worker=training_worker):
        self.worker = worker
        self.process = self.connection = None
        self.failed = False

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(2)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join(2)
            else:
                self.process.join(0)
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __call__(self, operation, rows, settings):
        if self.failed:
            raise TrainingError("An uncertain training request cannot be retried automatically.")
        if self.process is None:
            ctx = multiprocessing.get_context("spawn")
            self.connection, child = ctx.Pipe()
            self.process = ctx.Process(target=self.worker, args=(child,), daemon=True)
            self.process.start()
            child.close()
        reply = []
        connection = self.connection
        def exchange():
            try:
                connection.send((operation, rows, settings))
                reply.append(connection.recv())
            except BaseException:
                reply.append({"ok": False})
        thread = threading.Thread(target=exchange, daemon=True)
        thread.start()
        thread.join(settings["timeout_seconds"])
        if thread.is_alive() or not reply or not isinstance(reply[0], dict) or not reply[0].get("ok"):
            self.failed = True
            self.close()
            thread.join(1)
            error = TrainingError("Training operation is uncertain; stopped without retry or resume.")
            error.error_metadata = reply[0].get("error_metadata", {}) if reply and isinstance(reply[0], dict) else {"error_type": "LocalDeadlineOrWorkerFailure"}
            raise error
        return reply[0]["result"]


def run(config, *, execute=False, root=ROOT, transport=None):
    plan, batches, holdout = make_plan(config, root)
    if not execute:
        return {"status": "dry_run", **plan}
    if transport is None:
        from bibleprep.environment import load_project_environment
        load_project_environment()
        if not os.environ.get("TINKER_API_KEY"):
            raise TrainingError("TINKER_API_KEY is unavailable.")
    if config.phase == "full":
        if not config.calibration_run:
            raise TrainingError("Full execution requires a completed calibration run.")
        receipt = json.loads((private_path(root, config.calibration_run) / "summary.json").read_text())
        if (receipt.get("status") != "complete" or receipt.get("phase") != "calibration"
                or receipt.get("recipe_sha256") != plan["recipe_sha256"]):
            raise TrainingError("Calibration receipt is incomplete or uses a different data/recipe snapshot.")
    slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    directory = private_path(root, config.run_dir or "runs/inkling-" + config.phase + "-" + slug)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    run_id = uuid.uuid4().hex
    write_private(directory / "plan.json", {"run_id": run_id, **plan})
    used = reserve_budget(root, run_id, plan["planned_nano_usd"], dollars(config.max_cost_usd))
    journal = directory / "events.jsonl"
    settings = {"timeout_seconds": config.timeout_seconds, "seed": config.seed,
                "adam": plan["recipe"]["adam"], "checkpoint_ttl_seconds": config.checkpoint_ttl_seconds}
    native = BoundedTrainingTransport() if transport is None else transport
    op_count = 0
    allocated = 0

    def invoke(operation, rows=(), *, budget=0, stage="", step=None):
        nonlocal op_count, allocated
        op_count += 1
        allocated += budget
        if allocated > plan["planned_nano_usd"]:
            raise TrainingError("Operation costs exceed the complete run reservation.")
        event = {"operation_id": op_count, "operation": operation, "stage": stage, "step": step,
                 "reserved_nano_usd": budget, "processed_tokens": sum(len(r["input_ids"]) for r in rows)}
        append_event(journal, {"event": "operation_reserved", **event})
        try:
            result = native(operation, rows, settings)
            metrics = weighted_nll(rows, result["logprobs"]) if rows else None
            if operation in {"state", "sampler"} and (not isinstance(result.get("path"), str) or not result["path"].startswith("tinker://")):
                raise TrainingError("Checkpoint reply does not contain a valid private reference.")
            append_event(journal, {"event": "operation_complete", **event, "metrics": metrics})
            return result, metrics
        except BaseException as exc:
            append_event(journal, {"event": "operation_uncertain", **event,
                                  "error_metadata": getattr(exc, "error_metadata", {"error_type": type(exc).__name__})})
            raise TrainingError("Training stopped after an uncertain operation; no automatic retry or resume.") from None

    try:
        invoke("create")
        forward_budget = sum(len(r["input_ids"]) for r in holdout) * TOKEN_NANO
        _, before = invoke("forward", holdout, budget=forward_budget, stage="baseline_holdout")
        steps = []
        for index, batch in enumerate(batches, 1):
            _, metrics = invoke("forward_backward", batch, budget=sum(len(r["input_ids"]) for r in batch) * TOKEN_NANO,
                                stage="training", step=index)
            invoke("optim", stage="training", step=index)
            steps.append(metrics)
        _, after = invoke("forward", holdout, budget=forward_budget, stage="end_holdout")
        checkpoints = {"training_state_path": None, "sampler_path": None}
        for operation, key in (("state", "training_state_path"), ("sampler", "sampler_path")):
            settings["checkpoint_name"] = config.phase + "-" + operation
            result, _ = invoke(operation, budget=plan["checkpoint_reserve_nano_usd"] // 2, stage="checkpoint")
            checkpoints[key] = result["path"]
            write_private(directory / "checkpoints.json", checkpoints)
        summary = {"status": "complete", "phase": config.phase, "run_id": run_id,
                   "recipe_sha256": plan["recipe_sha256"], "training_batches": len(steps),
                   "training_processed_tokens": plan["training_processed_tokens"],
                   "training_loss_tokens": plan["training_loss_tokens"],
                   "baseline_holdout": before, "end_holdout": after,
                   "training_weighted_nll": math.fsum(s["weighted_loss_sum"] for s in steps) / sum(s["loss_tokens"] for s in steps),
                   "planned_estimated_usd": plan["planned_estimated_usd"],
                   "combined_reserved_estimated_usd": money(used),
                   "accounting_is_invoice": False, "checkpoint_ttl_seconds": config.checkpoint_ttl_seconds}
        write_private(directory / "summary.json", summary)
        append_event(journal, {"event": "run_complete", "run_id": run_id})
        return {**summary, "run_directory_name": directory.name}
    except BaseException:
        write_private(directory / "summary.json", {"status": "stopped_uncertain", "phase": config.phase,
                      "run_id": run_id, "recipe_sha256": plan["recipe_sha256"], "accounting_is_invoice": False})
        raise TrainingError("Training stopped; reserved costs remain charged against the local cap. Inspect private run status.") from None
    finally:
        native.close()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--phase", choices=("calibration", "full"), default="calibration")
    for name, kind in (("calibration_batches", int), ("batch_size", int), ("holdout_sequences", int),
                       ("seed", int), ("learning_rate", float), ("checkpoint_ttl_seconds", int),
                       ("checkpoint_reserve_usd", float), ("max_cost_usd", float), ("timeout_seconds", float)):
        p.add_argument("--" + name.replace("_", "-"), type=kind, default=getattr(Config(), name))
    p.add_argument("--run-dir")
    p.add_argument("--calibration-run")
    return p


def main(argv=None):
    values = vars(parser().parse_args(argv))
    execute = values.pop("execute")
    try:
        print(json.dumps(run(Config(**values), execute=execute), ensure_ascii=False, indent=2, allow_nan=False))
    except TrainingError as exc:
        print(str(exc))
        return 1
    except BaseException:
        print("Training could not complete; no automatic retry was attempted.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
