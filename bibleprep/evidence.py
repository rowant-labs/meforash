"""Validate private historical-evidence drafts without approving or loading them.

Uses the planned JSON Schema plus cross-reference, date and draft-stage checks.
This module never calls a model, changes chat inputs, or exports training data.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PLAN = "manifests/historical-evidence-plan-v1.json"
PRIVATE_DRAFTS = "data/evidence/drafts/v1"


def strict_load(path):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_record(record, schema):
    """Return mechanical errors separately from unresolved research/release work."""
    from jsonschema import Draft202012Validator, FormatChecker
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = ["schema:" + "/".join(map(str, e.absolute_path)) + ":" + str(e.validator)
              for e in validator.iter_errors(record)]
    if errors:
        return {"errors": sorted(errors), "research_gaps": [], "release_ready": False}

    def unique(items, field, label):
        identifiers = [item[field] for item in items]
        if any(not value.strip() for value in identifiers):
            errors.append(label + ":empty_id")
        if len(set(identifiers)) != len(identifiers):
            errors.append(label + ":duplicate_id")
        return set(identifiers)

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", record["id"]):
        errors.append("record:invalid_id")
    if record["status"] not in {"draft", "blocked"}:
        errors.append("record:this_pipeline_accepts_drafts_only")
    if not record["summary"].strip() or not record["citations"] or not record["claims"]:
        errors.append("record:missing_substantive_content")
    if not record["biblical_anchor_languages"] or not record["chapter_keys"]:
        errors.append("record:missing_anchor")
    citation_ids = unique(record["citations"], "id", "citations")
    claim_ids = unique(record["claims"], "id", "claims")
    unique(record["readings"], "id", "readings")
    by_citation = {item["id"]: item for item in record["citations"]}
    source_ids = {item["source_id"] for item in record["citations"]}
    rights_sources = {item["source_id"] for item in record["rights_by_component"]}
    if source_ids - rights_sources:
        errors.append("rights:source_without_component_decision")
    rights_keys = [(item["source_id"], item["component"]) for item in record["rights_by_component"]]
    if len(set(rights_keys)) != len(rights_keys):
        errors.append("rights:duplicate_component")

    def refs(values, available, label):
        if set(values) - available:
            errors.append(label + ":unresolved_reference")
        if len(set(values)) != len(values):
            errors.append(label + ":duplicate_reference")

    gaps = ["Independent specialist review is pending; no record is approved for app use or training."]
    refs(record["mapping_citation_ids"], citation_ids, "mapping")
    for citation in record["citations"]:
        address = urlsplit(citation["url"])
        if address.scheme != "https" or not address.hostname or address.username or address.password:
            errors.append("citation:invalid_public_url")
        if not citation["locator"].strip():
            errors.append("citation:missing_locator")
        if not citation["content_sha256"]:
            gaps.append("Citation snapshot not pinned: " + citation["id"])
        if not citation["pinned_version"]:
            gaps.append("Citation has no immutable version: " + citation["id"])
    for reading in record["readings"]:
        refs(reading["citation_ids"], citation_ids, "reading")
        if not reading["citation_ids"]:
            errors.append("reading:missing_evidence")
        if reading["english_rendering"] and not reading["rendering_author"]:
            errors.append("reading:unattributed_translation")
        if reading["attestation"] in {"unpreserved", "unchecked", "absent"} and reading["original_representation"]:
            errors.append("reading:unavailable_text_has_supplied_wording")
        if reading["attestation"] in {"damaged", "supplied", "uncertain"} and not reading["encoding_notes"]:
            errors.append("reading:uncertainty_without_encoding_note")
        cited = [by_citation[x] for x in reading["citation_ids"] if x in by_citation
                 and by_citation[x]["kind"] != "rights_notice"]
        if (reading["entity_type"] == "manuscript" and reading["attestation"] != "unchecked"
                and (not cited or all(c["kind"] == "edition" for c in cited))):
            errors.append("reading:manuscript_attestation_from_editions_only")
    for claim in record["claims"]:
        refs(claim["supporting_citation_ids"], citation_ids, "claim_support")
        refs(claim["contrary_citation_ids"], citation_ids, "claim_contrary")
        refs(claim["alternative_claim_ids"], claim_ids, "claim_alternative")
        if claim["id"] in claim["alternative_claim_ids"]:
            errors.append("claim:self_alternative")
        if claim["assessment"] == "supported" and not claim["supporting_citation_ids"]:
            errors.append("claim:supported_without_citation")
        if (claim["assessment"] == "disputed" and not claim["contrary_citation_ids"]
                and not claim["alternative_claim_ids"] and not claim["limitations"]):
            errors.append("claim:dispute_without_alternative_or_limit")
        if claim["kind"] == "historical_inference" and not claim["limitations"]:
            errors.append("claim:inference_without_limits")
    for category, dates in record["dates"].items():
        if not dates:
            gaps.append("No dating assertion entered: " + category)
        for value in dates:
            refs(value["citation_ids"], citation_ids, "date")
            earliest, latest = value["earliest"], value["latest"]
            def ordinal(year):
                return year["year"] if year["era"] == "CE" else 1 - year["year"]
            if earliest and latest and ordinal(earliest) > ordinal(latest):
                errors.append("date:reversed_range")
            if (earliest or latest) and not value["citation_ids"]:
                errors.append("date:known_bound_without_evidence")
            if not value["method"].strip() or not value["uncertainty"].strip():
                errors.append("date:missing_method_or_uncertainty")
    for component in record["rights_by_component"]:
        for use in ("app_display", "training", "adapter_release"):
            if component[use]["decision"] == "approved":
                errors.append("rights:draft_cannot_approve_" + use)
        for use in ("research_access", "app_display", "redistribution", "training", "adapter_release"):
            if not component[use]["basis"].strip():
                errors.append("rights:decision_without_basis")
        if component["source_id"] not in source_ids and component["component"] != "authored_note":
            errors.append("rights:unresolved_source")
    review = record["review"]
    if review["status"] not in {"draft", "needs_revision", "blocked"}:
        errors.append("review:this_pipeline_does_not_certify_approval")
    if review["reviewer_id"] is not None and review["reviewer_id"] == review["author_id"]:
        errors.append("review:author_cannot_review_own_record")
    return {"errors": sorted(set(errors)), "research_gaps": sorted(set(gaps)), "release_ready": False}


def confined_path(root, path, prefixes):
    """Reject lexical escapes and symlink ancestors before resolving a path."""
    root = Path(root).resolve()
    path = Path(path)
    path = path if path.is_absolute() else root / path
    relative = path.relative_to(root)
    if ".." in relative.parts or not any(path.is_relative_to(root / p) for p in prefixes):
        raise ValueError("Path must remain in an allowed project directory")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Research paths must not contain symlinks")
    resolved = path.resolve()
    if not any(resolved.is_relative_to(root / p) for p in prefixes):
        raise ValueError("Resolved path escaped the project directory")
    return resolved


def snapshot_index(root):
    """Hash locally available research artifacts; never enter private run/env paths."""
    found = {}
    for prefix in ("data/raw", "licenses"):
        directory = confined_path(root, root / prefix, (prefix,))
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                path = confined_path(root, path, (prefix,))
                relative = path.relative_to(directory)
            except ValueError:
                continue
            if any(part.startswith(".") for part in relative.parts):
                continue
            digest = sha256(path)
            found.setdefault(digest, []).append(path.relative_to(root).as_posix())
    return found


def audit_directory(root=ROOT, directory=None):
    root = Path(root).resolve()
    directory = confined_path(root, directory or root / PRIVATE_DRAFTS, ("data/evidence",))
    plan = strict_load(root / PLAN)
    schema = plan["record_schema"]
    snapshots = snapshot_index(root)
    results, seen = [], set()
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink():
            raise ValueError("Draft symlinks are not accepted")
        record = strict_load(path)
        checks = validate_record(record, schema)
        if checks["errors"]:
            results.append({"file": path.name, **checks})
            continue
        if record["id"] in seen:
            checks["errors"].append("pack:duplicate_record_id")
        seen.add(record["id"])
        pinned, missing = [], []
        for citation in record["citations"]:
            digest = citation["content_sha256"]
            if digest and digest in snapshots:
                pinned.append(citation["id"])
            elif digest:
                missing.append(citation["id"])
        checks["research_gaps"].extend("Pinned citation bytes unavailable locally: " + x for x in missing)
        results.append({"file": path.name, "id": record["id"], "kind": record["kind"],
                        "anchor_languages": record["biblical_anchor_languages"],
                        "status": record["status"], "sha256": sha256(path),
                        "citations": len(record["citations"]), "locally_matched_citation_hashes": pinned,
                        "claimed_hashes_without_local_bytes": missing, **checks})
    counts = Counter((r["kind"], lang) for r in results if "kind" in r for lang in r["anchor_languages"])
    return {"schema_version": 1, "status": "drafts_valid" if results and not any(r["errors"] for r in results) else "drafts_invalid",
            "schema_plan_sha256": sha256(root / PLAN), "record_count": len(results),
            "allocation": {kind: {lang: counts[(kind, lang)] for lang in ("hebrew", "aramaic", "greek")}
                           for kind in ("textual_dossier", "historical_note")},
            "records": results, "app_approved": 0, "training_approved": 0,
            "expert_certified": False, "model_calls": 0,
            "limits": ["Valid structure and cross-references do not establish factual correctness, legal clearance or expert review.",
                       "A matching source hash binds bytes, not the truth of a claim or the accuracy of its locator.",
                       "This draft-only pipeline does not export, train, or change chat context."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, help="Draft directory under data/evidence")
    parser.add_argument("--out", type=Path, help="New private receipt under runs or data/evidence")
    args = parser.parse_args(argv)
    result = audit_directory(directory=args.directory)
    if args.out:
        try:
            destination = confined_path(ROOT, args.out, ("runs", "data/evidence"))
        except ValueError:
            parser.error("Detailed receipts must stay in private research directories")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
        destination.chmod(0o600)
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, indent=2))
    return 0 if result["status"] == "drafts_valid" else 2


if __name__ == "__main__":
    raise SystemExit(main())
