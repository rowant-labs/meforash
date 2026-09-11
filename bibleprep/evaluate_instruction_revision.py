"""Frozen A/B/E/F evaluation with private diagnostics and no replay or resume."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from bibleprep import evaluate as ev
from bibleprep import evaluate_instruction as previous
from bibleprep import evaluate_instruction_calibration as calibration
from bibleprep import tinker_compare as comparison
from bibleprep import tinker_evaluate as native

ROOT = previous.ROOT
PROTOCOL = "manifests/instruction-target-revision-experiment-v3.json"
TRAINING = "manifests/instruction-target-revision-training-v3.json"
EVALUATION_MANIFEST = "manifests/instruction-target-revision-evaluation-v3.json"
DATASET = "evals/instruction-target-revision-v3.jsonl"
CRITERIA_REVIEW = "manifests/instruction-target-revision-criteria-review-v3.json"
PREFLIGHT = "manifests/instruction-target-revision-preflight-v3.json"
STATES = {"A": "unchanged", "B": "original_text_only",
          "E": "original_text_then_instruction_lr_0.00002",
          "F": "original_text_then_revised_instruction_lr_0.00002"}
RUN_DIRECTORIES = {arm: f"runs/instruction-target-revision-eval-{arm.lower()}-v3" for arm in STATES}
REFERENCE_FILES = {"B": "runs/inkling-original-text-v1/checkpoints.json",
                   "E": "runs/inkling-instruction-e-v2/checkpoints.json"}
F_CHECKPOINT = "runs/inkling-instruction-f-v3/checkpoints.json"
RECEIPT_FILES = {"checkpoints.json", "plan.json", "summary.json", "events.jsonl"}
PRIVATE_FIELDS = calibration.PRIVATE_FIELDS
MATCHED_SETTINGS = dict(calibration.MATCHED_SETTINGS)
BUDGET = {"per_arm_sampling_cap_usd": 1.5, "four_arm_sampling_cap_usd": 6.,
          "new_training_reservation_usd": 3.48945567, "incremental_experiment_cap_usd": 10.}
SEED_DECISION = {"sampling_seed": 20260905, "training_seed": 20260906,
                 "reference": "instruction-calibration-v2",
                 "reason": "Preserve the previous evaluation sampling seed; training seed is separate."}
REQUIRED_SOFTWARE = calibration.REQUIRED_SOFTWARE | {
    "bibleprep/evaluate_instruction_revision.py", "bibleprep/train_instruction_revision.py",
    "bibleprep/train_instruction_calibration.py"}
APPROVED = {"approved", "approved_with_scoring_caveats"}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def verified_criteria_review(protocol, root=ROOT):
    """Verify the complete pre-output supplement; never put it in model prompts."""
    entry = protocol.get("criteria_review", {})
    if entry.get("path") != CRITERIA_REVIEW:
        raise ev.EvaluationError("The mandatory v3 pre-output scoring supplement is missing.")
    _, _, review = previous._checked(root, entry, under="manifests")
    evaluation = protocol["evaluation"]
    cases, fingerprint = ev.load_cases(previous._path(root, evaluation["path"], under="evals"))
    if (fingerprint != evaluation["sha256"] or len(cases) != 30
            or [case["id"] for case in cases] != evaluation["case_ids"]
            or review.get("schema_version") != 3
            or review.get("status") != "frozen_preoutput_criteria_review_complete"
            or review.get("expert_certified") is not False
            or review.get("evaluation") != {key: evaluation[key] for key in ("path", "sha256")}
            or review.get("evaluation_manifest") != protocol["evaluation_manifest"]
            or review.get("counts", {}).get("cases") != 30
            or review["counts"].get("material_prompt_defects") != 0
            or not review.get("global_scoring_supplement")):
        raise ev.EvaluationError("The pre-output review does not bind the full frozen evaluation.")
    _, _, training = previous._checked(root, protocol["training_manifest"], under="manifests")
    if review.get("preparation_manifest") != training.get("preparation"):
        raise ev.EvaluationError("The scoring review and training data preparation disagree.")
    previous._checked(root, review["preparation_manifest"], under="manifests")
    previous._checked(root, review["dataset_freeze"], under="runs")
    actual = {case["id"]: ev.digest(_canonical(case)) for case in cases}
    checked = {}
    for item in review.get("cases", []):
        key = item.get("id")
        if (key in checked or key not in actual or item.get("case_sha256") != actual[key]
                or item.get("status") not in APPROVED or not item.get("scoring_caveats")):
            raise ev.EvaluationError("A pre-output case review is missing, duplicated, changed, or unapproved.")
        checked[key] = item
    if set(checked) != set(actual):
        raise ev.EvaluationError("All thirty cases need their frozen pre-output review.")
    receipt_ids = set()
    receipts = review.get("review_receipts", [])
    if len(receipts) != 2:
        raise ev.EvaluationError("Both separate pre-output review receipts are required.")
    for entry in receipts:
        _, _, receipt = previous._checked(root, entry, under="runs")
        if (receipt.get("status") not in APPROVED or receipt.get("expert_certified") is not False
                or receipt.get("reviewer") != entry.get("reviewer")
                or receipt.get("evaluation_sha256") != evaluation["sha256"]
                or len(receipt.get("cases", [])) != entry.get("cases")):
            raise ev.EvaluationError("A separate source-review receipt is invalid.")
        for case in receipt["cases"]:
            key = case.get("case_id", case.get("id"))
            caveats = case.get("scoring_caveats", [case.get("notes")])
            if (key in receipt_ids or key not in checked or case.get("case_sha256") != actual[key]
                    or case.get("status") not in APPROVED
                    or checked[key]["scoring_caveats"] != caveats
                    or checked[key].get("source_urls") != case.get("source_urls")):
                raise ev.EvaluationError("The public scoring supplement differs from its separate review.")
            receipt_ids.add(key)
    if receipt_ids != set(actual):
        raise ev.EvaluationError("Separate reviewers must cover all thirty cases exactly once.")
    return review


def load_protocol(root=ROOT):
    _, data, protocol = previous._read(root, PROTOCOL, under="manifests")
    if (protocol.get("schema_version") != 3
            or protocol.get("status") != "frozen_before_training_and_sampling"
            or protocol.get("experiment_id") != "instruction-target-revision-v3"
            or protocol.get("arms") != STATES or protocol.get("matched_settings") != MATCHED_SETTINGS
            or protocol.get("budget") != BUDGET or protocol.get("sampling_seed_decision") != SEED_DECISION
            or protocol.get("run_directories") != RUN_DIRECTORIES
            or protocol.get("planned_f_checkpoint_file") != F_CHECKPOINT
            or protocol.get("evaluation_manifest", {}).get("path") != EVALUATION_MANIFEST
            or protocol.get("training_manifest", {}).get("path") != TRAINING
            or protocol.get("preflight", {}).get("path") != PREFLIGHT
            or protocol.get("evaluation", {}).get("path") != DATASET
            or protocol.get("prior_protocol", {}).get("path") != calibration.PROTOCOL):
        raise ev.EvaluationError("The target-revision comparison is not frozen to its authorized settings.")
    _, _, freeze = previous._checked(root, protocol["evaluation_manifest"], under="manifests")
    _, _, training = previous._checked(root, protocol["training_manifest"], under="manifests")
    _, _, prior = previous._checked(root, protocol["prior_protocol"], under="manifests")
    previous._checked(root, protocol["prior_aggregate"], under="reports")
    _, _, preflight = previous._checked(root, protocol["preflight"], under="manifests")
    pricing = preflight.get("pricing", {})
    availability = preflight.get("provider_checkpoint_check", {})
    if (preflight.get("schema_version") != 3
            or preflight.get("status") != "verified_before_paid_v3_execution"
            or preflight.get("model") != MATCHED_SETTINGS["model"]
            or pricing.get("input_usd_per_million") != 1.87
            or pricing.get("output_usd_per_million") != 4.68
            or pricing.get("training_usd_per_million") != 5.61
            or pricing.get("rates_rechecked_before_run") is not True
            or availability.get("read_only") is not True
            or availability.get("verified_arms") != ["B", "E"]
            or any(availability.get(key) is not True for key in (
                "training_and_sampler_checkpoints_present", "all_checked_checkpoints_unexpired",
                "all_checked_checkpoints_private", "B_base_model_rank_and_components_match"))):
        raise ev.EvaluationError("The current pricing and retained-checkpoint preflight is invalid.")
    private_check = previous._path(root, availability["path"], under="runs").read_bytes()
    if ev.digest(private_check) != availability.get("sha256"):
        raise ev.EvaluationError("The private checkpoint-availability preflight receipt changed.")
    if (freeze.get("schema_version") != 3
            or freeze.get("status") != "frozen_before_training_and_sampling"
            or freeze.get("dataset") != protocol["evaluation"]
            or protocol["evaluation"].get("cases") != 30
            or training.get("schema_version") != 3 or training.get("status") != "frozen_training_recipe"
            or training.get("experiment_id") != "instruction-target-revision-v3"
            or training.get("arm") != "F" or training.get("parent_arm") != "B"
            or training.get("planned_nano_usd") != 3489455670
            or prior != calibration.load_protocol(root)[0]
            or protocol.get("system_prompt_sha256") != ev.digest(ev.SYSTEM_PROMPT.encode())):
        raise ev.EvaluationError("Evaluation, training, or prior comparison identities disagree.")
    if set(protocol.get("reference_checkpoints", {})) != set(REFERENCE_FILES):
        raise ev.EvaluationError("Both retained reference checkpoint identities are required.")
    for arm, location in REFERENCE_FILES.items():
        reference = protocol["reference_checkpoints"][arm]
        if (reference.get("checkpoint_file") != location
                or set(reference.get("receipt_sha256", {})) != RECEIPT_FILES
                or any(not previous.SHA.fullmatch(value) for value in reference["receipt_sha256"].values())):
            raise ev.EvaluationError("Every retained checkpoint needs its four frozen receipt hashes.")
    code = protocol.get("software_sha256", {})
    if not REQUIRED_SOFTWARE <= set(code):
        raise ev.EvaluationError("Frozen evaluator, diagnostics, and checkpoint verifier identities are required.")
    for name, expected in code.items():
        if ev.digest(previous._path(root, name).read_bytes()) != expected:
            raise ev.EvaluationError("Revision software changed after the freeze.")
    verified_criteria_review(protocol, root)
    return protocol, ev.digest(data)


def verified_dataset(config, protocol, root=ROOT):
    return calibration.verified_dataset(config, protocol, root)


def verified_checkpoint(arm, checkpoint_file, protocol, root=ROOT):
    if arm == "A":
        if checkpoint_file is not None:
            raise ev.EvaluationError("The unchanged control cannot load an adapter.")
        return None
    if arm not in STATES or not checkpoint_file:
        raise ev.EvaluationError("This arm requires its completed private checkpoint receipt.")
    path = previous._path(root, checkpoint_file, under="runs")
    expected = F_CHECKPOINT if arm == "F" else REFERENCE_FILES[arm]
    if str(path.relative_to(Path(root).resolve())) != expected:
        raise ev.EvaluationError("Use the frozen checkpoint location for the selected arm.")
    if arm == "F":
        from bibleprep.train_instruction_revision import verify_completed_checkpoint
        return verify_completed_checkpoint(root, path)
    reference = protocol["reference_checkpoints"][arm]
    if reference.get("checkpoint_file") != expected or set(reference.get("receipt_sha256", {})) != RECEIPT_FILES:
        raise ev.EvaluationError("The retained reference checkpoint receipt is incomplete.")
    for name, expected_hash in reference["receipt_sha256"].items():
        if ev.digest(previous._path(root, path.parent / name, under="runs").read_bytes()) != expected_hash:
            raise ev.EvaluationError("A retained reference checkpoint receipt changed.")
    if arm == "E":
        from bibleprep.train_instruction_calibration import verify_completed_checkpoint
        return verify_completed_checkpoint(root, path)
    return previous.verified_checkpoint("B", path, protocol=previous.load_protocol(root)[0], root=root)


def _run_directory(value, arm, root):
    root = Path(root).resolve()
    path = Path(value or RUN_DIRECTORIES[arm])
    path = path if path.is_absolute() else root / path
    if path != root / RUN_DIRECTORIES[arm] or path.is_symlink() or path.parent.is_symlink():
        raise ev.EvaluationError("Use the single fixed run directory for this arm; alternate-path replay is disabled.")
    if path.exists():
        raise ev.EvaluationError("This arm already has a run directory; no retry or resume is enabled.")
    return path


def run(config, arm, checkpoint_file=None, *, execute=False, transport=None, root=ROOT):
    if arm not in STATES or PRIVATE_FIELDS & set(config) or config.get("resume"):
        raise ev.EvaluationError("Choose a frozen arm without private identity overrides or resume.")
    protocol, fingerprint = load_protocol(root)
    _, cases = verified_dataset(config, protocol, root)
    identity = verified_checkpoint(arm, checkpoint_file, protocol, root)
    directory = _run_directory(config.get("run_dir"), arm, root)
    configured = comparison.configure(config)
    for key, value in MATCHED_SETTINGS.items():
        if configured.get(key) != value or isinstance(configured.get(key), bool) != isinstance(value, bool):
            raise ev.EvaluationError("A sampling setting differs from the target-revision freeze.")
    reservation = ev.estimated_cost(configured["max_input_tokens"], configured["max_output_tokens"], configured)
    budget = configured.get("budget_usd")
    if (not ev.finite_nonnegative(budget) or not reservation * 30 <= budget <= BUDGET["per_arm_sampling_cap_usd"]):
        raise ev.EvaluationError("The arm budget must cover all thirty requests within the frozen sampling cap.")
    configured.update(run_dir=str(directory), experiment_arm=arm, model_state=STATES[arm],
                      revision_protocol_sha256=fingerprint,
                      criteria_review_sha256=protocol["criteria_review"]["sha256"],
                      diagnostic_version="native-diagnostics-v1")
    if identity is not None:
        configured.update(adapter_sampler_path=identity[0], checkpoint_reference_sha256=identity[1],
                          checkpoint_reference_file=str(previous._path(root, checkpoint_file, under="runs")),
                          transport="native_tinker_inkling_adapter_diagnostics_v1")
    else:
        configured["transport"] = "native_tinker_inkling_base_diagnostics_v1"
    ev.validate_config(configured, execute)
    if any(ev.estimate_input_tokens(ev.build_payload(case, configured)) > configured["max_input_tokens"] for case in cases):
        raise ev.EvaluationError("A prompt exceeds the frozen input limit; no request was submitted.")
    if not execute:
        return {"mode": "dry_run", "selected_cases": 30, "completed_cases": 0, "pending_cases": 30,
                "accounted_cost_usd": 0., "per_request_reservation_usd": reservation,
                "remaining_worst_case_usd": reservation * 30, "stop_reason": "dry_run",
                "historical_correctness": "not_automatically_scored"}
    bounded = None
    old_umask = os.umask(0o077)
    try:
        directory.parent.mkdir(parents=True, exist_ok=True)
        # Atomic allocation fixes one attempt per arm even across concurrent callers.
        directory.mkdir(mode=0o700, exist_ok=False)
        if transport is None:
            from bibleprep.native_diagnostics_v1 import sampling_worker
            bounded = native.BoundedNativeTransport(worker=sampling_worker)
        result = ev.run(configured, execute=True, resume=False, transport=transport or bounded)
        return {key: value for key, value in result.items() if key in previous.PUBLIC_RESULT_FIELDS}
    finally:
        if bounded is not None:
            bounded.close()
        os.umask(old_umask)


def main(argv=None):
    parser = comparison.parser()
    parser.description = __doc__
    parser.set_defaults(model="thinkingmachines/Inkling", reasoning_effort="medium",
                        dataset=str(ROOT / DATASET), comparison_manifest=MATCHED_SETTINGS["comparison_manifest"],
                        max_output_tokens=8192, max_input_tokens=6000, max_cases=30,
                        timeout_seconds=300, budget_usd=1.5, run_dir=None,
                        input_price_per_million=1.87, output_price_per_million=4.68, seed=20260905)
    parser.add_argument("--arm", choices=tuple(STATES), required=True)
    parser.add_argument("--checkpoint-file")
    args = vars(parser.parse_args(argv))
    execute, resume = args.pop("execute"), args.pop("resume")
    arm, checkpoint = args.pop("arm"), args.pop("checkpoint_file")
    if resume:
        parser.error("No replay or resume of this experiment is supported.")
    try:
        result = run(args, arm, checkpoint, execute=execute)
    except Exception:
        print("Revision evaluation stopped; preserve private receipts. No automatic retry is enabled.", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
