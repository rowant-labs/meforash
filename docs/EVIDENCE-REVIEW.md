# Private evidence review export v1

Prepared September 7, 2026. The offline review export covers the eight hash-bound drafts in `evidence-first-pack-v1`. It is a deterministic review aid and issue queue. It does not certify a claim, approve a component for use, add evidence to the chat, or create training data.

## Run it

Install the evidence-validation requirements, then choose a new ignored output directory:

```sh
.venv/bin/python -m pip install -r requirements-evidence.txt
.venv/bin/python -m bibleprep.evidence_review --out-dir runs/evidence-review-v1
.venv/bin/python -m unittest tests.test_evidence_review -v
```

The output directory must be new and remain under `runs/` or `data/evidence/`. The command refuses overwrite, path escapes, and symlinked research paths. It reads no environment file, fetches no URL, and makes no provider or model call. The generated `review.json` and standalone `index.html` are private because they reproduce unreviewed research content.

The generated packet contains all eight records exactly once. It retains 45 citations, 52 claims, 36 readings, four separate date categories per record, 48 component-rights rows, and all 29 draft review issues. Its 130-row derived queue contains review tasks, not 130 established factual errors:

| Gap category | Count | Meaning |
|---|---:|---|
| Missing source bytes | 14 | `content_sha256` remains null. |
| Missing immutable version | 14 | `pinned_version` remains null. |
| Unchecked attestation | 9 | An identified witness or version has not been checked directly. |
| Qualified attestation | 1 | Damage, supply, or uncertainty must remain explicit. |
| Scholarly judgment | 15 | A claim is disputed, uncertain, or has insufficient evidence. |
| Component-use restriction | 48 | Unknown license or at least one non-approved use decision; each use and basis remains separate. |
| Recorded review issue | 29 | The draft's own `review.unresolved_issues` entry. |

Some rows intentionally overlap. A citation can lack both local bytes and an immutable version, while a draft's authored review issue can describe the same research problem in fuller terms. The stable field paths and IDs preserve both machine-derived and author-recorded provenance.

## Reference mapping

The public `manifests/evidence-reference-map-v1.json` supplies nine explicit chapter-anchor mappings. Each entry binds the original `chapter_keys` value to the exact draft hash, a normalized biblical chapter key, and a source/edition coordinate with citation IDs. This handles bare `Ezra.4` and `Dan.2` keys without treating them as raw-string matches to source-prefixed OSHB or SBLGNT keys.

The mapping review is labeled `ai_engineering_coordinate_check`; `specialist_certification` is false. The loader rejects missing or duplicate entries, draft-hash drift, unresolved citations, wrong source/edition prefixes, and inconsistent original, normalized, or edition chapter coordinates. Future mappings between versifications or editions require a separately designed and reviewed mapping rather than loosening this v1 check.

## Review behavior and limits

The export first runs the existing draft schema, cross-reference, date, rights, and local source-byte audit. It verifies the public inventory hashes for each JSON draft and Markdown companion. Null citation hashes remain null, and a matching hash is reported only as local byte availability. It does not interpret that match as verification of the locator or claim.

The HTML escapes every record value, uses collision-free anchors for records, claims, and citations, links claim support, contrary evidence, and alternatives, and contains wide tables in horizontal scrolling regions. Its gap queue is collapsed initially, with category counts and direct links to every record at the top.

Rights gaps are grouped by source component while retaining the five distinct decisions and bases: research access, app display, redistribution, training, and adapter release. Pending, unknown, not-approved, or conflicting rights never become implied permission. The export always reports zero app approvals, zero training approvals, and no expert certification.

The initial private output is preserved at `runs/evidence-review-v1/`: `review.json` SHA-256 `27b4bb771cd1546f00ed60694aea965d52160d47b6e036f476775d242d8a5348`; `index.html` SHA-256 `7d34e4e6cece4f1a4a2d23a13d913129aee2a517f3625bcf3d3174e2016f73e1`. The final packet, including the completed readability and provenance fixes, is `runs/evidence-review-v1/final/`: its JSON hash is unchanged and its `index.html` SHA-256 is `7b1c57b9821cd373f27d8c3a88b0fdabc479c6b114f1cfd604b22279fc424c19`. All sixteen v1 JSON/Markdown source hashes were unchanged after generation.
