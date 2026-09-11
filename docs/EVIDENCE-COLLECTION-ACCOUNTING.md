# Evidence collection accounting

Prepared September 8, 2026. `bibleprep/evidence_collection.py` is bounded,
model-free accounting for the proposed evidence comparison. It validates
constructed append-only journals against the exact ordered planned-slot
inventory. It makes no network calls, reads no credentials and writes no files.

## Interface and normalized events

Call `audit_collection(planned_slots, journal)`. Every planned slot is a finite
JSON object with at least nonempty `slot_id`, `case_id` and `arm` strings. The
full ordered objects, including extra planner fields, determine the inventory
hash. Slot IDs and case/arm pairs must be distinct. Submissions must follow that
exact order.

The journal accepts only these strict event shapes (a result and a failure are alternative terminal events, not both valid for one submission):

```json
{"event":"submission","slot_id":"case-1::B-memory"}
{"event":"result","slot_id":"case-1::B-memory","stop_reason":"stop","final_text":"Constructed answer.","receipt_sha256":"<64 lowercase hex>"}
{"event":"failure","slot_id":"case-1::B-memory","disposition":"uncertain","receipt_sha256":null}
```

`stop` means a future native adapter has already validated a complete native
turn; it is not a raw provider stop label. `output_limit` and `incomplete` are
the other result stop reasons. They produce a partial outcome when nonblank
final content exists. A returned result with no final content is failed and
remains distinguishable from an explicit transport failure. Failure disposition
is `failed` or `uncertain`. Extra event fields are rejected, including separate
reasoning fields. The future native adapter must supply only final-answer text;
this audit cannot identify reasoning that a caller incorrectly labels as final text.

The fixed v1 policy permits one open request and one submission per slot. An
output limit, incomplete result, missing final content, failure or uncertainty
stops the entire collection. No later submission or automatic retry is valid.
An end-of-journal submission without a terminal event remains uncertain and
open; all later slots remain unsubmitted rather than becoming model failures.

## Output and interpretation

The audit binds canonical hashes of the exact inventory and journal. It reports
each slot and per-arm/overall planned, complete, partial, failed, uncertain,
outstanding and unsubmitted counts. Outstanding is an overlapping subset of
uncertain, so totals that include both deliberately do not sum. Every complete
or partial final answer is preserved for review with an exact UTF-8 answer hash,
its stop reason and the supplied receipt hash.

These are technical collection facts. The tool leaves semantic answer
completeness, the predeclared collection threshold, critical errors, preferences,
expertise, model quality and promotion unassessed. Receipt hashes are opaque
caller-supplied bindings until a verified native adapter checks real receipts.
There is no live transport, masking, review freeze, label disclosure,
integration, quality judging or protocol authorization in this increment.

Run the constructed checks with:

```sh
.venv/bin/python -m unittest tests.test_evidence_collection -v
```
