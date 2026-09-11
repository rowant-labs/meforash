"""Matched four-arm Inkling evaluation; paid sampling requires --execute."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

from bibleprep import evaluate as ev
from bibleprep import evaluate_adapter as adapter
from bibleprep import tinker_compare as comparison
from bibleprep import tinker_evaluate as native

ROOT = comparison.ROOT
PROTOCOL = "manifests/instruction-experiment-v1.json"
STATES = {"A": "unchanged", "B": "original_text_only",
          "C": "instruction_only", "D": "original_text_then_instruction"}
SHA = re.compile(r"[0-9a-f]{64}")
PUBLIC_RESULT_FIELDS = {"mode", "selected_cases", "completed_cases", "pending_cases",
    "accounted_cost_usd", "per_request_reservation_usd", "remaining_worst_case_usd",
    "stop_reason", "historical_correctness"}


def _path(root, value, *, under=None):
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = Path(root) / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to((Path(root) / under).resolve() if under else Path(root).resolve())
    except ValueError:
        raise ev.EvaluationError("Evaluation artifact is outside its allowed project directory.") from None
    cursor = candidate
    while cursor != Path(root).resolve() and cursor != cursor.parent:
        if cursor.is_symlink():
            raise ev.EvaluationError("Evaluation artifacts must not use symlinked paths.")
        cursor = cursor.parent
    if not resolved.is_file():
        raise ev.EvaluationError("A required evaluation artifact is unavailable.")
    return resolved


def _read(root, value, *, under=None):
    path = _path(root, value, under=under)
    raw = path.read_bytes()
    return path, raw, json.loads(raw)


def _checked(root, entry, *, under=None):
    path, raw, value = _read(root, entry["path"], under=under)
    if not SHA.fullmatch(entry.get("sha256", "")) or ev.digest(raw) != entry["sha256"]:
        raise ev.EvaluationError("A frozen evaluation artifact checksum changed.")
    return path, raw, value


def load_protocol(root=ROOT):
    _, raw, protocol = _read(root, PROTOCOL, under="manifests")
    if (protocol.get("schema_version") != 1 or protocol.get("status") != "frozen_before_sampling"
            or protocol.get("arms") != STATES):
        raise ev.EvaluationError("The four-arm evaluation protocol is not frozen.")
    _, _, freeze = _checked(root, protocol["evaluation_manifest"], under="manifests")
    _, _, exclusions = _checked(root, protocol["evaluation_exclusions"], under="manifests")
    dataset = protocol["evaluation"]
    if (freeze.get("dataset", {}).get("path") != dataset["path"]
            or freeze["dataset"].get("sha256") != dataset["sha256"]
            or freeze["dataset"].get("cases") != dataset["cases"]
            or exclusions.get("status") != "frozen"
            or exclusions.get("evaluation_sha256") != dataset["sha256"]):
        raise ev.EvaluationError("Fresh evaluation and exclusion freeze identities disagree.")
    return protocol, ev.digest(raw)


def verified_dataset(config, protocol, root=ROOT):
    if not config.get("dataset"):
        raise ev.EvaluationError("An explicitly frozen evaluation dataset is required.")
    path = _path(root, config["dataset"])
    relative = str(path.relative_to(Path(root).resolve()))
    allowed = [entry for entry in protocol["allowed_datasets"] if entry["path"] == relative]
    if len(allowed) != 1:
        raise ev.EvaluationError("This dataset path is not in the frozen comparison protocol.")
    entry = allowed[0]
    cases, fingerprint = ev.load_cases(path)
    if (fingerprint != entry["sha256"] or len(cases) != entry["cases"]
            or config.get("max_cases") != entry["cases"]
            or [case["id"] for case in cases] != entry["case_ids"]):
        raise ev.EvaluationError("The evaluation content, order, count, or selected subset changed.")
    # This protocol permits only the full set; shards need a prespecified version.
    if entry != protocol["evaluation"]:
        raise ev.EvaluationError("Only the complete frozen evaluation is enabled.")
    return relative, fingerprint


def _journal(raw, plan, *, legacy=False):
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if not events or any(not isinstance(event, dict) for event in events):
        raise ev.EvaluationError("The training completion journal is invalid.")
    final = events[-1]
    if final.get("event") != "run_complete" or (not legacy and final.get("run_id") != plan["run_id"]):
        raise ev.EvaluationError("The training journal lacks its matching terminal completion receipt.")
    operations, prior = [], events[:-1]
    if len(prior) % 2:
        raise ev.EvaluationError("The training journal contains an unresolved operation.")
    for index in range(0, len(prior), 2):
        reserved, complete = prior[index:index+2]
        keys = ("operation", "operation_id", "stage", "step", "processed_tokens", "reserved_nano_usd")
        if (reserved.get("event") != "operation_reserved" or complete.get("event") != "operation_complete"
                or reserved.get("operation_id") != index // 2 + 1
                or any(reserved.get(key) != complete.get(key) for key in keys)):
            raise ev.EvaluationError("The training journal is incomplete, uncertain, or inconsistent.")
        operations.append(complete)
    if (not operations or operations[0]["operation"] != "create"
            or [event["operation"] for event in operations[-2:]] != ["state", "sampler"]
            or sum(event["operation"] == "forward_backward" for event in operations) != plan["training_batches"]
            or sum(event["operation"] == "optim" for event in operations) != plan["training_batches"]):
        raise ev.EvaluationError("The journal does not certify the planned updates and both checkpoints.")


def _receipt(checkpoint_file, root):
    path = _path(root, checkpoint_file, under="runs")
    if path.name != "checkpoints.json":
        raise ev.EvaluationError("Use the completed run's checkpoints.json receipt.")
    files = {name: _path(root, path.parent / name, under="runs").read_bytes()
             for name in ("checkpoints.json", "summary.json", "plan.json", "events.jsonl")}
    checkpoints, summary, plan = (json.loads(files[name]) for name in ("checkpoints.json", "summary.json", "plan.json"))
    if (not isinstance(plan.get("run_id"), str) or not plan["run_id"]
            or summary.get("run_id") != plan["run_id"] or summary.get("status") != "complete"
            or summary.get("phase") != plan.get("phase")
            or summary.get("recipe_sha256") != plan.get("recipe_sha256")
            or ev.digest(json.dumps(plan.get("recipe"), sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()) != plan.get("recipe_sha256")
            or plan["recipe"].get("model") != "thinkingmachines/Inkling"):
        raise ev.EvaluationError("Checkpoint plan, completed summary, and recipe do not agree.")
    for key, marker in (("sampler_path", "/sampler_weights/"), ("training_state_path", "/weights/")):
        value = checkpoints.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"tinker://[A-Za-z0-9._:/-]+", value) or marker not in value:
            raise ev.EvaluationError("Both private checkpoint kinds must be valid and complete.")
    for key in ("training_batches", "training_processed_tokens", "training_loss_tokens"):
        if (not ev.finite_nonnegative(plan.get(key)) or plan[key] <= 0
                or not float(plan[key]).is_integer() or summary.get(key) != plan[key]):
            raise ev.EvaluationError("Checkpoint training totals disagree with its plan.")
    return path, files, checkpoints, summary, plan


def verified_original(checkpoint_file, protocol, root=ROOT):
    _, files, checkpoints, _, plan = _receipt(checkpoint_file, root)
    legacy = protocol["original_text_receipt"]
    _, _, report = _checked(root, legacy["public_report"])
    reference = report["training"]["development_pass"]
    if (ev.digest(files["plan.json"]) != reference["provenance"]["plan_sha256"]
            or ev.digest(files["summary.json"]) != reference["provenance"]["summary_sha256"]
            or plan.get("phase") != "full" or plan.get("fresh_adapter") is not True
            or plan.get("recipe_sha256") != reference["recipe_sha256"]
            or any(plan.get(key) != reference[key] for key in
                   ("training_batches", "training_processed_tokens", "training_loss_tokens"))
            or ev.digest(files["events.jsonl"]) != legacy["events_sha256"]):
        raise ev.EvaluationError("Arm B differs from the completed original-text experiment receipt.")
    checkpoint_hash = ev.digest(files["checkpoints.json"])
    prior_hashes = []
    for entry in legacy["completed_adapter_evaluation_manifests"]:
        manifest_path, _, prior = _checked(root, entry, under="runs")
        settings = prior.get("settings", {})
        if (prior.get("dry_run_at_creation") is not False
                or settings.get("model") != "thinkingmachines/Inkling"
                or settings.get("transport") != "native_tinker_inkling_adapter"
                or settings.get("adapter_sampler_path") != checkpoints["sampler_path"]):
            raise ev.EvaluationError("Legacy sampling receipts do not identify the original adapter.")
        prior_hashes.append(settings.get("checkpoint_reference_sha256"))
        events = [json.loads(line) for line in _path(root, manifest_path.parent / "events.jsonl", under="runs").read_bytes().splitlines()]
        completed = [event for event in events if event.get("event") == "completed"]
        if (len(completed) != len(prior["case_ids"])
                or {event.get("case_id") for event in completed} != set(prior["case_ids"])
                or any(event.get("answer_complete") is not True for event in completed)
                or any(event.get("event") == "error" for event in events)):
            raise ev.EvaluationError("A legacy adapter evaluation is not recorded as complete.")
    if len(prior_hashes) != 3 or set(prior_hashes) != {checkpoint_hash}:
        raise ev.EvaluationError("The checkpoint bytes differ from the three completed adapter evaluations.")
    _journal(files["events.jsonl"], plan, legacy=True)
    source_identity = {"raw_recipe_sha256": plan["recipe_sha256"],
        "receipt_sha256": {name: ev.digest(data) for name, data in files.items()},
        "load_method": "load_state", "restore_optimizer": False}
    return checkpoints["sampler_path"], checkpoint_hash, source_identity


def verified_checkpoint(arm, checkpoint_file, *, protocol=None, root=ROOT):
    if arm == "A":
        if checkpoint_file is not None:
            raise ev.EvaluationError("The unchanged arm must not load an adapter.")
        return None
    if arm not in STATES or not checkpoint_file:
        raise ev.EvaluationError("This arm requires its completed private checkpoint receipt.")
    protocol = protocol or load_protocol(root)[0]
    if arm == "B":
        return verified_original(checkpoint_file, protocol, root)[:2]
    _, files, checkpoints, summary, plan = _receipt(checkpoint_file, root)
    if (plan.get("phase") != "instruction" or plan.get("arm") != arm or summary.get("arm") != arm
            or summary.get("checkpoint_reference_sha256") != ev.digest(files["checkpoints.json"])
            or plan.get("source_adapter") != summary.get("source_adapter")
            or plan.get("fresh_training_client") is not True
            or plan.get("fresh_adapter") is not (arm == "C")
            or plan.get("optimizer_restored") is not False or summary.get("optimizer_restored") is not False):
        raise ev.EvaluationError("Instruction checkpoint identity, arm, or initialization does not match its receipt.")
    expected = None if arm == "C" else verified_original(protocol["original_text_receipt"]["checkpoint_file"], protocol, root)[2]
    if plan.get("source_adapter") != expected:
        raise ev.EvaluationError("The instruction checkpoint has the wrong original-text parent.")
    _journal(files["events.jsonl"], plan)
    return checkpoints["sampler_path"], ev.digest(files["checkpoints.json"])


def run(config, arm, checkpoint_file=None, *, execute=False, transport=None, root=ROOT):
    if arm not in STATES or config.get("model") != "thinkingmachines/Inkling":
        raise ev.EvaluationError("Choose one of the four Inkling experiment arms.")
    if any(key in config for key in ("adapter_sampler_path", "checkpoint_reference_sha256")):
        raise ev.EvaluationError("Private checkpoint identity must come from the verified receipt.")
    protocol, protocol_hash = load_protocol(root)
    verified_dataset(config, protocol, root)
    identity = verified_checkpoint(arm, checkpoint_file, protocol=protocol, root=root)
    config = comparison.configure(config)
    for key, value in protocol["matched_settings"].items():
        if config.get(key) != value or isinstance(config.get(key), bool) != isinstance(value, bool):
            raise ev.EvaluationError("Sampling settings differ from the frozen four-arm protocol.")
    config.update(experiment_arm=arm, model_state=STATES[arm], instruction_protocol_sha256=protocol_hash)
    if identity is not None:
        config.update(adapter_sampler_path=identity[0], checkpoint_reference_sha256=identity[1],
                      transport="native_tinker_inkling_adapter")
    worker = adapter.worker if identity is not None else comparison.sampling_worker
    bounded = native.BoundedNativeTransport(worker=worker) if transport is None else None
    try:
        result = ev.run(config, execute=execute, resume=False, transport=transport or bounded)
        return {key: value for key, value in result.items() if key in PUBLIC_RESULT_FIELDS}
    finally:
        if bounded is not None:
            bounded.close()


def main(argv=None):
    parser = comparison.parser()
    parser.description = __doc__
    parser.set_defaults(model="thinkingmachines/Inkling", reasoning_effort="medium", dataset=None,
                        comparison_manifest="manifests/comparison-large-models-v1.json",
                        max_output_tokens=8192, max_input_tokens=6000, max_cases=24, timeout_seconds=300)
    parser.add_argument("--arm", required=True, choices=tuple(STATES))
    parser.add_argument("--checkpoint-file")
    args = vars(parser.parse_args(argv))
    execute, resume = args.pop("execute"), args.pop("resume")
    arm, checkpoint = args.pop("arm"), args.pop("checkpoint_file")
    if resume:
        parser.error("No automatic replay of uncertain evaluation requests is supported.")
    try:
        result = run(args, arm, checkpoint, execute=execute)
    except Exception:
        print("Instruction comparison stopped; inspect the private run record before retrying.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
