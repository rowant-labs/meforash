# Known-topic evidence pilot runner

`bibleprep.evidence_pilot` is the narrow live runner for the frozen 18-slot
English development pilot. It connects the existing notice-complete evidence
coordinator, exact local Inkling request renderer, retained B checkpoint checks,
bounded native sampling worker, native diagnostic sidecars, and collection
accounting. It is specific to six frozen cases in three conditions. It is not a
general evaluation framework or a fresh whole-Bible benchmark.

The runner does not contain a training client. The protocol fixes training and
promotion authorization to false. The separate owner training hold remains in
force: notify the owner, receive the additional research topic, complete that
research and revisit the plan, then obtain a separate training go-ahead before
any future training.

## API

Offline preparation takes the protocol file and its independently recorded raw
file hash:

```python
preparation = prepare_known_topic_pilot(
    "runs/evidence-pilot-v1/protocol.json",
    protocol_sha256,
    root=project_root,
)
```

This performs no provider call, environment read, credential read, run-file
write, or model generation. It returns the 18 exact request records and a
sanitized checkpoint identity hash, together with the complete worst-case
reservation.

The execution entry point requires a strict Boolean opt-in:

```python
result = run_known_topic_pilot(
    "runs/evidence-pilot-v1/protocol.json",
    protocol_sha256,
    execute=True,
    root=project_root,
)
```

Calling it with `execute=False` performs the same offline preparation. Values
such as `1` do not count as an opt-in. There is no resume or retry flag and no
transport callback in the public API.

After collection, the read-only verifier rebuilds current source and request
closure and checks the saved private run:

```python
verified = verify_pilot_run(
    "runs/evidence-pilot-v1/protocol.json",
    protocol_sha256,
    root=project_root,
)
```

## Frozen protocol

The strict version-1 protocol binds:

- the six cases, scoring criteria, AI criteria review and frozen blinded-review
  plan as separate exact files;
- the current eligibility registry, saved projection and notice manifest;
- the fixed lookup policy and constructed-compatible settings;
- the pinned comparison renderer manifest;
- the redacted, read-only retained-checkpoint preflight;
- retained B's locally verified checkpoint receipt and opaque sampler hash;
- the exact pricing review and its official snapshot;
- every implementation file that determines source delivery, prompt rendering,
  native collection, receipt verification and accounting; and
- the one-pass execution controls and private run destination.

All bound paths are project-relative. Input and support files must remain under
their expected public or ignored project directories and must not pass through
a symlink. Duplicate JSON keys and nonfinite numbers fail closed.

The protocol fixes full Inkling B, numeric effort `0.7` and its native named
setting `medium`, temperature `0.0`, seed `1702`, an 8,192-token input ceiling,
an 8,192-token output ceiling and a 300-second complete-operation deadline. The
inventory is case-then-arm and contains B-memory, B-packet and B-lookup for each
case. Four Bible cases cover only the two already reviewed source families; two
general cases are retention controls.

The reviewed rates are explicit decimal strings: `$1.87` per million input
tokens and `$4.68` per million output tokens. With both 8,192-token ceilings,
the maximum reservation is `$0.0536576` per slot and `$0.9658368` for all 18
slots. The operator cap is `$2`. No cache discount is assumed. These are maximum
sampling reservations, not an invoice or reconciled charge.

Pricing and retained-checkpoint preflight receipts must be no more than 24 hours
old when preparation runs. The retained checkpoint must remain unexpired. The
runner verifies the saved checkpoint through both existing provenance helpers;
a caller-supplied opaque path or hash cannot replace those checks.

## Immediate regeneration and submission

Before each single attempt, the runner repeats the entire offline closure:

1. Rehash every protocol, input, pricing, checkpoint and implementation file.
2. Rebuild the current app-display projection from the exact registry and
   records through the existing eligibility validator.
3. Rebuild the selected notice-complete evidence delivery, including applicable
   licenses, attribution, change notices, disclaimers, uncertainty and citation
   limits.
4. Rebuild all 18 planner slots and exact native messages and token IDs with the
   pinned local tokenizer and official renderer.
5. Compare the complete preparation with the preparation frozen when execution
   began.

Any pre-submission difference stops collection with the current and remaining
slots unsubmitted. It cannot create a submitted event.

For an attempt that passes these checks, the runner durably appends the strict
`submission` event and calls `fsync` before the native worker can initialize or
send the request. The worker uses retained adapter B, disables application
retries, enforces one complete-operation deadline and writes its private native
diagnostic sidecar before returning the safe response.

The runner then requires the response prompt-token hash and count to equal the
exact prepared request. It also requires the returned sequence count to remain
within the prepared output ceiling. Native parser evidence determines `stop`,
`output_limit` or `incomplete`; a provider label alone does not. Only completed
and valid partial final text enters the result event. Thinking and raw generated
token IDs stay in the mode-0600 diagnostic sidecar.

For a valid response, the runner durably writes a private receipt before the
terminal journal event. The receipt binds the exact protocol, preparation,
planned inventory, slot, model input, payload, prompt tokens, output count,
native sidecar, final text, checkpoint, implementation and review files. The
terminal result contains the exact final text and normalized stop reason.

If submission may have occurred but transport or response verification fails,
the runner records a terminal `uncertain` failure with a null receipt and stops.
It never automatically retries. An output limit, incomplete native turn, blank
final, or valid partial also stops the whole run. All later slots remain in the
18-slot denominator.

## Private artifacts and verification

Execution creates one new mode-0700 private run directory and refuses any
existing destination. It creates an empty mode-0600 journal before credential or
transport setup, so a local setup failure still yields durable zero-submission
accounting. It also writes:

- a manifest binding protocol, preparation, implementation and checkpoint
  identities;
- append-only strict collection events;
- one receipt file for each returned result;
- native diagnostic sidecars containing raw generated IDs and separated
  reasoning/final content; and
- a summary with all planned slot outcomes and maximum reservation bookkeeping.

`verify_pilot_run` regenerates the current source and request preparation. It
then verifies every receipt and native sidecar and compares each journal result's
receipt hash, final text and stop reason with the normalized native evidence.
Changing a journal answer and recomputing its summary therefore cannot create a
valid result. The verifier also repeats the 18-slot audit and exact reservation
accounting.

Every submitted attempt, including a partial or uncertain attempt, retains its
full maximum reservation. Every unsubmitted slot releases its planning
reservation. Submitted and released values must add to `$0.9658368`. Release is
bookkeeping for unused reservation, not a refund. The summary explicitly makes
no invoice claim and no quality, promotion or training decision.

## Validation

Focused tests use only deterministic mocks. They cover complete 18-slot
collection, exact payload and retained-adapter config, output-limit partials,
durable uncertainty, stop-all behavior, stale pre-submission source closure,
zero-submission setup failure, strict execute types, output caps and forged
journal text with a valid unchanged receipt.

Run them with:

```sh
.venv/bin/python -m unittest tests.test_evidence_pilot -v
```

Mock outcomes establish runner control flow only. Actual provider responses are
not described as synthetic. The known-topic pilot can at most inform whether a
later fresh-source evaluation is warranted. Its two source families cannot
establish whole-corpus accuracy, expert certification, production readiness or
model improvement.
