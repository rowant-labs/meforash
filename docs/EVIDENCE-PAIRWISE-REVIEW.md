# Constructed offline pairwise review and collection gate

Prepared September 8, 2026. `bibleprep/evidence_pairwise.py` adds masked paired
preferences and a caller-declared collection-sufficiency gate to the constructed
evidence workflow. It builds on `evidence_collection.py` and
`evidence_blinded_review.py`. It has no API client, model transport, credential or
environment access, source approval, expert certification, quality gate, or
promotion action.

Only `fixture_kind: "constructed"` inputs are accepted. This tooling contains no
real evaluation question or decision and does not authorize generation. Private
questions, answers, pair maps, and reviews remain in ignored `runs/` paths.

## Freeze the collection gate first

The caller prepares exact thresholds against the planned inventory:

```json
{
  "schema_version": 1,
  "artifact_kind": "constructed_collection_gate",
  "gate_id": "constructed-full-collection-v1",
  "fixture_kind": "constructed",
  "planned_slots_sha256": "<canonical planned_slots SHA-256>",
  "minimum_complete_slots_by_arm": {
    "B-memory": 2,
    "B-packet": 2,
    "B-lookup": 2
  },
  "minimum_matched_complete_bible_pairs_by_contrast": {
    "packet_vs_memory": 1,
    "lookup_vs_packet": 1
  },
  "limitations": ["Constructed collection sufficiency only."]
}
```

Thresholds are strict integers, must fit the actual denominators, and must cover
all three core arms and both primary contrasts exactly. Matched-complete Bible
thresholds must be at least one, preventing a zero-case or zero-pair gate from
passing vacuously.

`freeze_collection_gate(planned_slots, criteria, gate, out_path)` validates the
exact inventory, cases, questions, control flags, arms, and thresholds before
exclusively creating a private `0600` file. Its receipt returns
`gate_file_sha256`. The caller can and should freeze it before collection. The
hash binds the bytes but cannot independently prove the time at which they were
created.

## Build the masked pair packet

`build_pair_artifacts` takes the exact planned inventory and normalized journal,
the neutral constructed criteria document used by the single-answer review, and
the frozen gate path and receipt hash:

```python
pair_packet, private_pair_map = build_pair_artifacts(
    planned_slots,
    journal,
    criteria,
    gate_path,
    expected_gate_file_sha256=gate_receipt["gate_file_sha256"],
)
```

Collection accounting is recomputed; saved aggregates are not accepted. Every
planned case gets two pair records: B-packet versus B-memory, and B-lookup versus
B-packet. Pair IDs, packet order, and left/right placement use HMAC-SHA256 with a
fresh 256-bit system secret. Supplying the secret is reserved for constructed
tests. It is stored only in the private pair map.

The reviewer packet contains opaque pair IDs, case IDs, complete neutral
criteria, availability, and exact answer and receipt bindings. It contains no arm
labels, contrast names, slot IDs, threshold values, gate configuration, or map.
Content may still reveal evidence treatment, so masking is procedural.

A pair is `reviewable` only when both arms returned nonblank final content.
Complete and partial finals are preserved unchanged and may be judged together.
A pair is `matched_complete` only when both finals are technically complete.
Every other planned pair remains explicit as `unavailable`; it is never scored as
a loss. General controls remain in the pair inventory but are excluded from Bible
preference totals.

`write_pair_artifacts(packet, pair_map, output_directory)` writes a fresh private
directory with mode `0700` and exclusive `0600` packet and map files. Existing
targets, path escapes, and symlink ancestors are rejected.

## Freeze paired assessments

The review document has this exact structure:

```json
{
  "schema_version": 1,
  "artifact_kind": "frozen_constructed_pair_review",
  "review_id": "constructed-ai-pair-review-v1",
  "packet_sha256": "<canonical pair packet SHA-256>",
  "reviewer_kind": "ai",
  "reviewer_role": "Synthetic pair fixture reviewer",
  "conflicts": ["Shared engineering fixture context."],
  "expert_certified": false,
  "assessments": [
    {
      "pair_id": "pair-<opaque value>",
      "left_answer_sha256": "<SHA-256>",
      "left_receipt_sha256": "<SHA-256>",
      "right_answer_sha256": "<SHA-256>",
      "right_receipt_sha256": "<SHA-256>",
      "preference": "left",
      "rationale": "Constructed pair preference only."
    }
  ],
  "limitations": ["No real semantic judgment or expert review."]
}
```

Preference is `left`, `right`, or `tie`. Every reviewable pair must appear exactly
once; unavailable pairs receive no assessment. Reviewer kind, role, conflicts,
packet hash, answer hashes, receipt hashes, and rationale are mandatory.
`expert_certified` must be false.

`validate_and_freeze_pair_review(packet, review, out_path)` validates exact
coverage and creates a new private `0600` review file. Integration requires the
returned file hash, so a valid-looking post-freeze edit fails before the private
pair map is read.

## Integrate without promoting

`integrate_frozen_pair_review` requires the exact inventory, journal, criteria,
packet, gate, frozen review, and private map paths plus gate and review receipt
hashes. Supplying the map writer's file hash is optional but recommended.

Integration validates in this order: frozen gate, recomputed collection and
arm-free packet, frozen review bytes and assessments, then private map. After
unmasking it regenerates the complete packet and map from the secret and requires
canonical equality. This closes pair ID, order, left/right, case, contrast,
criteria, answer, receipt, status, and unavailable-row bindings. Swapping
left/right or moving answers between cases cannot invert a preference after
review.

The result reports every arm's planned, complete, partial, failed, uncertain,
outstanding, and unsubmitted counts with its declared completion threshold. Each
contrast separately reports:

- all reviewable Bible pairs, including pairs with partial finals;
- matched-complete Bible pairs;
- unavailable Bible pairs;
- general-control planned, reviewable, matched-complete, and unavailable counts.

General controls do not enter Bible preference totals. Missing pairs do not enter
either arm's win count. The only gate statuses are `collection_sufficient` and
`inconclusive`. Threshold failure or incomplete matched coverage yields
`inconclusive`; the integration never promotes a model or claims factual quality.

## Verification

Run:

```sh
.venv/bin/python -m unittest tests.test_evidence_pairwise -v
```

The constructed suite covers complete, partial, uncertain and zero-reviewable
collections; explicit planned/control denominators; nonvacuous thresholds;
secret deterministic randomization; masking; exact review coverage; private file
permissions and confinement; post-freeze edits; seed/map changes; orientation
swaps; and cross-case answer swaps. It performs no network request or real
semantic evaluation.
