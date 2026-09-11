# Offline evidence native bridge

Prepared September 8, 2026. `bibleprep/evidence_native.py` connects the
constructed evidence planner to the normalized collection auditor using
injected native-diagnostic fixtures. It is an offline engineering bridge, not a
live runner, frozen protocol, fresh benchmark, source approval or generation
authorization.

## Boundary

The module has no command-line execution mode, provider transport, retry path,
credential or environment access, tokenizer load, network access, file writer,
review scoring or label disclosure. It accepts only a plan whose
`planner_kind` is `constructed_offline_evidence_inventory`, whose engineering
dependencies are ready, and whose `execution_readiness.status` remains
`not_ready`. A blocked plan is rejected. Simulation copies the plan's unchanged
execution-readiness record into its result; it does not clear any live-run
prerequisite.

The bridge exposes four bounded functions:

- `normalize_diagnostic_artifact(diagnostic, declared_sha256)` validates an
  injected native-diagnostics-v1 object and derives final-only collection facts.
- `normalize_native_response(response, run_dir)` verifies an already existing
  native response and private sidecar with the established
  `native_diagnostics_v1` helpers. It does not make the response.
- `simulate_sequential_collection(plan, fixtures)` produces an ordered strict
  journal, separate receipt bindings and the existing `audit_collection`
  result.
- `verify_simulated_collection(plan, fixtures, record)` rebuilds the simulation
  and requires exact equality, then checks unique terminal receipt coverage.

No function accepts a caller-supplied transport or arbitrary callback.

## Constructed fixture contract

Fixtures are ordered exactly like `plan.planned_slots` and have this strict
shape:

```json
{
  "schema_version": 1,
  "fixture_kind": "constructed_native_outcome_v1",
  "slot_id": "case-one--b-memory",
  "model_input_sha256": "<64 lowercase hex>",
  "outcome_kind": "diagnostic",
  "payload": {"schema_version": 1},
  "payload_sha256": "<64 lowercase hex>"
}
```

For `diagnostic`, `payload` is a native-diagnostics-v1 artifact and its hash is
`sha256(canonical finite JSON UTF-8)`. The bridge applies the existing public
summary and raw-token validation, checks the raw token-ID hash and count, and
checks final/partial state, parser issues, completion flags and finish reason.
Parser errors, unknown status combinations and contradictory completion facts
are rejected. Thinking text is inspected only through schema/count checks and
never copied into the journal or simulation record.

For `failure`, the payload is exactly:

```json
{"disposition":"uncertain"}
```

`failed` is the other accepted disposition. This is a labeled, hash-bound
injected transport fixture. It is not presented as a provider receipt.

The plan slot must still contain the exact `model_input` whose canonical hash is
declared by `model_input_sha256`. The fixture repeats that hash. When a native
diagnostic includes `prompt_token_ids_sha256` and `prompt_token_count`, the
bridge validates their types and carries the prompt-token hash into the receipt
binding. It does not prove that those native prompt tokens are the native
rendering of the planner's model input; that requires a future verified renderer
and request adapter.

## Stop and final-text derivation

The normalized stop reason does not trust a caller's raw provider stop label.
It is derived from the checked native diagnostic:

| Checked diagnostic state | Normalized result |
| --- | --- |
| Complete native turn, provider stop, nonblank completed final | `stop` |
| Native `length` finish with matching provider length fact | `output_limit` |
| Structurally unfinished native turn | `incomplete` |
| Any parser issue or contradictory/ambiguous state | reject |

Completed final messages and a valid unfinished final tail are joined in native
message order with a newline. This preserves partial final content after an
output limit. Completed and partial thinking are never promoted to final text.
An output-limit or incomplete result stops the whole simulation even when it has
reviewable final text. A result with no nonblank final content is passed to the
collection auditor as a returned result and becomes failed there.

## Journal and receipt binding

Each accepted outcome is preceded by the exact strict submission event required
by `evidence_collection`:

```json
{"event":"submission","slot_id":"case-one--b-memory"}
```

The following terminal event is the existing strict `result` or `failure`
shape. Its `receipt_sha256` is the canonical hash of a separate binding that
contains the ordered planned-slot inventory hash, exact slot hash and ID,
planner model-input hash, fixture payload hash, nullable native prompt-token
hash, and normalized terminal facts. Result bindings include the exact UTF-8
final-text hash. No later fixture, resubmission or retry is accepted after a
failure, uncertainty, output limit, incomplete result or blank returned final.
All later planned slots remain unsubmitted in the accounting denominator.

Exact verification fails if the plan, slot, model input, diagnostic or failure
payload, terminal event, audit, execution-readiness copy or receipt binding is
changed or missing. These receipts establish deterministic fixture accounting;
they are not provider receipts, proof that an official parser originally
created an injected object, or proof of planner-input/native-prompt equivalence.
`normalize_native_response` separately verifies a real existing diagnostic
sidecar through its native receipt, while retaining the same prompt-rendering
limitation.

Run the focused offline checks with:

```sh
.venv/bin/python -m unittest tests.test_evidence_native -v
```
