# Offline blinded review for constructed evidence fixtures

Prepared September 8, 2026. `bibleprep/evidence_blinded_review.py` implements the
receipt-bound review increment that follows the constructed evidence planner and
normalized collection auditor. It is file-based and offline. It does not call a
model, read credentials or environment configuration, approve source material,
certify expertise, choose a model, or promote an evidence feature.

This tool accepts only criteria labeled `fixture_kind: "constructed"`. It does
not authorize live generation or turn a planning fixture into a fresh benchmark.
Questions, criteria, answers, reviews, and the private identity key remain under
ignored `runs/` paths until a separate disclosure decision is recorded.

## Inputs and masking boundary

`build_review_artifacts(planned_slots, journal, criteria)` recomputes
`audit_collection(planned_slots, journal)`. It does not accept or trust a saved
aggregate. Every nonblank returned final answer is included exactly once,
including `output_limit` and `incomplete` partials. Exact UTF-8 answer hashes and
the normalized native receipt hashes travel with each candidate.

The criteria document must exactly cover the planned case IDs and must agree
with every arm's question and `general_control` flag:

```json
{
  "schema_version": 1,
  "suite_id": "constructed-review-suite-v1",
  "fixture_kind": "constructed",
  "cases": [
    {
      "case_id": "case-one",
      "question": "A constructed question",
      "general_control": false,
      "scoring_criteria": ["A constructed source-based criterion."],
      "reviewer_instructions": ["Accept a stated constructed alternative."]
    }
  ]
}
```

The review packet carries that complete neutral document and its canonical hash.
Each candidate also carries its case-specific criteria hash. The packet contains
no arm field, slot ID, label map, eligibility registry, evidence projection,
source-workflow decision, or local path. Candidate IDs and order come from
HMAC-SHA256 with a fresh 256-bit system secret. The secret is stored only in the
private label map, which binds the exact planned inventory, journal, criteria,
slot, arm, answer, stop status, and receipt hashes. Supplying a secret explicitly
is supported for constructed tests; ordinary callers should omit it.

Masking cannot hide what an answer says. A candidate may mention that evidence
was supplied or otherwise reveal its treatment. This is procedural label and
order concealment, not a guarantee that a reviewer cannot infer a condition.
Paired preference judging is explicitly `not_implemented` in this bounded
increment.

`write_review_artifacts(packet, label_map, output_directory)` writes
`review-packet.json` and `private-label-map.json` to a new directory under
`runs/`. The directory is mode `0700` and files are mode `0600`. Existing paths,
path escapes, symlink ancestors, and overwrite attempts are rejected.

## Review and freeze

The reviewer supplies one structured assessment for every candidate:

```json
{
  "schema_version": 1,
  "artifact_kind": "frozen_blinded_review",
  "review_id": "synthetic-ai-review-v1",
  "packet_sha256": "<canonical packet SHA-256>",
  "reviewer_kind": "ai",
  "reviewer_role": "Synthetic engineering fixture reviewer",
  "conflicts": ["The reviewer shares the engineering project context."],
  "expert_certified": false,
  "assessments": [
    {
      "candidate_id": "candidate-<opaque value>",
      "answer_sha256": "<exact UTF-8 answer SHA-256>",
      "receipt_sha256": "<verified normalized receipt SHA-256>",
      "critical_errors": [],
      "requested_content_omissions": [],
      "general_semantic_pass": null,
      "rationale": "Constructed assessment rationale."
    }
  ],
  "limitations": ["AI fixture review; no real semantic judgment or expertise."]
}
```

`reviewer_kind` is `ai`, `human`, or `mixed`; role and conflicts remain explicit.
This workflow requires `expert_certified: false`. `general_semantic_pass` must be
Boolean for a general control and null for a Bible case. Critical errors and
requested-content omissions remain separate and apply to complete and partial
finals alike.

`validate_and_freeze_review(packet, review, out_path)` verifies exact candidate
coverage plus packet, answer, receipt, criteria, and semantic-field bindings. It
then creates one new private `0600` file with exclusive-create semantics. Its
receipt returns `review_file_sha256`. Keeping that receipt separate makes later
edits detectable; exclusive creation alone cannot prevent another program from
mutating the bytes.

## Integration order and output

Integration requires the freeze receipt hash:

```python
result = integrate_frozen_review(
    planned_slots,
    journal,
    packet,
    frozen_review_path,
    label_map_path,
    expected_frozen_review_file_sha256=freeze_receipt["review_file_sha256"],
    expected_label_map_file_sha256=write_receipt["label_map_file_sha256"],
)
```

The label-map file hash is optional but recommended. Integration proceeds in a
fixed order: recompute collection accounting; validate the packet against every
reviewable final and the complete criteria document; verify the frozen review's
exact file hash; load and validate the review; only then inspect or load the
label map. A stale, edited, incomplete, or otherwise invalid review therefore
fails before unmasking. The secret map is checked by regenerating every opaque
candidate ID, candidate order, and packet ID from its exact slot binding.

The result reports planned, complete, partial, failed, uncertain, outstanding,
unsubmitted, and reviewed counts overall and by arm. Every arm's `planned` count
is its explicit denominator. General-control planned, reviewed, semantic-pass,
and semantic-fail counts are separate; an unsubmitted control stays in the
planned denominator and is not converted into a semantic failure. Critical-error
and omission counts include all reviewable complete and partial answers.

The result always records `decision: "not_assessed_or_authorized"`,
`expert_certified: false`, and `paired_preference: "not_implemented"`. It does
not apply a promotion gate or make a historical-accuracy claim.

## Verification and limits

Run the focused offline tests with:

```sh
.venv/bin/python -m unittest tests.test_evidence_blinded_review -v
```

The constructed tests cover identical answer text without deduplication,
partial-answer retention, stopped-run denominators, criteria/control binding,
opaque random and deterministic seeded identities, exact review coverage,
general semantic typing, private permissions and confinement, forged maps,
post-freeze edits, and the requirement that invalid review data fail before the
label map is read. They make no native request and contain no real evaluation
question or source decision.
