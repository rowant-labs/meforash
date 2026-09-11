"""Validate evidence-use decisions and project only an eligible private subset.

Version 1 deliberately supports whole claim and reading objects from the existing
historical-evidence records.  It does not fetch sources, call a model, inspect
environment variables, authenticate reviewer expertise, or approve content.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import html
import json
import os
from pathlib import Path
import re

from bibleprep.evidence import (
    PLAN,
    PRIVATE_DRAFTS,
    ROOT,
    confined_path,
    sha256,
    snapshot_index,
    strict_load,
    validate_record,
)

SCHEMA_VERSION = 1
USES = ("app_display", "redistribution", "training", "adapter_release")
DECISIONS = {"approved", "pending", "rejected", "stale", "unknown"}
SHA256_RE = re.compile(r"[a-f0-9]{64}")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}")
FIELD_REF_RE = re.compile(r"/(claims|readings)/(0|[1-9][0-9]*)")
AI_ROLE_RE = re.compile(
    r"(?:\bAI\b|artificial intelligence|language model|\bLLM\b|development assistant|engineering check)",
    re.IGNORECASE,
)


def _require_keys(value, expected, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    actual = set(value)
    expected = set(expected)
    if actual != expected:
        raise ValueError(
            f"{label} fields differ: missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )


def _identifier(value, label):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{label} must be a nonempty stable identifier")


def _text(value, label, *, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{label} must be a nonempty string")


def _text_list(value, label):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} must be a list of nonempty strings")


def _sha(value, label, *, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256")


def _canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value):
    """Hash a JSON value with the registry's stable canonical representation."""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _selected_fields(record, field_refs):
    selected = []
    for ref in field_refs:
        if not isinstance(ref, str) or not FIELD_REF_RE.fullmatch(ref):
            raise ValueError(f"Unsupported field_ref: {ref!r}")
        field, raw_index = ref.strip("/").split("/")
        index = int(raw_index)
        if index >= len(record[field]):
            raise ValueError(f"field_ref is outside the record: {ref}")
        _identifier(record[field][index]["id"], f"selected content ID at {ref}")
        selected.append({"field_ref": ref, "value": record[field][index]})
    return selected


def component_content_sha256(record, field_refs):
    """Return the hash for exact claim/reading objects named by JSON pointers."""
    return canonical_sha256(_selected_fields(record, field_refs))


def _required_citation_ids(selected):
    result = set()
    for item in selected:
        value = item["value"]
        if item["field_ref"].startswith("/claims/"):
            result.update(value["supporting_citation_ids"])
            result.update(value["contrary_citation_ids"])
        else:
            result.update(value["citation_ids"])
    return result


def _validate_alternative_closure(record, selected):
    selected_claim_ids = {
        item["value"]["id"] for item in selected if item["field_ref"].startswith("/claims/")
    }
    required = {
        alternative
        for item in selected
        if item["field_ref"].startswith("/claims/")
        for alternative in item["value"]["alternative_claim_ids"]
    }
    missing = required - selected_claim_ids
    if missing:
        raise ValueError("Selected claim omits alternative claim content: " + ", ".join(sorted(missing)))


def _review_evidence(entries, root, label):
    if not isinstance(entries, list):
        raise ValueError(f"{label} must be a list")
    seen = set()
    result = []
    for index, entry in enumerate(entries):
        item_label = f"{label}[{index}]"
        _require_keys(entry, {"evidence_id", "path", "content_sha256"}, item_label)
        _identifier(entry["evidence_id"], item_label + ".evidence_id")
        if entry["evidence_id"] in seen:
            raise ValueError(f"Duplicate supporting review evidence ID: {entry['evidence_id']}")
        seen.add(entry["evidence_id"])
        _text(entry["path"], item_label + ".path")
        _sha(entry["content_sha256"], item_label + ".content_sha256")
        path = confined_path(root, entry["path"], ("data/evidence", "runs"))
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Supporting review evidence is missing or unsafe: {entry['path']}")
        if sha256(path) != entry["content_sha256"]:
            raise ValueError(f"Supporting review evidence hash mismatch: {entry['evidence_id']}")
        result.append(entry)
    return result


def _review_decision(value, root, label, *, scholarly):
    expected = {
        "decision", "reviewer_kind", "reviewer_role", "reviewed_on", "rationale", "limitations",
        "supporting_review_evidence",
    }
    if scholarly:
        expected.add("expert_certification")
    _require_keys(value, expected, label)
    if value["decision"] not in DECISIONS:
        raise ValueError(f"Unsupported {label} decision")
    if value["reviewer_kind"] not in {None, "ai", "human", "unknown"}:
        raise ValueError(f"{label}.reviewer_kind must be ai, human, unknown, or null")
    if scholarly and not isinstance(value["expert_certification"], bool):
        raise ValueError(f"{label}.expert_certification must be boolean")
    if scholarly and value["expert_certification"] and value["decision"] != "approved":
        raise ValueError("Expert certification requires an approved scholarly decision")
    if value["decision"] == "pending" and value["reviewer_kind"] is not None:
        raise ValueError(f"{label}.reviewer_kind must be null while pending")
    if value["reviewer_role"] is not None:
        _text(value["reviewer_role"], label + ".reviewer_role")
    if value["reviewed_on"] is not None:
        try:
            date.fromisoformat(value["reviewed_on"])
        except (TypeError, ValueError):
            raise ValueError(f"{label}.reviewed_on must be an ISO date or null") from None
    _text(value["rationale"], label + ".rationale")
    _text_list(value["limitations"], label + ".limitations")
    evidence = _review_evidence(value["supporting_review_evidence"], root, label + ".supporting_review_evidence")
    if value["decision"] in {"approved", "rejected", "stale"}:
        if (value["reviewer_kind"] is None or value["reviewer_role"] is None
                or value["reviewed_on"] is None or not evidence):
            raise ValueError(f"{label} {value['decision']} decision lacks complete review evidence")
    if scholarly:
        if value["expert_certification"] and value["reviewer_kind"] != "human":
            raise ValueError("Expert certification requires reviewer_kind human")
        if value["expert_certification"] and AI_ROLE_RE.search(value["reviewer_role"]):
            raise ValueError("AI or unspecified reviewer role cannot claim expert certification")
    return value


def _load_records(root, directory):
    directory = confined_path(root, directory, ("data/evidence",))
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Record directory is missing or unsafe")
    schema = strict_load(root / PLAN)["record_schema"]
    records = {}
    paths = {}
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink() or path.parent != directory:
            raise ValueError("Record path is unsafe")
        record = strict_load(path)
        result = validate_record(record, schema)
        if result["errors"]:
            raise ValueError(f"Record validation failed for {path.name}: {result['errors']}")
        if record["id"] in records:
            raise ValueError(f"Duplicate record ID: {record['id']}")
        records[record["id"]] = record
        paths[record["id"]] = path
    if not records:
        raise ValueError("No evidence records found")
    return records, paths


def _validate_registry(registry, root, record_directory):
    root = Path(root).resolve()
    records, record_paths = _load_records(root, record_directory)
    _require_keys(registry, {"schema_version", "registry_id", "status", "scope", "records", "limitations"},
                  "registry")
    if registry["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported eligibility registry schema_version")
    _identifier(registry["registry_id"], "registry.registry_id")
    if registry["status"] not in {"pending", "reviewed", "superseded"}:
        raise ValueError("Unsupported registry status")
    _text(registry["scope"], "registry.scope")
    _text_list(registry["limitations"], "registry.limitations")
    if not isinstance(registry["records"], list):
        raise ValueError("registry.records must be a list")

    prepared = []
    seen_records = set()
    for record_index, registry_record in enumerate(registry["records"]):
        label = f"registry.records[{record_index}]"
        _require_keys(registry_record, {"record_id", "record_sha256", "components"}, label)
        record_id = registry_record["record_id"]
        _identifier(record_id, label + ".record_id")
        if record_id in seen_records:
            raise ValueError(f"Duplicate registry record ID: {record_id}")
        seen_records.add(record_id)
        if record_id not in records:
            raise ValueError(f"Registry record is unavailable: {record_id}")
        _sha(registry_record["record_sha256"], label + ".record_sha256")
        if sha256(record_paths[record_id]) != registry_record["record_sha256"]:
            raise ValueError(f"Record hash mismatch or stale registry dependency: {record_id}")
        if not isinstance(registry_record["components"], list):
            raise ValueError(f"{label}.components must be a list")
        record = records[record_id]
        citation_by_id = {item["id"]: item for item in record["citations"]}
        seen_components = set()
        components = []
        for component_index, component in enumerate(registry_record["components"]):
            component_label = f"{label}.components[{component_index}]"
            _require_keys(component, {
                "component_id", "field_refs", "content_sha256", "citation_dependencies",
                "source_dependencies", "scholarly_review", "uses",
            }, component_label)
            _identifier(component["component_id"], component_label + ".component_id")
            if component["component_id"] in seen_components:
                raise ValueError(f"Duplicate component ID in {record_id}: {component['component_id']}")
            seen_components.add(component["component_id"])
            if not isinstance(component["field_refs"], list) or not component["field_refs"]:
                raise ValueError(f"{component_label}.field_refs must be a nonempty list")
            if len(set(component["field_refs"])) != len(component["field_refs"]):
                raise ValueError(f"Duplicate field_ref in {component['component_id']}")
            selected = _selected_fields(record, component["field_refs"])
            _validate_alternative_closure(record, selected)
            _sha(component["content_sha256"], component_label + ".content_sha256")
            if component_content_sha256(record, component["field_refs"]) != component["content_sha256"]:
                raise ValueError(f"Component hash mismatch or stale content: {record_id}/{component['component_id']}")

            required_citations = _required_citation_ids(selected)
            if not isinstance(component["citation_dependencies"], list):
                raise ValueError(f"{component_label}.citation_dependencies must be a list")
            citation_dependencies = {}
            for dependency in component["citation_dependencies"]:
                _require_keys(dependency, {"citation_id", "citation_sha256"}, "citation dependency")
                _identifier(dependency["citation_id"], "citation dependency citation_id")
                _sha(dependency["citation_sha256"], "citation dependency citation_sha256")
                citation_id = dependency["citation_id"]
                if citation_id in citation_dependencies:
                    raise ValueError(f"Duplicate citation dependency: {citation_id}")
                if citation_id not in citation_by_id:
                    raise ValueError(f"Unresolved citation dependency: {citation_id}")
                if canonical_sha256(citation_by_id[citation_id]) != dependency["citation_sha256"]:
                    raise ValueError(f"Citation hash mismatch or stale dependency: {citation_id}")
                citation_dependencies[citation_id] = dependency
            if set(citation_dependencies) != required_citations:
                raise ValueError(
                    f"Citation dependency closure differs for {record_id}/{component['component_id']}: "
                    f"missing={sorted(required_citations - set(citation_dependencies))} "
                    f"extra={sorted(set(citation_dependencies) - required_citations)}"
                )

            if not isinstance(component["source_dependencies"], list):
                raise ValueError(f"{component_label}.source_dependencies must be a list")
            source_dependencies = {}
            source_complete = True
            exclusion_reasons = []
            for dependency in component["source_dependencies"]:
                _require_keys(dependency, {"citation_id", "source_id", "snapshot_path", "content_sha256"},
                              "source dependency")
                citation_id = dependency["citation_id"]
                _identifier(citation_id, "source dependency citation_id")
                _text(dependency["source_id"], "source dependency source_id")
                _sha(dependency["content_sha256"], "source dependency content_sha256", nullable=True)
                if dependency["snapshot_path"] is not None:
                    _text(dependency["snapshot_path"], "source dependency snapshot_path")
                if citation_id in source_dependencies:
                    raise ValueError(f"Duplicate source dependency: {citation_id}")
                citation = citation_by_id.get(citation_id)
                if citation is None or citation_id not in required_citations:
                    raise ValueError(f"Source dependency does not match selected citation: {citation_id}")
                if dependency["source_id"] != citation["source_id"]:
                    raise ValueError(f"Source ID mismatch for citation: {citation_id}")
                if dependency["content_sha256"] != citation["content_sha256"]:
                    raise ValueError(f"Source hash mismatch or stale citation source: {citation_id}")
                if dependency["content_sha256"] is None:
                    if dependency["snapshot_path"] is not None:
                        raise ValueError(f"Snapshot path cannot stand in for an unbound citation: {citation_id}")
                    source_complete = False
                    exclusion_reasons.append(f"source hash is unresolved for citation {citation_id}")
                elif dependency["snapshot_path"] is None:
                    source_complete = False
                    exclusion_reasons.append(f"local source snapshot is unresolved for citation {citation_id}")
                else:
                    source_path = confined_path(root, dependency["snapshot_path"], ("data/raw",))
                    if not source_path.is_file() or source_path.is_symlink():
                        raise ValueError(f"Source snapshot is missing or unsafe: {dependency['snapshot_path']}")
                    if sha256(source_path) != dependency["content_sha256"]:
                        raise ValueError(f"Source snapshot hash mismatch: {citation_id}")
                source_dependencies[citation_id] = dependency
            if set(source_dependencies) != required_citations:
                raise ValueError(
                    f"Source dependency closure differs for {record_id}/{component['component_id']}: "
                    f"missing={sorted(required_citations - set(source_dependencies))} "
                    f"extra={sorted(set(source_dependencies) - required_citations)}"
                )

            scholarly = _review_decision(component["scholarly_review"], root,
                                           component_label + ".scholarly_review", scholarly=True)
            _require_keys(component["uses"], set(USES), component_label + ".uses")
            uses = {
                use: _review_decision(component["uses"][use], root,
                                      component_label + f".uses.{use}", scholarly=False)
                for use in USES
            }
            components.append({
                "component": component,
                "selected": selected,
                "citations": [citation_by_id[cid] for cid in sorted(required_citations)],
                "source_complete": source_complete,
                "source_exclusion_reasons": exclusion_reasons,
                "scholarly": scholarly,
                "uses": uses,
            })
        prepared.append({"registry_record": registry_record, "record": record, "components": components})
    return prepared


def _eligibility(component, selected_use, registry_status):
    reasons = list(component["source_exclusion_reasons"])
    if registry_status != "reviewed":
        reasons.append("registry status is " + registry_status)
    scholarly = component["scholarly"]
    use = component["uses"][selected_use]
    if scholarly["decision"] != "approved":
        reasons.append("scholarly review decision is " + scholarly["decision"])
    if use["decision"] != "approved":
        reasons.append(f"{selected_use} decision is {use['decision']}")
    return not reasons, reasons


def audit_registry(registry, root=ROOT, record_directory=None):
    """Return a deterministic validation/eligibility summary without writing."""
    root = Path(root).resolve()
    prepared = _validate_registry(registry, root, record_directory or root / PRIVATE_DRAFTS)
    counts = {use: 0 for use in USES}
    component_count = 0
    for record in prepared:
        for component in record["components"]:
            component_count += 1
            for use in USES:
                eligible, _ = _eligibility(component, use, registry["status"])
                counts[use] += int(eligible)
    return {
        "schema_version": SCHEMA_VERSION,
        "registry_id": registry["registry_id"],
        "registry_sha256": canonical_sha256(registry),
        "status": "valid",
        "record_count": len(prepared),
        "component_count": component_count,
        "eligible_components_by_use": counts,
        "expertise_authenticated": False,
        "model_calls": 0,
        "network_requests": 0,
        "limitations": [
            "Hash and dependency checks do not establish scholarly accuracy or legal permission.",
            "Reviewer roles and expert-certification fields are recorded claims; this validator cannot authenticate identity or expertise.",
        ],
    }


def build_projection(registry, selected_use, root=ROOT, record_directory=None):
    """Build the selected-use projection; an empty eligible subset is valid."""
    if selected_use not in USES:
        raise ValueError(f"Unsupported selected use: {selected_use}")
    root = Path(root).resolve()
    prepared = _validate_registry(registry, root, record_directory or root / PRIVATE_DRAFTS)
    projected_records = []
    exclusions = []
    for item in sorted(prepared, key=lambda value: value["registry_record"]["record_id"]):
        projected_components = []
        for component in sorted(item["components"], key=lambda value: value["component"]["component_id"]):
            raw = component["component"]
            eligible, reasons = _eligibility(component, selected_use, registry["status"])
            if not eligible:
                exclusions.append({
                    "record_id": item["registry_record"]["record_id"],
                    "component_id": raw["component_id"],
                    "reasons": reasons,
                })
                continue
            projected_components.append({
                "component_id": raw["component_id"],
                "content_sha256": raw["content_sha256"],
                "content": component["selected"],
                "citations": component["citations"],
                "citation_dependencies": raw["citation_dependencies"],
                "source_dependencies": raw["source_dependencies"],
                "scholarly_review": component["scholarly"],
                "use_decision": component["uses"][selected_use],
            })
        if projected_components:
            projected_records.append({
                "record_id": item["registry_record"]["record_id"],
                "record_sha256": item["registry_record"]["record_sha256"],
                "coverage_limits": item["record"]["coverage_limits"],
                "record_unresolved_issues": item["record"]["review"]["unresolved_issues"],
                "components": projected_components,
            })
    return {
        "schema_version": SCHEMA_VERSION,
        "registry_id": registry["registry_id"],
        "registry_sha256": canonical_sha256(registry),
        "selected_use": selected_use,
        "status": "eligible_subset_projected",
        "record_count": len(projected_records),
        "component_count": sum(len(item["components"]) for item in projected_records),
        "records": projected_records,
        "excluded_components": exclusions,
        "limitations": list(registry["limitations"]) + [
            "Projection eligibility records review decisions; it does not independently prove scholarly accuracy, reviewer expertise, or legal permission.",
            "Only whole v1 claim and reading objects are supported; their uncertainty, alternatives, citations, and qualifications remain attached.",
        ],
    }


def _pending_review(*, scholarly):
    result = {
        "decision": "pending",
        "reviewer_kind": None,
        "reviewer_role": None,
        "reviewed_on": None,
        "rationale": "No review decision has been recorded.",
        "limitations": ["Review and supporting evidence are pending."],
        "supporting_review_evidence": [],
    }
    if scholarly:
        result["expert_certification"] = False
    return result


def _claim_groups(record):
    by_id = {claim["id"]: index for index, claim in enumerate(record["claims"])}
    remaining = set(by_id)
    groups = []
    while remaining:
        start = min(remaining)
        group = {start}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            neighbors = set(record["claims"][by_id[current]]["alternative_claim_ids"])
            neighbors.update(
                claim["id"] for claim in record["claims"] if current in claim["alternative_claim_ids"]
            )
            for neighbor in sorted(neighbors):
                if neighbor not in group:
                    group.add(neighbor)
                    frontier.append(neighbor)
        remaining -= group
        groups.append(sorted(group))
    return groups


def seed_pending_registry(root=ROOT, record_directory=None, registry_id="evidence-eligibility-v1"):
    """Derive an explicit all-pending registry; this never makes an approval."""
    root = Path(root).resolve()
    records, paths = _load_records(root, record_directory or root / PRIVATE_DRAFTS)
    snapshots = {
        digest: [path for path in paths if path.startswith("data/raw/")]
        for digest, paths in snapshot_index(root).items()
    }
    registry_records = []
    for record_id in sorted(records):
        record = records[record_id]
        citation_by_id = {item["id"]: item for item in record["citations"]}
        components = []
        selections = []
        for group in _claim_groups(record):
            indices = sorted(record["claims"].index(next(c for c in record["claims"] if c["id"] == cid))
                             for cid in group)
            selections.append(("claim-" + group[0], [f"/claims/{index}" for index in indices]))
        selections.extend(("reading-" + reading["id"], [f"/readings/{index}"])
                          for index, reading in enumerate(record["readings"]))
        for component_id, field_refs in selections:
            selected = _selected_fields(record, field_refs)
            citation_ids = sorted(_required_citation_ids(selected))
            citation_dependencies = [
                {"citation_id": cid, "citation_sha256": canonical_sha256(citation_by_id[cid])}
                for cid in citation_ids
            ]
            source_dependencies = []
            for cid in citation_ids:
                citation = citation_by_id[cid]
                digest = citation["content_sha256"]
                paths_for_hash = snapshots.get(digest, []) if digest else []
                source_dependencies.append({
                    "citation_id": cid,
                    "source_id": citation["source_id"],
                    "snapshot_path": paths_for_hash[0] if paths_for_hash else None,
                    "content_sha256": digest,
                })
            components.append({
                "component_id": component_id,
                "field_refs": field_refs,
                "content_sha256": component_content_sha256(record, field_refs),
                "citation_dependencies": citation_dependencies,
                "source_dependencies": source_dependencies,
                "scholarly_review": _pending_review(scholarly=True),
                "uses": {use: _pending_review(scholarly=False) for use in USES},
            })
        registry_records.append({
            "record_id": record_id,
            "record_sha256": sha256(paths[record_id]),
            "components": components,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "registry_id": registry_id,
        "status": "pending",
        "scope": "Exact claim and reading components from validated v1 evidence records.",
        "records": registry_records,
        "limitations": [
            "All scholarly and use decisions are pending; this seed grants no eligibility.",
            "Missing local snapshots remain explicit unresolved source dependencies.",
        ],
    }


def _md(value):
    """Render untrusted plain text without activating Markdown or HTML."""
    if value is None:
        return "(none)"
    escaped = html.escape(str(value), quote=True)
    for character in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!", "|", ">"):
        escaped = escaped.replace(character, "\\" + character)
    return escaped.replace("\r", " ").replace("\n", " ")


def render_markdown(projection):
    """Render a compact, deterministic private review companion."""
    lines = [
        "# Evidence eligibility projection",
        "",
        f"Registry: `{projection['registry_id']}`  ",
        f"Registry SHA-256: `{projection['registry_sha256']}`  ",
        f"Selected use: `{projection['selected_use']}`  ",
        f"Eligible records: {projection['record_count']}  ",
        f"Eligible components: {projection['component_count']}",
        "",
    ]
    if not projection["records"]:
        lines.extend(["No components are eligible for this use.", ""])
    for record in projection["records"]:
        lines.extend([f"## {record['record_id']}", "", f"Record SHA-256: `{record['record_sha256']}`", ""])
        lines.extend(["Coverage limits:", ""])
        lines.extend("- " + _md(value) for value in record["coverage_limits"])
        if not record["coverage_limits"]:
            lines.append("- (none recorded)")
        lines.extend(["", "Parent-record unresolved issues:", ""])
        lines.extend("- " + _md(value) for value in record["record_unresolved_issues"])
        if not record["record_unresolved_issues"]:
            lines.append("- (none recorded)")
        lines.append("")
        for component in record["components"]:
            scholarly = component["scholarly_review"]
            use_decision = component["use_decision"]
            lines.extend([
                f"### {component['component_id']}", "",
                f"Content SHA-256: `{component['content_sha256']}`", "",
                f"Scholarly review: `{component['scholarly_review']['decision']}`; "
                f"expert certification recorded: `{str(component['scholarly_review']['expert_certification']).lower()}`",
                "",
                f"Use decision: `{component['use_decision']['decision']}`",
                "",
                "Scholarly review details:",
                "",
                f"- Reviewer kind: {_md(scholarly['reviewer_kind'])}",
                f"- Reviewer role: {_md(scholarly['reviewer_role'])}",
                f"- Reviewed on: {_md(scholarly['reviewed_on'])}",
                f"- Rationale: {_md(scholarly['rationale'])}",
                "- Limitations: " + ("; ".join(_md(value) for value in scholarly["limitations"]) or "(none recorded)"),
                "- Supporting review evidence: " + (
                    "; ".join(_md(item["evidence_id"]) + " at " + _md(item["path"])
                              for item in scholarly["supporting_review_evidence"])
                    or "(none recorded)"
                ),
                "",
                "Use review details:",
                "",
                f"- Reviewer kind: {_md(use_decision['reviewer_kind'])}",
                f"- Reviewer role: {_md(use_decision['reviewer_role'])}",
                f"- Reviewed on: {_md(use_decision['reviewed_on'])}",
                f"- Rationale: {_md(use_decision['rationale'])}",
                "- Limitations: " + ("; ".join(_md(value) for value in use_decision["limitations"]) or "(none recorded)"),
                "- Supporting review evidence: " + (
                    "; ".join(_md(item["evidence_id"]) + " at " + _md(item["path"])
                              for item in use_decision["supporting_review_evidence"])
                    or "(none recorded)"
                ),
                "",
                "Selected content:",
                "",
            ])
            for selected in component["content"]:
                value = selected["value"]
                lines.append(f"- `{selected['field_ref']}` · ID `{value['id']}`")
                if selected["field_ref"].startswith("/claims/"):
                    lines.extend([
                        f"  - Text: {_md(value['text'])}",
                        f"  - Kind: `{value['kind']}`; assessment: `{value['assessment']}`",
                        f"  - Attributed position: {_md(value['attributed_position'])}",
                        "  - Supporting citations: " + ", ".join(f"`{item}`" for item in value["supporting_citation_ids"]),
                        "  - Contrary citations: " + (", ".join(f"`{item}`" for item in value["contrary_citation_ids"]) or "(none)"),
                        "  - Alternative claims: " + (", ".join(f"`{item}`" for item in value["alternative_claim_ids"]) or "(none)"),
                        "  - Limitations: " + ("; ".join(_md(item) for item in value["limitations"]) or "(none recorded)"),
                    ])
                else:
                    lines.extend([
                        f"  - Entity: `{value['entity_type']}` · {_md(value['stable_entity_id'])}",
                        f"  - Edition or transcription: {_md(value['edition_or_transcription'])}",
                        f"  - Hand: {_md(value['hand'])}",
                        f"  - Original representation: {_md(value['original_representation'])}",
                        f"  - English rendering: {_md(value['english_rendering'])}",
                        f"  - Rendering author: {_md(value['rendering_author'])}",
                        f"  - Attestation: `{value['attestation']}`",
                        "  - Citation IDs: " + ", ".join(f"`{item}`" for item in value["citation_ids"]),
                        "  - Encoding notes: " + ("; ".join(_md(item) for item in value["encoding_notes"]) or "(none recorded)"),
                    ])
            lines.extend(["", "Citations:", ""])
            for citation in component["citations"]:
                lines.append(f"- `{citation['id']}` — {_md(citation['title'])}; {_md(citation['locator'])}")
            lines.append("")
    lines.extend(["## Excluded components", ""])
    if not projection["excluded_components"]:
        lines.extend(["None.", ""])
    else:
        for item in projection["excluded_components"]:
            lines.append(
                f"- `{item['record_id']}/{item['component_id']}` — " + "; ".join(_md(reason) for reason in item["reasons"])
            )
        lines.append("")
    lines.extend(["## Limitations", ""])
    lines.extend("- " + _md(item) for item in projection["limitations"])
    lines.append("")
    return "\n".join(lines)


def _exclusive_text(path):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8")


def _mkdir_private(path, root):
    root = Path(root).resolve()
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists():
            if not current.is_dir() or current.is_symlink():
                raise ValueError(f"Private output ancestor is unsafe: {current}")
            continue
        os.mkdir(current, 0o700)


def _exclusive_json(path, value):
    with _exclusive_text(path) as output:
        json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")


def write_projection(projection, output_directory, root=ROOT):
    """Write JSON and Markdown to a new private directory without overwrite."""
    root = Path(root).resolve()
    destination = confined_path(root, output_directory, ("runs", "data/evidence"))
    if destination.exists():
        raise FileExistsError(destination)
    _mkdir_private(destination.parent, root)
    os.mkdir(destination, 0o700)
    json_path = destination / "projection.json"
    markdown_path = destination / "projection.md"
    try:
        _exclusive_json(json_path, projection)
        with _exclusive_text(markdown_path) as output:
            output.write(render_markdown(projection))
    except Exception:
        # Preserve any successfully written file for diagnosis; never overwrite or delete user data.
        raise
    return {
        "output_directory": destination.relative_to(root).as_posix(),
        "json_sha256": sha256(json_path),
        "markdown_sha256": sha256(markdown_path),
    }


def write_pending_registry(registry, destination, root=ROOT):
    """Write a seed registry to a fresh private file."""
    root = Path(root).resolve()
    path = confined_path(root, destination, ("runs", "data/evidence"))
    _mkdir_private(path.parent, root)
    _exclusive_json(path, registry)
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256(path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(PRIVATE_DRAFTS),
                        help="Validated v1 record directory under data/evidence")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--registry", type=Path, help="Existing private registry JSON")
    mode.add_argument("--seed-pending", type=Path, metavar="PATH",
                      help="Write a fresh all-pending private registry")
    parser.add_argument("--registry-id", default="evidence-eligibility-v1")
    parser.add_argument("--use", choices=USES, default="app_display")
    parser.add_argument("--out", type=Path, help="Fresh private projection directory")
    args = parser.parse_args(argv)
    try:
        if args.seed_pending:
            if args.out:
                parser.error("--out cannot be combined with --seed-pending")
            registry = seed_pending_registry(ROOT, args.directory, args.registry_id)
            receipt = write_pending_registry(registry, args.seed_pending, ROOT)
            print(json.dumps({"status": "pending_registry_written", **receipt}, indent=2))
            return 0
        registry_path = confined_path(ROOT, args.registry, ("runs", "data/evidence"))
        registry = strict_load(registry_path)
        summary = audit_registry(registry, ROOT, args.directory)
        if args.out:
            projection = build_projection(registry, args.use, ROOT, args.directory)
            receipt = write_projection(projection, args.out, ROOT)
            summary["projection"] = {"selected_use": args.use, **receipt}
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
