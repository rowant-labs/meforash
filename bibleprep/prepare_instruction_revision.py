"""Prepare the approved v3 instruction revision offline; never open evaluation cases.

The original preparation is an immutable parent. Only the fourteen reviewed
training prompts/answers may change, and all other source and split data stay
identical. Running with --verify rebuilds in memory and checks existing bytes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path

from bibleprep import prepare_instruction as p

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIRECTORY = "data/prepared/instruction-v3"
PREPARATION_MANIFEST = "manifests/preparation-instruction-v3.json"
ORIGINAL_PREPARATION = "manifests/preparation-instruction-v1.json"
ORIGINAL_DATASET = "runs/instruction-v1-prep/reviewed/all.jsonl"
REVISED_DATASET = "runs/instruction-v3-prep/reviewed/all.jsonl"
ORIGINAL_PREPARATION_SHA256 = "b851caf978f50c63ef5f2cba856e74f46ab751090ee47401100fcf9cff8b34cc"
ORIGINAL_DATASET_SHA256 = "2bb0e9d842564267173bf8de1c8481fa03996a960a3719eabb633281c963a567"
VALIDATION_SHA256 = "695f578c1bd8e068d7b5ad1903f9860c8d1c030c176335e0902d18ef3ec33f00"
CHANGED_IDS = ("IA004", "IA006", "IA010", "IA020", "IG002", "IG035",
               "IH004", "IH006", "IH013", "IH021", "IH028", "IH031", "IH037", "IH040")
GROUP_IDS = {name: tuple(cid for cid in CHANGED_IDS if cid.startswith(prefix))
             for name, prefix in (("hebrew", "IH"), ("aramaic", "IA"), ("greek", "IG"))}
AUTHORED_FIELDS = {"prompt", "answer", "author", "support_notes"}
CODE_FILES = ("bibleprep/prepare_instruction_revision.py", *p.CODE_FILES)
SETTINGS = {"model": p.MODEL, "thinking_effort_numeric": 0.7,
            "maximum_input_tokens": 8192, "preserve_original_order": True,
            "preserve_original_split": True}


def require(value, message):
    if not value:
        raise ValueError(message)


def exact_keys(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys), f"Invalid {label} fields.")


def allowed_keys(value, required, optional, label):
    require(isinstance(value, dict) and set(required) <= set(value)
            and set(value) <= set(required) | set(optional), f"Invalid {label} fields.")


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON key.")
        result[key] = value
    return result


def decode(data):
    return json.loads(data, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON value.")))


def read_rows(path):
    data = path.read_bytes()
    require(bool(data) and data.endswith(b"\n"), "JSONL must end with a complete newline.")
    lines = data.splitlines(keepends=True)
    require(all(line.strip() for line in lines), "Blank JSONL rows are not accepted.")
    rows = [decode(line) for line in lines]
    require(all(isinstance(row, dict) for row in rows), "Invalid JSONL row.")
    return rows, lines


def artifact(root, entry, *, under, exact_path=None):
    exact_keys(entry, ("path", "sha256"), "artifact reference")
    require(isinstance(entry["sha256"], str) and p.SHA.fullmatch(entry["sha256"]), "Invalid artifact hash.")
    require(exact_path is None or entry["path"] == exact_path, "Artifact path differs from the frozen experiment.")
    path = p.relative_path(root, entry["path"], under=under)
    require(p.digest(path.read_bytes()) == entry["sha256"], "Artifact checksum changed.")
    return path


def load_plan(root, plan_path):
    path = p.relative_path(root, plan_path, under="manifests")
    plan = decode(path.read_bytes())
    exact_keys(plan, ("schema_version", "status", "revision_id", "original_preparation", "original_dataset",
                      "revised_dataset", "changed_training_ids", "unchanged_validation_sha256",
                      "evaluation_exclusion", "review_groups", "settings"), "revision plan")
    require(plan["schema_version"] == 3 and plan["status"] == "frozen_before_preparation"
            and plan["revision_id"] == "instruction-revision-v3", "Revision plan is not frozen.")
    require(plan["settings"] == SETTINGS, "Native settings or preservation policy changed.")
    require(plan["changed_training_ids"] == list(CHANGED_IDS), "The fourteen selected training IDs changed.")
    require(plan["original_dataset"]["sha256"] == ORIGINAL_DATASET_SHA256
            and plan["original_preparation"]["sha256"] == ORIGINAL_PREPARATION_SHA256
            and plan["unchanged_validation_sha256"] == VALIDATION_SHA256,
            "Original experiment anchor changed.")
    return plan, {"path": plan_path, "sha256": p.digest(path.read_bytes())}


def validate_revisions(root, plan, old_examples, old_lines, examples, lines, train_ids):
    """Bind every changed full row to the author draft and separate source receipt."""
    require(len(examples) == len(old_examples) == 120, "Exactly 120 original IDs are required.")
    ids = [row["id"] for row in old_examples]
    require(len(set(ids)) == 120 and [row["id"] for row in examples] == ids, "Full dataset IDs or order changed.")
    old, new = dict(zip(ids, old_examples)), dict(zip(ids, examples))
    require(set(CHANGED_IDS) <= set(train_ids), "A selected change moved into validation.")
    require([cid for cid in ids if cid in CHANGED_IDS] == list(CHANGED_IDS), "Selected ID order differs from parent.")
    for before, after, before_bytes, after_bytes in zip(old_examples, examples, old_lines, lines):
        cid = before["id"]
        if cid not in CHANGED_IDS:
            require(before_bytes == after_bytes, "An unchanged full row differs byte-for-byte.")
            continue
        require(set(before) == set(after), "Revised row schema changed.")
        fixed = set(before) - AUTHORED_FIELDS - p.REVIEW_FIELDS
        require(all(before[k] == after[k] for k in fixed), "Source, evidence, ID or split metadata changed.")
        require(before["prompt"] != after["prompt"] and before["answer"] != after["answer"],
                "Selected composition changes must replace both prompt and answer.")
    groups = plan["review_groups"]
    require(isinstance(groups, list) and len(groups) == 3, "Require exactly three independent review groups.")
    seen, names, reviewers, receipts = set(), set(), set(), []
    for group in groups:
        exact_keys(group, ("name", "ids", "revision_drafts", "receipt"), "review group")
        name = group["name"]
        require(name in GROUP_IDS and name not in names and group["ids"] == list(GROUP_IDS[name]), "Review group IDs changed.")
        names.add(name)
        drafts_path = artifact(root, group["revision_drafts"], under="runs/instruction-v3-prep")
        receipt_path = artifact(root, group["receipt"], under="runs/instruction-v3-prep/reviews",
                                exact_path=f"runs/instruction-v3-prep/reviews/{name}.json")
        drafts, _ = read_rows(drafts_path)
        receipt = decode(receipt_path.read_bytes())
        allowed_keys(receipt, ("status", "reviewer", "revisions_file_sha256", "approvals", "expert_certified", "limitations"),
                     ("schema_version", "review_basis"), "source receipt")
        require("schema_version" not in receipt or type(receipt["schema_version"]) is int
                and receipt["schema_version"] == 1, "Unsupported source receipt version.")
        require("review_basis" not in receipt or isinstance(receipt["review_basis"], str)
                and receipt["review_basis"].strip(), "Invalid source review basis.")
        require(receipt["status"] == "approved" and receipt["expert_certified"] is False
                and receipt["revisions_file_sha256"] == group["revision_drafts"]["sha256"], "Approval is stale or incomplete.")
        reviewer = receipt["reviewer"]
        require(isinstance(reviewer, str) and reviewer.strip() and reviewer not in reviewers, "Require distinct source reviewers.")
        reviewers.add(reviewer)
        approvals = receipt["approvals"]
        require(isinstance(approvals, list) and [row["id"] for row in drafts] == group["ids"]
                and [row["id"] for row in approvals] == group["ids"], "Draft or approval coverage/order changed.")
        for draft, approval in zip(drafts, approvals):
            allowed_keys(draft, ("id", "prompt", "answer", "author", "support_notes", "coverage", "rationale", "source_urls",
                                 "old_prompt_sha256", "old_answer_sha256", "status"),
                         ("new_prompt_sha256", "new_answer_sha256"), "author draft")
            exact_keys(approval, ("id", "status", "content_sha256", "source_urls", "coverage_complete", "notes"), "approval")
            cid = draft["id"]
            require(cid not in seen and cid == approval["id"], "Duplicate or mismatched approval.")
            seen.add(cid)
            before, candidate = old[cid], new[cid]
            require(draft["status"] == "authored_pending_review" and approval["status"] == "approved"
                    and approval["coverage_complete"] is True, "Independent coverage approval is required.")
            require(draft["old_prompt_sha256"] == p.digest(before["prompt"].encode())
                    and draft["old_answer_sha256"] == p.digest(before["answer"].encode()), "Draft parent target hashes changed.")
            require(all(candidate[k] == draft[k] for k in AUTHORED_FIELDS), "Full candidate differs from reviewed author draft.")
            for field in ("prompt", "answer"):
                key = f"new_{field}_sha256"
                require(key not in draft or draft[key] == p.digest(draft[field].encode()), "Draft new-content hash changed.")
            require(candidate["author"] != reviewer and candidate["reviewer"] == reviewer
                    and candidate["review_status"] == "ai_source_checked", "Self-review or mismatched reviewer.")
            content_sha = p.content_hash(candidate)
            require(content_sha == approval["content_sha256"] == candidate["reviewed_content_sha256"], "Reviewed content hash changed.")
            require(candidate["review_sources"] == approval["source_urls"] and approval["source_urls"]
                    and all(isinstance(u, str) and u.startswith("https://") for u in approval["source_urls"]),
                    "Source approval references differ.")
        receipts.append(group)
    require(seen == set(CHANGED_IDS), "Not every selected change has an independent approval.")
    return receipts


def _build(root, plan_path):
    root = Path(root)
    plan, plan_reference = load_plan(root, plan_path)
    old_manifest_path = artifact(root, plan["original_preparation"], under="manifests", exact_path=ORIGINAL_PREPARATION)
    old_manifest = decode(old_manifest_path.read_bytes())
    old_prepared = p.verify_prepared(root, old_manifest)
    old_path = artifact(root, plan["original_dataset"], under="runs", exact_path=ORIGINAL_DATASET)
    require(old_manifest["reviewed_dataset"]["path"] == ORIGINAL_DATASET
            and old_manifest["reviewed_dataset"]["sha256"] == ORIGINAL_DATASET_SHA256, "Parent preparation uses another dataset.")
    new_path = artifact(root, plan["revised_dataset"], under="runs/instruction-v3-prep", exact_path=REVISED_DATASET)
    old_examples, old_lines = read_rows(old_path)
    examples, lines = read_rows(new_path)
    old_bytes, split_ids = {}, {}
    for label in ("train", "validation"):
        entry = old_manifest["artifacts"][label]
        path = p.relative_path(root, entry["path"], under=p.ARTIFACT_DIRECTORY)
        old_bytes[label] = path.read_bytes()
        split_ids[label] = [row["id"] for row in old_prepared[label]]
    require(len(split_ids["train"]) == 104 and len(split_ids["validation"]) == 16
            and p.digest(old_bytes["validation"]) == VALIDATION_SHA256, "Parent validation or split changed.")
    reviews = validate_revisions(root, plan, old_examples, old_lines, examples, lines, split_ids["train"])
    artifact(root, plan["evaluation_exclusion"], under="manifests")
    # This helper accepts only an allowlisted inventory of hashes/chapter keys.
    # It never follows an evaluation dataset path or reads questions/criteria.
    excluded, exclusion = p.load_exclusion(root, plan["evaluation_exclusion"]["path"])
    require(exclusion["sha256"] == plan["evaluation_exclusion"]["sha256"], "Exclusion inventory changed.")
    records, identities = p.load_sources(root)
    require(identities == old_manifest["sources"], "Source identity changed from original preparation.")
    evidence = {e["id"]: p.validate_example(e, records, identities, excluded) for e in examples}
    by_id = {e["id"]: e for e in examples}
    renderer = p.InstructionRenderer()
    require(renderer.identity == old_manifest["tokenizer"]
            and renderer.identity["runtime_packages"] == old_manifest["runtime_versions"], "Original tokenizer/runtime changed.")
    prepared, artifacts, result = {}, {}, {}
    for label, ids in split_ids.items():
        rows = []
        for cid in ids:
            e = by_id[cid]
            row = renderer.render(e["prompt"], e["answer"], evidence[cid], e.get("evidence_mode", "provided"))
            p.validate_sequence(row, SETTINGS["maximum_input_tokens"])
            row.update({k: e[k] for k in ("id", "language", "category", "chapter_keys", "source_refs")})
            row.update(answer_sha256=p.digest(e["answer"].encode()), reviewed_content_sha256=e["reviewed_content_sha256"],
                       evidence_sha256=p.digest(evidence[cid].encode()), evidence_mode=e.get("evidence_mode", "provided"))
            rows.append(row)
        encoded = [p.json_bytes(row) + b"\n" for row in rows]
        prior = old_bytes[label].splitlines(keepends=True)
        require(len(prior) == len(encoded), "Native split length changed.")
        require(all(new == old for cid, new, old in zip(ids, encoded, prior) if cid not in CHANGED_IDS),
                "An unchanged native training/validation row differs byte-for-byte.")
        data = b"".join(encoded)
        if label == "validation":
            require(data == old_bytes[label] and p.digest(data) == VALIDATION_SHA256, "Validation bytes changed.")
        prepared[label], result[label] = data, rows
        artifacts[label] = {"path": f"{ARTIFACT_DIRECTORY}/{label}.jsonl", "sha256": p.digest(data), "sequences": len(rows),
                            "processed_tokens": sum(r["processed_token_count"] for r in rows),
                            "loss_tokens": sum(r["loss_token_count"] for r in rows)}
    require(p.EFFORT == SETTINGS["thinking_effort_numeric"] and p.MODEL == SETTINGS["model"], "Renderer settings changed.")
    report = {"schema_version": 3, "status": "prepared_not_trained", "objective": "reviewed_english_instruction_sft",
              "revision_id": "instruction-revision-v3", "review_status": "ai_source_checked", "expert_certified": False,
              "model": p.MODEL, "thinking_effort_numeric": p.EFFORT, "maximum_input_tokens": SETTINGS["maximum_input_tokens"],
              "native_start_token_id": 200002, "native_end_token_id": 200006,
              "revision_plan": plan_reference, "original_preparation": plan["original_preparation"],
              "original_dataset": plan["original_dataset"], "review_groups": reviews,
              "reviewed_dataset": {**plan["revised_dataset"], "examples": 120},
              "changed_training_ids": list(CHANGED_IDS), "unchanged_full_rows": 106, "unchanged_training_rows": 90,
              "validation_bytes_unchanged": True, "tokenizer": renderer.identity,
              "runtime_versions": renderer.identity["runtime_packages"], "sources": identities,
              "system_prompt_sha256": p.digest(p.SYSTEM_PROMPT.encode()),
              "preparation_code_sha256": {name: p.digest((root / name).read_bytes()) for name in CODE_FILES},
              "evaluation_exclusion": exclusion, "artifacts": artifacts, "split": old_manifest["split"],
              "by_language": {label: dict(Counter(row["language"] for row in rows)) for label, rows in result.items()},
              "framing": old_manifest["framing"], "provider_references": p.REFERENCES,
              "limitations": ["AI source review is not expert certification. No model API was called.",
                              "This composition revision does not establish the cause of earlier omissions.",
                              "All validation bytes and unchanged training rows are preserved; no new evaluation cases were read.",
                              "Final-only native targets and medium effort are unchanged; base prior exposure remains unknown."]}
    return report, prepared, result


def build(plan_path, *, root=ROOT):
    """Deterministically rebuild all prospective output bytes in memory only."""
    try:
        return _build(Path(root), plan_path)
    except (KeyError, TypeError, OSError, AttributeError) as exc:
        raise ValueError("Required revision artifact or schema is missing or invalid.") from exc


def _write_new(path, data, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def prepare(plan_path, *, root=ROOT):
    root = Path(root)
    output = p.relative_path(root, ARTIFACT_DIRECTORY, under="data/prepared")
    manifest_path = p.relative_path(root, PREPARATION_MANIFEST, under="manifests")
    require(not output.exists() and not output.is_symlink() and not manifest_path.exists() and not manifest_path.is_symlink(),
            "Preparation outputs already exist; refusing overwrite.")
    report, prepared, _ = build(plan_path, root=root)
    output.mkdir(parents=True, mode=0o700)
    for label, data in prepared.items():
        _write_new(output / f"{label}.jsonl", data, 0o600)
    _write_new(output / "summary.json", p.json_bytes(report) + b"\n", 0o600)
    _write_new(manifest_path, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode(), 0o644)
    return report


def verify_prepared(root, manifest):
    """Re-render and verify v3; never change files or open evaluation questions."""
    try:
        root = Path(root)
        expected, prepared, result = build(manifest["revision_plan"]["path"], root=root)
        require(manifest == expected, "Prepared revision manifest or provenance changed.")
        for label, data in prepared.items():
            path = p.relative_path(root, manifest["artifacts"][label]["path"], under=ARTIFACT_DIRECTORY)
            require(path.read_bytes() == data, "Prepared revision token bytes changed.")
        summary = p.relative_path(root, f"{ARTIFACT_DIRECTORY}/summary.json", under=ARTIFACT_DIRECTORY)
        require(summary.read_bytes() == p.json_bytes(expected) + b"\n", "Prepared revision summary changed.")
        return result
    except (KeyError, TypeError, OSError, AttributeError) as exc:
        raise ValueError("Required revision artifact or schema is missing or invalid.") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, help="Frozen public revision plan inside manifests/.")
    parser.add_argument("--verify", action="store_true", help="Rebuild in memory and verify existing artifacts without writing.")
    args = parser.parse_args(argv)
    if args.verify:
        path = p.relative_path(ROOT, PREPARATION_MANIFEST, under="manifests")
        report = decode(path.read_bytes())
        require(report["revision_plan"]["path"] == args.plan, "Verification plan differs from prepared manifest.")
        verify_prepared(ROOT, report)
    else:
        report = prepare(args.plan)
    print(json.dumps({"status": "verified" if args.verify else report["status"],
                      "artifacts": report["artifacts"], "changed_training_examples": len(CHANGED_IDS)}, indent=2))


if __name__ == "__main__":
    main()
