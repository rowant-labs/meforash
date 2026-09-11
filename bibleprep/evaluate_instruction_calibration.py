"""Frozen, bounded A/B/D/E sampling with private native output diagnostics."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from bibleprep import evaluate as ev
from bibleprep import evaluate_instruction as previous
from bibleprep import tinker_compare as comparison
from bibleprep import tinker_evaluate as native

ROOT = previous.ROOT
PROTOCOL = "manifests/instruction-calibration-experiment-v2.json"
STATES = {"A": "unchanged", "B": "original_text_only",
          "D": "original_text_then_instruction_lr_0.0001",
          "E": "original_text_then_instruction_lr_0.00002"}
PRIVATE_FIELDS = {"adapter_sampler_path", "checkpoint_reference_sha256", "checkpoint_reference_file"}
MATCHED_SETTINGS = {"model": "thinkingmachines/Inkling", "reasoning_effort": "medium",
    "thinking_effort_numeric": .7, "temperature": 0., "seed": 20260905,
    "max_output_tokens": 8192, "max_input_tokens": 6000, "timeout_seconds": 300,
    "evidence_mode": "provided", "api_key_env": "TINKER_API_KEY", "base_url": native.TINKER_URL,
    "comparison_manifest": "manifests/comparison-large-models-v1.json",
    "output_limit_field": "max_completion_tokens", "input_price_per_million": 1.87,
    "output_price_per_million": 4.68}
BUDGET = {"per_arm_sampling_cap_usd": 1.5, "four_arm_sampling_cap_usd": 6.,
          "new_training_reservation_usd": 3.48149508, "incremental_experiment_cap_usd": 10.}
REQUIRED_SOFTWARE = {"bibleprep/evaluate_instruction_calibration.py", "bibleprep/native_diagnostics_v1.py",
    "bibleprep/evaluate.py", "bibleprep/evaluate_instruction.py", "bibleprep/tinker_compare.py",
    "bibleprep/tinker_evaluate.py", "bibleprep/evaluate_adapter.py", "bibleprep/environment.py"}


def load_protocol(root=ROOT):
    _, data, protocol = previous._read(root, PROTOCOL, under="manifests")
    if (protocol.get("schema_version") != 2
            or protocol.get("status") != "frozen_before_training_and_sampling"
            or protocol.get("experiment_id") != "instruction-calibration-v2"
            or protocol.get("arms") != STATES
            or protocol.get("matched_settings") != MATCHED_SETTINGS or protocol.get("budget") != BUDGET):
        raise ev.EvaluationError("The calibration comparison is not frozen.")
    _, _, freeze = previous._checked(root, protocol["evaluation_manifest"], under="manifests")
    _, _, training = previous._checked(root, protocol["training_manifest"], under="manifests")
    _, _, old = previous._checked(root, protocol["prior_protocol"], under="manifests")
    previous._checked(root, protocol["prior_aggregate"], under="reports")
    if (freeze.get("schema_version") != 2
            or freeze.get("status") != "frozen_before_training_and_sampling"
            or freeze.get("dataset") != protocol["evaluation"]
            or protocol["evaluation"].get("cases") != 30
            or old != previous.load_protocol(root)[0]
            or protocol.get("system_prompt_sha256") != ev.digest(ev.SYSTEM_PROMPT.encode())):
        raise ev.EvaluationError("Evaluation, training, or prior comparison freeze differs.")
    code = protocol.get("software_sha256", {})
    if not REQUIRED_SOFTWARE <= set(code):
        raise ev.EvaluationError("Frozen evaluator and diagnostic code identities are required.")
    for name, expected in code.items():
        if ev.digest(previous._path(root, name).read_bytes()) != expected:
            raise ev.EvaluationError("Calibration software changed after the freeze.")
    return protocol, ev.digest(data)


def verified_dataset(config, protocol, root=ROOT):
    if not config.get("dataset"):
        raise ev.EvaluationError("A frozen calibration dataset is required.")
    path = previous._path(root, config["dataset"], under="evals")
    entry = protocol["evaluation"]
    cases, digest = ev.load_cases(path)
    if (str(path.relative_to(Path(root).resolve())) != entry["path"]
            or digest != entry["sha256"] or len(cases) != 30
            or config.get("max_cases") != 30
            or [case["id"] for case in cases] != entry["case_ids"]):
        raise ev.EvaluationError("Only the entire unchanged 30-case evaluation is enabled.")
    return path, cases


def verified_checkpoint(arm, checkpoint_file, protocol, root=ROOT):
    if arm == "A":
        if checkpoint_file is not None:
            raise ev.EvaluationError("The unchanged control cannot load an adapter.")
        return None
    if arm not in STATES or not checkpoint_file:
        raise ev.EvaluationError("This condition requires its completed checkpoint receipt.")
    if arm == "E":
        from bibleprep.train_instruction_calibration import verify_completed_checkpoint
        return verify_completed_checkpoint(root, checkpoint_file)
    reference = protocol["reference_checkpoints"][arm]
    if set(reference.get("receipt_sha256", {})) != {"checkpoints.json", "plan.json", "summary.json", "events.jsonl"}:
        raise ev.EvaluationError("Every preserved reference receipt is required.")
    path = previous._path(root, checkpoint_file, under="runs")
    if str(path.relative_to(Path(root).resolve())) != reference["checkpoint_file"]:
        raise ev.EvaluationError("A reference arm must use the preserved checkpoint location.")
    for name, expected in reference["receipt_sha256"].items():
        if ev.digest(previous._path(root, path.parent / name, under="runs").read_bytes()) != expected:
            raise ev.EvaluationError("A reference checkpoint receipt changed.")
    old = previous.load_protocol(root)[0]
    return previous.verified_checkpoint(arm, path, protocol=old, root=root)


def run(config, arm, checkpoint_file=None, *, execute=False, transport=None, root=ROOT):
    if arm not in STATES or PRIVATE_FIELDS & set(config):
        raise ev.EvaluationError("Choose a frozen condition and obtain private identity from its receipt.")
    protocol, fingerprint = load_protocol(root)
    verified_dataset(config, protocol, root)
    identity = verified_checkpoint(arm, checkpoint_file, protocol, root)
    configured = comparison.configure(config)
    for key, value in protocol["matched_settings"].items():
        if configured.get(key) != value or isinstance(configured.get(key), bool) != isinstance(value, bool):
            raise ev.EvaluationError("A sampling setting differs from the calibration freeze.")
    if (not ev.finite_nonnegative(configured.get("budget_usd"))
            or not 0 < configured["budget_usd"] <= protocol["budget"]["per_arm_sampling_cap_usd"]):
        raise ev.EvaluationError("The arm budget must remain within its frozen limit.")
    configured.update(experiment_arm=arm, model_state=STATES[arm],
                      calibration_protocol_sha256=fingerprint, diagnostic_version="native-diagnostics-v1")
    if identity is not None:
        configured.update(adapter_sampler_path=identity[0], checkpoint_reference_sha256=identity[1],
                          checkpoint_reference_file=str(previous._path(root, checkpoint_file, under="runs")),
                          transport="native_tinker_inkling_adapter_diagnostics_v1")
    else:
        configured["transport"] = "native_tinker_inkling_base_diagnostics_v1"
    bounded = None
    try:
        if transport is None and execute:
            from bibleprep.native_diagnostics_v1 import sampling_worker
            bounded = native.BoundedNativeTransport(worker=sampling_worker)
        result = ev.run(configured, execute=execute, resume=False, transport=transport or bounded)
        return {key: value for key, value in result.items() if key in previous.PUBLIC_RESULT_FIELDS}
    finally:
        if bounded is not None:
            bounded.close()


def main(argv=None):
    parser = comparison.parser()
    parser.description = __doc__
    parser.set_defaults(model="thinkingmachines/Inkling", reasoning_effort="medium",
                        dataset=str(ROOT / "evals/instruction-calibration-v2.jsonl"),
                        comparison_manifest="manifests/comparison-large-models-v1.json",
                        max_output_tokens=8192, max_input_tokens=6000, max_cases=30,
                        timeout_seconds=300, budget_usd=1.50,
                        input_price_per_million=1.87, output_price_per_million=4.68)
    parser.add_argument("--arm", choices=tuple(STATES), required=True)
    parser.add_argument("--checkpoint-file")
    args = vars(parser.parse_args(argv))
    execute, resume = args.pop("execute"), args.pop("resume")
    arm, checkpoint = args.pop("arm"), args.pop("checkpoint_file")
    if resume:
        parser.error("No automatic replay of uncertain requests is supported.")
    try:
        result = run(args, arm, checkpoint, execute=execute)
    except Exception:
        print("Calibration evaluation stopped; inspect private records before retrying.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
