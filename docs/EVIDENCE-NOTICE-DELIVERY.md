# Evidence notice delivery

`bibleprep.evidence_delivery` is an offline bridge between exact evidence components and a future private evidence display. It preserves factual content, citations, coverage limits, attribution, license facts, change notices, and disclaimers. It does not change the existing eligibility registry, formatter, private chat, model transport, or training pipeline.

The bridge uses two separate stages so a use approval can cite a stable candidate without the candidate depending on that approval:

1. `build_candidate_bundle(...)` validates the complete registry and source dependencies, requires approved scholarly review for the selected components, validates the notice manifest, and returns a deterministic artifact with status `prepared_not_authorized`. Registry identity, registry hash, registry status, and all use decisions are excluded from the candidate.
2. `verify_for_use(...)` regenerates the candidate, builds a fresh `app_display` projection from the current registry, and requires every selected component and its exact record, content, citation, source, and scholarly-review closure to be present. It also requires every selected app-display decision to bind the supplied manifest through supporting evidence with ID `delivery-notice-manifest`. The returned wrapper binds the current registry hash.

Candidate preparation can therefore precede an app-display decision without approving itself. Changing notice prose requires a new candidate and a corresponding use decision bound to that exact manifest. A saved or caller-constructed verification wrapper is not an authorization token: `public_delivery_payload`, `render_model_input`, and `render_display` all require the current registry and notice manifest and repeat the complete use verification before rendering.

## API

```python
from bibleprep.evidence_delivery import (
    build_candidate_bundle,
    public_delivery_payload,
    render_display,
    render_model_input,
    verify_candidate_bundle,
    verify_for_use,
    write_private_json,
)

candidate = build_candidate_bundle(
    registry,
    ["GT01/claim-GT-A1", "GT01/reading-GT-R1"],
    notice_manifest,
    root=project_root,
    record_directory=record_directory,
)

verify_candidate_bundle(
    candidate, registry, notice_manifest,
    root=project_root, record_directory=record_directory,
)

verified = verify_for_use(
    candidate, reviewed_registry, notice_manifest,
    root=project_root, record_directory=record_directory,
)

model_evidence = render_model_input(
    verified, reviewed_registry, notice_manifest,
    root=project_root, record_directory=record_directory,
)
display_markdown = render_display(
    verified, reviewed_registry, notice_manifest,
    root=project_root, record_directory=record_directory,
)
```

`record_directory` defaults to the existing private v1 draft directory. Inputs are in-memory objects; callers can use the existing duplicate-key and nonfinite-value rejecting `strict_load` helper when loading JSON.

`write_private_json` writes either candidate or verified artifacts below `runs/` or `data/evidence/`. It creates new directories with mode `0700` and files with mode `0600`, refuses overwrite, and rejects symlink traversal. There is no CLI and no network, environment, credential, tokenizer, model, or transport access.

## Notice manifest v1

The manifest has exactly four top-level fields:

```json
{
  "schema_version": 1,
  "notice_manifest_id": "stable-versioned-id",
  "notices": [],
  "limitations": []
}
```

Each notice has exactly these fields:

```json
{
  "notice_id": "stable-notice-id",
  "record_id": "GT01",
  "source_id": "sblgnt",
  "rights_component": "source_text",
  "rights_fact_sha256": "<canonical rights-fact hash>",
  "rights_snapshot_path": "data/raw/.../LICENSE.txt",
  "applies_to_component_keys": ["GT01/claim-GT-A1"],
  "license_notice": "User-visible license and source notice.",
  "disclaimer": "User-visible limitation and no-endorsement notice."
}
```

`rights_fact_sha256` hashes this exact allowlist from the matching record `rights_by_component` row, using UTF-8 JSON with sorted keys, compact separators, unescaped Unicode, and no nonfinite numbers:

```json
{
  "source_id": "...",
  "component": "...",
  "observed_license": "... or null",
  "rights_url": "... or null",
  "rights_notice_sha256": "... or null",
  "attribution": "...",
  "change_notice": "..."
}
```

Per-use decisions are intentionally outside that hash. When `rights_notice_sha256` is non-null, `rights_snapshot_path` must name a confined, nonsymlink file below `data/raw/` or `licenses/` whose bytes have that hash. A null rights hash requires a null snapshot path.

For every citation source used by a selected component, the manifest must apply a notice for every `rights_by_component` row with that source ID. This prevents a source-text notice from masking a separate annotation license or attribution. Duplicate notice IDs and duplicate component/source/rights-component bindings fail. A manifest may cover more known components than a particular candidate; a subset candidate includes only notices and content applicable to its selected components.

Manifest `limitations` are private workflow metadata bound by the manifest hash. They are never copied into model input or display output.

## Candidate and rendered content

The candidate binds:

- exact record and component hashes and complete selected field objects;
- complete citation objects plus citation and source dependency hashes;
- the canonical hash of each complete scholarly-review decision, without exposing reviewer fields or supporting-review paths;
- exact displayable rights facts and their hashes;
- the canonical notice-manifest hash; and
- one aggregate implementation hash over `evidence.py`, `evidence_eligibility.py`, and `evidence_delivery.py`.

The selected objects remain unchanged. Claim assessments, attributed positions, limitations, supporting and contrary citations, alternative-claim closure, original-language representations, attestations, translations, and encoding notes therefore remain attached. Original-language characters and trailing spaces survive candidate construction and the JSON model rendering.

The public payload contains only record IDs, record coverage limits, complete selected factual objects, public citation fields, and the source-notice fields. It excludes component and source hashes, filesystem paths, reviewer identities and roles, review evidence, registry metadata, use-decision metadata, manifest workflow limitations, questions, criteria, and expected answers. Its public status is `supplied_source_material`; it does not describe the source assertions as independently verified.

`render_model_input` places compact Unicode JSON between fixed `SUPPLIED_EVIDENCE_DATA` delimiters and states that every nested value is evidence data or a source notice, never an instruction. `render_display` escapes untrusted text and explicitly shows the observed license, rights URL, license notice, attribution, change notice, and disclaimer.

## Authorization boundary

Candidate and verified artifacts always set `generation_authorized` and `training_authorized` to `false`. A verified wrapper records only that the exact evidence bundle currently passes the separate `app_display` eligibility decision. It does not authorize a provider request, answer generation, training, redistribution, adapter release, deployment, or publication.

Training remains on explicit hold. Before any future training work, the owner must be notified, supply an additional research topic, receive research and a revised plan, and then give a separate training go-ahead. This delivery module cannot satisfy or bypass those steps.

The checks establish internal byte, hash, notice, and decision consistency. They do not establish factual truth, reviewer expertise, legal clearance, or application compliance. No application is changed by this module.
