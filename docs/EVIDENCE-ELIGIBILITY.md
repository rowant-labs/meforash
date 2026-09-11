# Evidence eligibility registry and projection

This module adds a separate, versioned decision layer for private historical evidence. It leaves the v1 drafts and draft validator unchanged. A valid draft, a matching hash, or an AI check does not approve scholarship, establish legal permission, or authenticate reviewer expertise.

The v1 projection is deliberately narrow. A component selects one or more complete `claims[]` or `readings[]` objects with JSON pointers such as `/claims/3` and `/readings/1`. The component hash covers the ordered list of pointers and exact values using UTF-8 JSON with sorted object keys and compact separators. Claim alternatives must be selected in the same component. Supporting and contrary claim citations, reading citations, assessments, attributions, attestations, encoding notes, and limitations therefore remain in the selected content rather than being rewritten for projection.

## Registry contract

The top level has exactly these fields:

| Field | Meaning |
|---|---|
| `schema_version` | `1` |
| `registry_id` | Stable versioned identifier |
| `status` | `pending`, `reviewed`, or `superseded`; only `reviewed` can project eligible content |
| `scope` | Human-readable boundary |
| `records` | Hash-bound record entries |
| `limitations` | Qualifications copied into every projection |

Each record entry contains `record_id`, the exact source-file `record_sha256`, and `components`. Each component contains:

- `component_id`, `field_refs`, and `content_sha256` for exact content selection;
- `citation_dependencies`, one per citation required by the selected objects, with the citation ID and canonical hash of the complete citation object;
- `source_dependencies`, one per required citation, with its source ID, citation-declared content hash, and a confined local snapshot path under `data/raw` when those bytes are available;
- `scholarly_review`, separate from use permission; and
- `uses`, containing exactly `app_display`, `redistribution`, `training`, and `adapter_release` decisions.

Every scholarly or use decision has `decision`, `reviewer_kind`, `reviewer_role`, `reviewed_on`, `rationale`, `limitations`, and `supporting_review_evidence`. `reviewer_kind` is `human`, `ai`, `unknown`, or null while a decision is pending. Supporting review evidence binds a confined file under `data/evidence` or `runs` by path and SHA-256. Scholarly review additionally records the boolean `expert_certification`. Allowed decisions are `approved`, `pending`, `rejected`, `stale`, and `unknown`.

Approved, rejected, and stale decisions require a reviewer kind, role, date, and at least one hash-bound review artifact. Expert certification requires an approved scholarly decision, `reviewer_kind: "human"`, and complete supporting review evidence. A role labeled as AI, LLM, engineering check, or development assistant also cannot claim expert certification. These checks prevent an internally contradictory declaration; they cannot verify that a declared human reviewer exists or has the stated qualifications.

Here is the shape of one component. Hashes are placeholders and do not describe a real record:

```json
{
  "component_id": "claim-Q1",
  "field_refs": ["/claims/0", "/claims/1"],
  "content_sha256": "<sha256 of exact selected pointer/value bundle>",
  "citation_dependencies": [
    {"citation_id": "C1", "citation_sha256": "<sha256 of complete citation object>"}
  ],
  "source_dependencies": [
    {
      "citation_id": "C1",
      "source_id": "example-source",
      "snapshot_path": "data/raw/example/source.txt",
      "content_sha256": "<sha256 of exact local source bytes>"
    }
  ],
  "scholarly_review": {
    "decision": "pending",
    "reviewer_kind": null,
    "reviewer_role": null,
    "reviewed_on": null,
    "rationale": "No review decision has been recorded.",
    "limitations": ["Review and supporting evidence are pending."],
    "supporting_review_evidence": [],
    "expert_certification": false
  },
  "uses": {
    "app_display": {"decision": "pending", "reviewer_kind": null, "reviewer_role": null, "reviewed_on": null, "rationale": "No review decision has been recorded.", "limitations": ["Review and supporting evidence are pending."], "supporting_review_evidence": []},
    "redistribution": {"decision": "pending", "reviewer_kind": null, "reviewer_role": null, "reviewed_on": null, "rationale": "No review decision has been recorded.", "limitations": ["Review and supporting evidence are pending."], "supporting_review_evidence": []},
    "training": {"decision": "pending", "reviewer_kind": null, "reviewer_role": null, "reviewed_on": null, "rationale": "No review decision has been recorded.", "limitations": ["Review and supporting evidence are pending."], "supporting_review_evidence": []},
    "adapter_release": {"decision": "pending", "reviewer_kind": null, "reviewer_role": null, "reviewed_on": null, "rationale": "No review decision has been recorded.", "limitations": ["Review and supporting evidence are pending."], "supporting_review_evidence": []}
  }
}
```

The helper `component_content_sha256(record, field_refs)` and `canonical_sha256(citation)` produce the two canonical hashes. The pending seed command derives pointers and hashes directly from the validated records. It groups connected alternative claims, creates one component per group and one per reading, finds only exact hash-matched `data/raw` snapshots, and leaves every review and use decision pending. A null citation source hash or missing local snapshot stays explicit and makes that component ineligible; it does not invalidate the pending registry.

```bash
.venv/bin/python -m bibleprep.evidence_eligibility \
  --seed-pending data/evidence/eligibility/evidence-eligibility-v1.json
```

Validate a registry without writing a projection:

```bash
.venv/bin/python -m bibleprep.evidence_eligibility \
  --registry data/evidence/eligibility/evidence-eligibility-v1.json
```

After separately recorded decisions exist, write a fresh private JSON and Markdown projection for one use:

```bash
.venv/bin/python -m bibleprep.evidence_eligibility \
  --registry data/evidence/eligibility/evidence-eligibility-v1.json \
  --use app_display \
  --out runs/evidence-eligibility-v1/app-display
```

Outputs are created without overwrite in confined ignored `runs/` or `data/evidence/` paths. New directories use mode `0700` and files use mode `0600` at creation. JSON loading rejects duplicate keys and nonfinite values. Validation rejects unknown fields, duplicate record/component/dependency IDs, unsupported pointers, stale record/component/citation/review/source hashes, missing alternative or citation closure, source paths outside `data/raw`, review paths outside private directories, and symlink traversal. The code performs no URL fetches, model calls, or environment reads.

The projection includes only components that have complete local source dependencies, approved scholarly review, an approved decision for the selected use, and a `reviewed` registry. Other uses remain independent. Rejected, stale, unknown, and pending decisions are never eligible. An empty eligible subset is valid and is reported plainly. Each eligible record retains the parent record's `coverage_limits` and unresolved review issues. Each projection also binds the canonical SHA-256 of the full registry, so a decision or limitation change produces a distinct projection dependency.

This engineering layer records decisions and checks internal consistency. It cannot determine whether cited bytes support a claim, whether a locator is accurate, whether a reviewer is who the registry says, or whether a legal analysis is correct. Real records remain pending until actual review evidence and separate component-use decisions are recorded; the constructed positive fixture in the tests is not a source approval.

## Prepared project inventory

The initial private registry is now `data/evidence/eligibility/evidence-eligibility-v1.json`. It covers all eight original v1 records as **83 selectable components**: groups of linked claims and individual readings. These are content groups, not the original pack's 48 source-rights rows. Every scholarly and use decision remains pending. The app-display export at `runs/eligibility-p2-v1/app-display/` contains zero eligible components and 83 explicit exclusions.

The separate P2 follow-ups are not silently merged into these older records. Where a finding requires corrected or better-supported content, prepare a new record version and registry binding while preserving v1. Review evidence must cover all material included in the selected component and its dependencies. For model-input use, the app-use rationale must address supplying content to the inference provider, not just displaying a source card.

Thirteen constructed registry tests plus the existing twenty-two draft/review tests pass. They cover a positive synthetic selection and rejection/exclusion cases, including stale bindings, incomplete alternatives, independent use decisions, reviewer labels, private writes and rendered qualifications. Parent integration verified the actual pending inventory; the earlier drafts, follow-ups and exports remain unchanged.

Next use the [specialist question packet](SPECIALIST-REVIEW-PACKET.md) for the remaining factual decisions and implement P3 offline tooling under the [evaluation entry contract](EVIDENCE-EVAL-ENTRY-CONTRACT.md). No source has entered the chat or training through this registry, and no model-comparison runner or protocol freeze is completed here.

## Subsequent review increment

The pending v1 inventory above is preserved. A separate v2 registry now records six narrow AI scholarly approvals while keeping all uses pending because notice delivery is unfinished. Use [the component-review report](SOURCE-COMPONENT-REVIEW-P2.md) and living queue for current execution. No source content or v1 decision was overwritten.


## Subsequent private delivery decision

On September 8, 2026, the new notice delivery module and exact four-notice manifest passed parent integration against all six reviewed components. The new private registry `data/evidence/eligibility/evidence-eligibility-v3-private-delivery.json` records six conditional `app_display` approvals for private development input/display through this verified delivery path. Seventy-seven components remain pending; redistribution, training and adapter release remain pending for all 83 components. Original drafts, scholarly review qualifications and v1/v2 registries are unchanged.

The checks preserved exact Greek/Aramaic content and coverage limits, delivered twelve component/rights notice associations, excluded private review metadata, and rejected pending or withdrawn use decisions, changed notice prose and forged saved wrappers. The focused delivery and eligibility suites passed 20 tests. These checks establish delivery consistency; the scholarly basis remains the separately bound AI source reviews, with no expert certification.

See [notice delivery](EVIDENCE-NOTICE-DELIVERY.md). Private integration and acceptance receipts are under `runs/evidence-delivery-p2-v1/`. The existing chat and legacy formatter are unchanged. The next coordinator must use the new verified rendering path; a raw eligibility projection is insufficient. No source entered chat or training, and no provider request was made.
