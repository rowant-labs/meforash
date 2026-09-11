"""Build a deterministic, private review aid from validated evidence drafts.

The export preserves draft uncertainty and component-use decisions.  It does not
approve evidence, fetch sources, call a model, or alter the source records.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import html
import json
from pathlib import Path
import re

from bibleprep.evidence import (
    PRIVATE_DRAFTS,
    ROOT,
    audit_directory,
    confined_path,
    sha256,
    strict_load,
)

INVENTORY = "manifests/evidence-first-pack-v1.json"
REFERENCE_MAP = "manifests/evidence-reference-map-v1.json"
DATE_CATEGORIES = (
    "narrated_setting",
    "proposed_composition",
    "physical_witness",
    "modern_edition",
)
USES = ("research_access", "app_display", "redistribution", "training", "adapter_release")
DOWNSTREAM_USES = ("app_display", "redistribution", "training", "adapter_release")


def _require_keys(value, expected, label):
    actual = set(value)
    expected = set(expected)
    if actual != expected:
        raise ValueError(f"{label} fields differ: missing={sorted(expected-actual)} extra={sorted(actual-expected)}")


def validate_reference_mapping(mapping, records, record_hashes):
    """Return entries keyed by (record ID, original key), rejecting ambiguity."""
    _require_keys(mapping, {"schema_version", "id", "status", "scope", "review", "entries", "limitations"},
                  "reference mapping")
    if mapping["schema_version"] != 1 or mapping["id"] != "evidence-reference-map-v1":
        raise ValueError("Unsupported reference mapping")
    review = mapping["review"]
    _require_keys(review, {"review_type", "reviewer_role", "reviewed_on", "specialist_certification"},
                  "reference mapping review")
    if review["review_type"] != "ai_engineering_coordinate_check" or review["specialist_certification"] is not False:
        raise ValueError("Reference mapping must remain an engineering check, not specialist certification")

    record_by_id = {record["id"]: record for record in records}
    if len(record_by_id) != len(records):
        raise ValueError("Duplicate record ID")
    expected = {(record["id"], key) for record in records for key in record["chapter_keys"]}
    result = {}
    entry_keys = {
        "record_id", "record_sha256", "original_chapter_key", "normalized_chapter_key",
        "source_id", "edition", "edition_coordinate", "mapping_citation_ids", "note",
    }
    for index, entry in enumerate(mapping["entries"]):
        _require_keys(entry, entry_keys, f"reference mapping entry {index}")
        pair = (entry["record_id"], entry["original_chapter_key"])
        if pair in result:
            raise ValueError(f"Ambiguous reference mapping for {pair[0]} {pair[1]}")
        record = record_by_id.get(entry["record_id"])
        if record is None or pair not in expected:
            raise ValueError(f"Reference mapping does not identify a draft chapter key: {pair}")
        if entry["record_sha256"] != record_hashes[entry["record_id"]]:
            raise ValueError(f"Reference mapping record hash mismatch: {entry['record_id']}")
        if not re.fullmatch(r"bible:[A-Za-z0-9]+\.[1-9][0-9]*", entry["normalized_chapter_key"]):
            raise ValueError(f"Invalid normalized chapter key: {entry['normalized_chapter_key']}")
        if not all(isinstance(entry[key], str) and entry[key].strip()
                   for key in ("source_id", "edition", "edition_coordinate", "note")):
            raise ValueError(f"Incomplete source/edition coordinate for {pair}")
        coordinate = re.fullmatch(r"(oshb|sblgnt):([A-Za-z0-9]+)\.([1-9][0-9]*)",
                                  entry["edition_coordinate"])
        original = re.fullmatch(r"(?:(oshb|sblgnt):)?([A-Za-z0-9]+)\.([1-9][0-9]*)",
                                entry["original_chapter_key"])
        normalized = re.fullmatch(r"bible:([A-Za-z0-9]+)\.([1-9][0-9]*)",
                                  entry["normalized_chapter_key"])
        if not coordinate or not original or not normalized:
            raise ValueError(f"Unsupported v1 chapter coordinate for {pair}")
        prefix, book, chapter = coordinate.groups()
        expected_edition = {"oshb": "OSHB/WLC", "sblgnt": "SBLGNT"}[prefix]
        source_matches = (entry["source_id"] == "oshb" or entry["source_id"].startswith("oshb-")) \
            if prefix == "oshb" else entry["source_id"] == "sblgnt"
        if (entry["edition"] != expected_edition or not source_matches
                or original.groups()[1:] != (book, chapter)
                or (original.group(1) is not None and original.group(1) != prefix)
                or normalized.groups() != (book, chapter)):
            raise ValueError(f"Inconsistent v1 source/edition chapter coordinate for {pair}")
        citations = {item["id"]: item for item in record["citations"]}
        if not entry["mapping_citation_ids"] or any(cid not in citations for cid in entry["mapping_citation_ids"]):
            raise ValueError(f"Unresolved mapping citation for {pair}")
        if not any(citations[cid]["source_id"] == entry["source_id"]
                   for cid in entry["mapping_citation_ids"]):
            raise ValueError(f"Mapping source is not bound to its citation for {pair}")
        result[pair] = entry
    missing = expected - set(result)
    extra = set(result) - expected
    if missing or extra:
        raise ValueError(f"Reference mapping coverage differs: missing={sorted(missing)} extra={sorted(extra)}")
    return result


def _field(record_id, path, item_id=None):
    result = {"record_id": record_id, "field_path": path}
    if item_id is not None:
        result["item_id"] = item_id
    return result


def derive_gap_queue(records, audit_by_id):
    """Derive stable, traceable issues without interpreting gaps as approval."""
    gaps = []

    def add(record_id, category, field_path, item_id, reason, evidence_needed, next_action, uses=None):
        suffix = re.sub(r"[^A-Za-z0-9]+", "-", item_id or field_path).strip("-").lower()
        issue = {
            "issue_id": f"{record_id.lower()}-{category.replace('_', '-')}-{suffix}",
            "record_id": record_id,
            "affected": _field(record_id, field_path, item_id),
            "reason_category": category,
            "reason": reason,
            "evidence_needed": evidence_needed,
            "next_action": next_action,
            "status": "open",
        }
        if uses is not None:
            issue["uses"] = uses
        gaps.append(issue)

    for record in records:
        record_id = record["id"]
        audit = audit_by_id[record_id]
        missing_local = set(audit["claimed_hashes_without_local_bytes"])
        for index, citation in enumerate(record["citations"]):
            path = f"citations[{index}]"
            if citation["content_sha256"] is None:
                add(record_id, "missing_source_bytes", path, citation["id"],
                    "Citation has no content_sha256; its source bytes are not locally bound.",
                    "Exact source bytes and a matching SHA-256, while retaining the current locator and pinned-version uncertainty.",
                    "Acquire the exact permitted source snapshot and verify its locator; do not infer the bytes from the URL.")
            elif citation["id"] in missing_local:
                add(record_id, "missing_source_bytes", path, citation["id"],
                    "Citation claims a content hash but matching local source bytes were not found.",
                    "Local source bytes matching the asserted content_sha256.",
                    "Recover the exact snapshot and rerun source-byte validation before review.")
            if citation["pinned_version"] is None:
                add(record_id, "missing_immutable_version", path, citation["id"],
                    "Citation has no pinned_version; the cited locator is not bound to an immutable source version.",
                    "An immutable version identifier or a documented exact-byte snapshot with its limits.",
                    "Pin the exact source version without treating a current web page as historically stable.")
        for index, reading in enumerate(record["readings"]):
            attestation = reading["attestation"]
            attestation_categories = {
                "unchecked": ("unchecked_attestation", "Reading has not been checked against the identified witness or edition."),
                "uncertain": ("qualified_attestation", "Reading attestation is explicitly uncertain."),
                "damaged": ("qualified_attestation", "Reading is attested in damaged material; preserved and restored characters must remain distinct."),
                "supplied": ("qualified_attestation", "Reading contains supplied material; the editorial supply must remain explicit."),
                "absent": ("confirmed_absence", "The record reports a checked absence; this is distinct from an unchecked witness."),
                "unpreserved": ("unpreserved_witness", "The relevant part is reported as unpreserved; no wording can be recovered from this witness."),
            }
            if attestation in attestation_categories:
                category, reason = attestation_categories[attestation]
                add(record_id, category, f"readings[{index}]", reading["id"], reason,
                    "Directly checked witness or edition evidence with an exact locator and preserved correction/damage state.",
                    "Check or review the cited artifact while preserving the recorded attestation category and unavailable wording.")
        for index, claim in enumerate(record["claims"]):
            if claim["assessment"] != "supported":
                add(record_id, "scholarly_judgment", f"claims[{index}]", claim["id"],
                    f"Claim assessment is {claim['assessment']}; its alternatives, contrary evidence, and limitations remain live.",
                    "Qualified review of the supporting and contrary citations and any directly relevant evidence.",
                    "Adjudicate the claim with an appropriate specialist and retain dissent or uncertainty.")
        for category in DATE_CATEGORIES:
            if not record["dates"][category]:
                add(record_id, "missing_date_assertion", f"dates.{category}", category,
                    f"No {category} date assertion is entered.",
                    "A sourced date range with method and uncertainty, or a reviewed decision that the category is not applicable.",
                    "Review this date category without transferring a date from another category.")
        seen_rights = set()
        for index, component in enumerate(record["rights_by_component"]):
            identity = (component["source_id"], component["component"])
            if identity in seen_rights:
                raise ValueError(f"Conflicting duplicate rights component: {record_id} {identity}")
            seen_rights.add(identity)
            pending = {use: component[use]["decision"] for use in USES
                       if component[use]["decision"] != "approved"}
            unknown_license = component["observed_license"] is None
            if pending or unknown_license:
                reasons = []
                if unknown_license:
                    reasons.append("observed license is unknown")
                if pending:
                    reasons.append("use decisions are not approved: " + ", ".join(
                        f"{use}={decision}" for use, decision in pending.items()))
                add(record_id, "use_restriction", f"rights_by_component[{index}]",
                    f"{component['source_id']}:{component['component']}", "; ".join(reasons) + ".",
                    "A component-specific rights basis and separate reviewed decision for every intended use.",
                    "Resolve each use independently; do not treat research access or another component's license as permission.",
                    uses={use: component[use] for use in USES})
        for index, issue in enumerate(record["review"]["unresolved_issues"]):
            add(record_id, "record_review", f"review.unresolved_issues[{index}]", f"issue-{index + 1}",
                issue, "Evidence or qualified review responsive to the recorded issue.",
                "Resolve or explicitly retain this issue in a separately reviewed record; do not edit the v1 draft in place.")

    identifiers = [item["issue_id"] for item in gaps]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Derived issue IDs are not unique")
    return gaps


def build_review_export(root=ROOT, directory=None, inventory_path=None, mapping_path=None):
    lexical_root = Path(root).absolute()
    root = lexical_root.resolve()
    def input_path(value, default, prefixes):
        candidate = Path(value) if value is not None else root / default
        if candidate.is_absolute() and candidate.is_relative_to(lexical_root):
            candidate = root / candidate.relative_to(lexical_root)
        return confined_path(root, candidate, prefixes)

    directory = input_path(directory, PRIVATE_DRAFTS, ("data/evidence",))
    inventory_path = input_path(inventory_path, INVENTORY, ("manifests",))
    mapping_path = input_path(mapping_path, REFERENCE_MAP, ("manifests",))
    inventory = strict_load(inventory_path)
    expected_rows = inventory["records"]
    expected_ids = [item["id"] for item in expected_rows]
    if len(set(expected_ids)) != len(expected_ids) or inventory["record_count"] != len(expected_ids):
        raise ValueError("Inventory record IDs/count are inconsistent")

    audit = audit_directory(root, directory)
    if audit["status"] != "drafts_valid":
        raise ValueError("Draft validation failed: " + json.dumps(
            {row.get("file", "unknown"): row["errors"] for row in audit["records"] if row["errors"]},
            sort_keys=True))
    audit_by_id = {item["id"]: item for item in audit["records"]}
    if len(audit_by_id) != len(audit["records"]) or set(audit_by_id) != set(expected_ids):
        raise ValueError("Validated draft set differs from the eight-record inventory")

    records = []
    record_hashes = {}
    inventory_by_id = {item["id"]: item for item in expected_rows}
    markdown_hashes = {}
    for record_id in expected_ids:
        audit_row = audit_by_id[record_id]
        expected = inventory_by_id[record_id]
        path = confined_path(root, directory / audit_row["file"], ("data/evidence",))
        if path.is_symlink() or path.parent != directory:
            raise ValueError("Draft path is unsafe")
        if audit_row["sha256"] != expected["draft_json_sha256"]:
            raise ValueError(f"Inventory draft hash mismatch: {record_id}")
        markdown = path.with_suffix(".md")
        if not markdown.is_file() or markdown.is_symlink():
            raise ValueError(f"Missing or unsafe Markdown companion: {record_id}")
        markdown_digest = sha256(markdown)
        if markdown_digest != expected["readable_markdown_sha256"]:
            raise ValueError(f"Inventory Markdown hash mismatch: {record_id}")
        records.append(strict_load(path))
        record_hashes[record_id] = audit_row["sha256"]
        markdown_hashes[record_id] = markdown_digest

    mapping = strict_load(mapping_path)
    mapped = validate_reference_mapping(mapping, records, record_hashes)
    exported_records = []
    for record in records:
        record_id = record["id"]
        citation_state = {}
        local_matches = set(audit_by_id[record_id]["locally_matched_citation_hashes"])
        local_missing = set(audit_by_id[record_id]["claimed_hashes_without_local_bytes"])
        for citation in record["citations"]:
            citation_state[citation["id"]] = (
                "matched" if citation["id"] in local_matches else
                "missing" if citation["id"] in local_missing else "not_pinned"
            )
        exported_records.append({
            "id": record_id,
            "kind": record["kind"],
            "status": record["status"],
            "biblical_anchor_languages": record["biblical_anchor_languages"],
            "summary": record["summary"],
            "source_record": {
                "json_sha256": record_hashes[record_id],
                "markdown_sha256": markdown_hashes[record_id],
            },
            "reference_mapping": [mapped[(record_id, key)] for key in record["chapter_keys"]],
            "mapped_references": record["mapped_references"],
            "mapping_citation_ids": record["mapping_citation_ids"],
            "citations": [{**citation, "local_source_bytes": citation_state[citation["id"]]}
                          for citation in record["citations"]],
            "readings": record["readings"],
            "dates": record["dates"],
            "claims": record["claims"],
            "coverage_limits": record["coverage_limits"],
            "rights_by_component": record["rights_by_component"],
            "review": record["review"],
        })
    gaps = derive_gap_queue(records, audit_by_id)
    gap_counts = Counter(item["reason_category"] for item in gaps)
    return {
        "schema_version": 1,
        "id": "evidence-review-export-v1",
        "status": "private_review_aid_only",
        "source_inventory": {"path": inventory_path.relative_to(root).as_posix(), "sha256": sha256(inventory_path)},
        "reference_mapping": {"path": mapping_path.relative_to(root).as_posix(), "sha256": sha256(mapping_path),
                              "review": mapping["review"], "limitations": mapping["limitations"]},
        "record_count": len(exported_records),
        "records": exported_records,
        "gap_queue": gaps,
        "gap_counts": dict(sorted(gap_counts.items())),
        "app_approved": 0,
        "training_approved": 0,
        "expert_certified": False,
        "model_calls": 0,
        "limitations": [
            "This deterministic export is a review aid, not scholarly certification or a use-eligibility registry.",
            "A matching source hash binds bytes; it does not verify a locator, reading, claim, or right to use the component.",
            "Pending, unknown, not-approved, or conflicting rights never become implied permission.",
            "The source drafts and their Markdown companions remain unchanged.",
        ],
    }


def _anchor(*values):
    encoded = []
    for value in values:
        token = base64.urlsafe_b64encode(str(value).encode("utf-8")).decode("ascii").rstrip("=")
        encoded.append(f"{len(token)}-{token}")
    return "a-" + "-".join(encoded)


def _e(value):
    if value is None:
        return "<span class=\"null\">null</span>"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return html.escape(str(value), quote=True)


def _refs(record_id, citation_ids):
    if not citation_ids:
        return "<span class=\"null\">none</span>"
    return ", ".join(f'<a href="#{_anchor(record_id, "citation", cid)}">{_e(cid)}</a>' for cid in citation_ids)


def _claim_refs(record_id, claim_ids):
    if not claim_ids:
        return "<span class=\"null\">none</span>"
    return ", ".join(f'<a href="#{_anchor(record_id, "claim", claim_id)}">{_e(claim_id)}</a>'
                     for claim_id in claim_ids)


def _table(headers, rows):
    head = "".join(f"<th>{_e(item)}</th>" for item in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render_html(export):
    """Render an escaped, standalone review index with resolvable local anchors."""
    parts = ["""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evidence review export v1</title><style>
body{font:15px/1.45 system-ui,sans-serif;max-width:1500px;margin:auto;padding:2rem;color:#202124}.table-wrap{overflow-x:auto;margin:1rem 0 2rem}table{border-collapse:collapse;width:100%;min-width:850px}th,td{border:1px solid #bbb;padding:.45rem;vertical-align:top;text-align:left}th{background:#eee;position:sticky;top:0}code{overflow-wrap:anywhere}.null{color:#755;font-style:italic}.warning{background:#fff3cd;padding:1rem}a{color:#0645ad}h2{border-top:3px solid #555;padding-top:1.5rem}ul{margin-top:.25rem}details{margin:1rem 0}summary{cursor:pointer;font-weight:600}
</style></head><body><h1>Evidence review export v1</h1>"""]
    parts.append('<p class="warning">Private review aid only. It does not certify scholarship or approve app, training, redistribution, or adapter use.</p>')
    parts.append(f"<p>Records: {_e(export['record_count'])}. Open gaps: {_e(len(export['gap_queue']))}. Model calls: 0.</p>")
    record_links = " · ".join(f"<a href=\"#{_anchor('record', record['id'])}\">{_e(record['id'])}</a>"
                              for record in export["records"])
    gap_summary = " · ".join(f"{_e(category)}: {_e(count)}"
                              for category, count in export["gap_counts"].items())
    parts.append(f"<nav><strong>Records:</strong> {record_links}</nav>")
    parts.append(f"<p><strong>Gap categories:</strong> {gap_summary}</p>")
    parts.append("<h2 id=\"gap-queue\">Gap queue</h2>")
    gap_rows = []
    for gap in export["gap_queue"]:
        record_id = gap["record_id"]
        gap_rows.append([
            f'<a id="{_anchor("gap", gap["issue_id"])}"></a><code>{_e(gap["issue_id"])}</code>',
            f'<a href="#{_anchor("record", record_id)}">{_e(record_id)}</a>',
            f"<code>{_e(gap['affected']['field_path'])}</code> / {_e(gap['affected'].get('item_id'))}",
            _e(gap["reason_category"]), _e(gap["reason"]), _e(gap["evidence_needed"]),
            _e(gap["next_action"]), _e(gap["status"]),
        ])
    parts.append(f"<details><summary>Show all {_e(len(gap_rows))} gap rows</summary>" +
                 _table(("Issue", "Record", "Field / item", "Category", "Reason", "Evidence needed", "Next action", "Status"), gap_rows) +
                 "</details>")

    for record in export["records"]:
        rid = record["id"]
        record_anchor = _anchor("record", rid)
        parts.append(f'<h2 id="{record_anchor}">{_e(rid)} — {_e(record["kind"])}</h2>')
        parts.append(f"<p>{_e(record['summary'])}</p><p><code>records/{_e(rid)}</code>; source JSON {_e(record['source_record']['json_sha256'])}</p>")
        mapping_rows = []
        for index, item in enumerate(record["reference_mapping"]):
            mapping_rows.append([f'<a href="#{record_anchor}">{_e(rid)}</a>', f"<code>reference_mapping[{index}]</code>",
                                 _e(item["original_chapter_key"]), _e(item["normalized_chapter_key"]),
                                 _e(item["source_id"]), _e(item["edition"]), _e(item["edition_coordinate"]),
                                 _refs(rid, item["mapping_citation_ids"]), _e(item["note"])])
        parts.append("<h3>Reviewed reference mapping</h3>" + _table(
            ("Record", "Field", "Original key", "Normalized key", "Source", "Edition", "Edition coordinate", "Citations", "Note"), mapping_rows))
        mapped_reference_rows = [
            [f'<a href="#{record_anchor}">{_e(rid)}</a>', f"<code>mapped_references[{index}]</code>",
             _e(value), _refs(rid, record["mapping_citation_ids"])]
            for index, value in enumerate(record["mapped_references"])
        ]
        if not mapped_reference_rows:
            mapped_reference_rows.append([
                f'<a href="#{record_anchor}">{_e(rid)}</a>', "<code>mapped_references</code>",
                _e("No additional mapped reference entered"), _refs(rid, record["mapping_citation_ids"]),
            ])
        parts.append("<h3>Draft mapped references and qualifications</h3>" + _table(
            ("Record", "Field", "Mapped reference / qualification", "Draft mapping citations"), mapped_reference_rows))

        citation_rows = []
        for index, citation in enumerate(record["citations"]):
            cid = citation["id"]
            citation_rows.append([
                f'<a href="#{record_anchor}">{_e(rid)}</a>',
                f'<a id="{_anchor(rid, "citation", cid)}"></a><code>citations[{index}]/{_e(cid)}</code>',
                _e(citation["source_id"]), _e(citation["kind"]), _e(citation["title"]),
                _e(citation["locator"]), f'<a href="{_e(citation["url"])}">source</a>',
                _e(citation["pinned_version"]), _e(citation["content_sha256"]), _e(citation["local_source_bytes"]),
            ])
        parts.append("<h3>Citations</h3>" + _table(
            ("Record", "Field / citation", "Source ID", "Kind", "Title", "Locator", "URL", "Pinned version", "content_sha256", "Local bytes"), citation_rows))

        claim_rows = []
        for index, claim in enumerate(record["claims"]):
            claim_id = claim["id"]
            claim_rows.append([
                f'<a href="#{record_anchor}">{_e(rid)}</a>',
                f'<a id="{_anchor(rid, "claim", claim_id)}"></a><code>claims[{index}]/{_e(claim_id)}</code>',
                _e(claim["kind"]), _e(claim["text"]), _refs(rid, claim["supporting_citation_ids"]),
                _refs(rid, claim["contrary_citation_ids"]), _claim_refs(rid, claim["alternative_claim_ids"]),
                _e(claim["assessment"]), _e(claim["limitations"]),
            ])
        parts.append("<h3>Claims</h3>" + _table(
            ("Record", "Field / claim", "Kind", "Claim", "Supporting citations", "Contrary citations",
             "Alternative claims", "Assessment", "Limitations"), claim_rows))

        reading_rows = []
        for index, reading in enumerate(record["readings"]):
            reading_rows.append([
                f'<a href="#{record_anchor}">{_e(rid)}</a>', f"<code>readings[{index}]/{_e(reading['id'])}</code>",
                _e(reading["entity_type"]), _e(reading["stable_entity_id"]), _e(reading["edition_or_transcription"]),
                _e(reading["hand"]), _e(reading["original_representation"]), _e(reading["english_rendering"]),
                _e(reading["rendering_author"]), _e(reading["attestation"]), _refs(rid, reading["citation_ids"]),
                _e(reading["encoding_notes"]),
            ])
        parts.append("<h3>Readings and attestation</h3>" + _table(
            ("Record", "Field / reading", "Entity", "Stable entity ID", "Edition/transcription", "Hand", "Original", "English", "Rendering author", "Attestation", "Citations", "Encoding notes"), reading_rows))

        date_rows = []
        for category in DATE_CATEGORIES:
            values = record["dates"][category]
            if not values:
                date_rows.append([f'<a href="#{record_anchor}">{_e(rid)}</a>', f"<code>dates.{_e(category)}</code>",
                                  _e(category), _e(None), _e(None), _e("No assertion entered"), _e(""), _e(""), _e([])])
            for index, value in enumerate(values):
                date_rows.append([f'<a href="#{record_anchor}">{_e(rid)}</a>', f"<code>dates.{_e(category)}[{index}]</code>",
                                  _e(category), _e(value["earliest"]), _e(value["latest"]), _e(value["display_label"]),
                                  _e(value["method"]), _e(value["uncertainty"]), _refs(rid, value["citation_ids"])])
        parts.append("<h3>Four date categories</h3>" + _table(
            ("Record", "Field", "Category", "Earliest", "Latest", "Display", "Method", "Uncertainty", "Citations"), date_rows))

        rights_rows = []
        for index, item in enumerate(record["rights_by_component"]):
            rights_rows.append([
                f'<a href="#{record_anchor}">{_e(rid)}</a>', f"<code>rights_by_component[{index}]</code>",
                _e(item["source_id"]), _e(item["component"]), _e(item["observed_license"]),
                _e(item["rights_url"]), _e(item["rights_notice_sha256"]),
                *[_e(item[use]) for use in USES],
            ])
        parts.append("<h3>Component-use rights</h3>" + _table(
            ("Record", "Field", "Source", "Component", "Observed license", "Rights URL", "Notice hash",
             "Research access", "App display", "Redistribution", "Training", "Adapter release"), rights_rows))

        unresolved_rows = [[f'<a href="#{record_anchor}">{_e(rid)}</a>',
                            f"<code>review.unresolved_issues[{index}]</code>", _e(issue)]
                           for index, issue in enumerate(record["review"]["unresolved_issues"])]
        coverage_rows = [[f'<a href="#{record_anchor}">{_e(rid)}</a>',
                          f"<code>coverage_limits[{index}]</code>", _e(issue)]
                         for index, issue in enumerate(record["coverage_limits"])]
        parts.append("<h3>Unresolved review issues</h3>" + _table(("Record", "Field", "Issue"), unresolved_rows))
        parts.append("<h3>Coverage limits</h3>" + _table(("Record", "Field", "Limit"), coverage_rows))
    parts.append("</body></html>\n")
    return "".join(parts)


def write_export(export, out_dir, root=ROOT):
    lexical_root = Path(root).absolute()
    root = lexical_root.resolve()
    out_dir = Path(out_dir)
    destination_input = out_dir
    if out_dir.is_absolute() and out_dir.is_relative_to(lexical_root):
        destination_input = root / out_dir.relative_to(lexical_root)
    destination = confined_path(root, destination_input, ("runs", "data/evidence"))
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing output directory: {destination}")
    destination.mkdir(parents=True, mode=0o700)
    json_text = json.dumps(export, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    html_text = render_html(export)
    for name, content in (("review.json", json_text), ("index.html", html_text)):
        path = destination / name
        with path.open("x", encoding="utf-8") as output:
            output.write(content)
        path.chmod(0o600)
    return {
        "output_directory": destination.relative_to(root).as_posix(),
        "json_sha256": sha256(destination / "review.json"),
        "html_sha256": sha256(destination / "index.html"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, help="Draft directory under data/evidence")
    parser.add_argument("--reference-map", type=Path, help="Reviewed mapping under manifests")
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="New private output directory under runs or data/evidence")
    args = parser.parse_args(argv)
    try:
        export = build_review_export(directory=args.directory, mapping_path=args.reference_map)
        receipt = write_export(export, args.out_dir)
    except (FileExistsError, OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({**receipt, "record_count": export["record_count"],
                      "gap_count": len(export["gap_queue"]), "gap_counts": export["gap_counts"],
                      "model_calls": 0}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
