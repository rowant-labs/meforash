# Offline evidence coordinator

`bibleprep.evidence_coordinator` connects the existing constructed evidence planner, notice-complete delivery bridge, pinned local Inkling request preparer, native diagnostic fixture simulator, and collection accountant. It only builds and checks offline artifacts. It has no provider transport, execution flag, environment or credential access, model call, retry path, file writer, chat integration, research action, training action, deployment, or publication path.

The coordinator preserves the existing modules and their frozen artifacts. It calls their public validation and construction APIs rather than replacing their source, eligibility, rendering, diagnostic, or accounting rules.

## API

Build the notice-bearing planner inventory:

```python
plan = build_coordinated_plan(
    root=project_root,
    cases=cases,
    settings=settings,
    policy=policy,
    registry=current_registry,
    saved_projection=saved_app_display_projection,
    notice_manifest=notice_manifest,
    record_directory=record_directory,
    input_file_sha256=input_file_hashes_or_none,
)
```

Render every slot with the pinned local tokenizer and explicit fixture prices:

```python
prepared = prepare_mock_coordination(
    root=project_root,
    cases=cases,
    settings=settings,
    policy=policy,
    registry=current_registry,
    saved_projection=saved_app_display_projection,
    notice_manifest=notice_manifest,
    record_directory=record_directory,
    input_rate_usd_per_million=Decimal("1"),
    output_rate_usd_per_million=Decimal("2"),
    allowance_usd=Decimal("1"),
)
```

Run fixed labeled fixtures only after regenerating the current plan and requests:

```python
result = simulate_mock_collection(
    prepared,
    fixtures,
    root=project_root,
    cases=cases,
    settings=settings,
    policy=policy,
    registry=current_registry,
    saved_projection=saved_app_display_projection,
    notice_manifest=notice_manifest,
    record_directory=record_directory,
    input_rate_usd_per_million=Decimal("1"),
    output_rate_usd_per_million=Decimal("2"),
    allowance_usd=Decimal("1"),
)
```

`verify_mock_collection(prepared, fixtures, result, **the_same_arguments)` regenerates and compares the complete simulation with finite canonical JSON hashes.

The APIs accept in-memory inputs and expose no generic callback. The only renderer is the existing request preparer's locally pinned official Inkling renderer. Tests can patch that module's existing private test seam with a deterministic fake; the coordinator itself accepts no renderer or transport injection.

## Plan reconstruction and evidence replacement

`build_coordinated_plan` first calls `evaluate_evidence.build_offline_plan`. That rebuilds the current `app_display` projection from the supplied registry and exact local records, compares it with the saved projection, validates the constructed cases/settings/fixed lookup policy, and creates the complete case-then-arm denominator.

The coordinator then handles each original slot as follows:

- B-memory remains empty.
- A general-control slot remains empty in every arm.
- An explicit exact-fixture lookup miss remains empty and retains `retrieval_status: exact_fixture_miss`.
- A nonempty B-packet or B-lookup selection is rebuilt through `evidence_delivery.build_candidate_bundle`, approved for the current app-display projection through `verify_for_use`, and rendered with `render_model_input`.

The delivery call retains exact claims/readings, alternatives, uncertainty, citations, original-language characters, record coverage limits, and every applicable source-text and annotation notice. It excludes expected answers, criteria, reviewer data, internal paths, registry metadata, and notice-workflow limitations from the model input.

After substitution, the coordinator recomputes the question, UTF-8 evidence, and complete model-input hashes. The request preparer later hashes the entire updated slot. Each notice-bearing slot carries a private provenance sidecar with the exact selected component keys, candidate hash, current registry hash, notice-manifest hash, evidence hash, and model-input hash. These values never enter the user question.

The coordinated plan binds the original plan, notice manifest, delivered-slot inventory, and exact byte hashes of:

- `evidence_coordinator.py`;
- `evidence_delivery.py`;
- `evaluate_evidence.py`;
- `evidence_requests.py`;
- `evidence_native.py`;
- `evidence_collection.py`; and
- `native_diagnostics_v1.py`.

The original planner's obsolete execution requirements are replaced by the current live gaps: no live native transport, no frozen fresh question/quality protocol, no verified current pricing, no recorded live sampling allowance, and no live checkpoint-retention/preflight verification. The narrow current source-use decisions do not introduce an extra human-approval requirement. Execution readiness remains `not_ready`.

## Exact native request preparation

`prepare_mock_coordination` passes the coordinated plan unchanged to `evidence_requests.prepare_constructed_requests`. That existing module:

- requires the complete ordered three-arm inventory;
- reconstructs messages with evidence quoted as data;
- uses pinned local Inkling tokenizer and official renderer assets;
- verifies native/HF prompt-token parity;
- checks each exact prompt against the declared input and total context bounds; and
- reserves each slot at its complete declared input ceiling plus full output ceiling.

Input and output rates and allowance must be explicit finite `Decimal` fixture values. They are caller-declared planning inputs, not verified current prices. A low allowance or an exact rendered input over its declared cap fails before fixture simulation.

The preparation record contains the complete coordinated plan and exact prepared-request record, plus canonical hashes of both. `fixture_simulation_only` is true. `generation_authorized` and `training_authorized` remain false.

## Fixed native fixtures and prompt binding

`simulate_mock_collection` first regenerates the current coordinated plan and prepared requests from every explicit input. It rejects changed source bytes, a changed or withdrawn approval, a changed notice manifest, a stale saved projection, changed settings or policy, changed renderer assets, and any difference in the saved prepared record before recording a simulated submission.

It accepts only the existing ordered `constructed_native_outcome_v1` fixture objects. There is no arbitrary transport callback, retry, resubmission, or live execution flag. Existing native simulation records submission before the injected outcome and stops the whole inventory on an uncertain/failed transport outcome, output limit, incomplete result, or blank returned final.

For every diagnostic fixture, the coordinator additionally requires:

- `prompt_token_ids_sha256` to equal the exact prepared request's prompt-token hash;
- integer `prompt_token_count` to equal the exact prepared input-token count; and
- both `generated_token_count` and the retained raw generated-token list length to fit within the prepared maximum output-token ceiling.

These checks prevent an older fixture from masquerading as the result of a changed notice-bearing prompt and prevent a fixture from exceeding its declared output reservation. Existing native validators still check the complete diagnostic schema, raw generated-token hash/count, parser structure, final-only content, completion flags, and normalized stop reason. A failure fixture has no diagnostic prompt receipt and makes no claim about native generation; it remains bound to the exact next slot/model input and is accounted as a submitted uncertain or failed attempt.

The native audit retains all planned slots in the denominator. Complete and valid partial final text remain reviewable under the existing rules; thinking is never copied into the coordinator result.

## Reservation accounting

The coordinator joins each prepared request to its exact audited slot outcome. Because retries are forbidden, every submitted slot has one attempt and retains its full per-attempt maximum reservation, including a partial, failed, uncertain, or outstanding outcome. Every unsubmitted slot has zero attempts and its full reservation moves to the `released_unsubmitted_reservation_usd` bookkeeping total.

The submitted and released totals must add exactly to the prepared full-run worst-case reservation. Arithmetic uses a local 50-digit Decimal context, independent of ambient Decimal precision. The record labels the values `maximum_sampling_reservation_not_invoice`, retains the preparer's `caller_declared_fixture_rates_not_current_verified_pricing` status, assumes no retry, and explicitly sets both `invoice_reconciled` and `invoice_cost_claimed` false. “Released” describes unused planning reservation; it is not a refund or invoice claim.

## Validation and limits

Focused constructed tests cover:

- notice-bearing packet/hit model messages and exact prepared tokens;
- empty memory/control and lookup-miss slots;
- retained alternative and uncertainty content without private expected answers;
- complete, partial, uncertain, and unsubmitted denominator accounting;
- maximum submitted reservation and released unsubmitted reservation;
- stale or withdrawn approval, changed notices, and stale source bytes;
- wrong prompt hash/count and generated output over the prepared cap;
- exact input limits, insufficient allowance, prepared/result tampering, and type-sensitive canonical comparison.

Run them with:

```sh
.venv/bin/python -m unittest tests.test_evidence_coordinator -v
```

The coordinator does not establish factual truth, reviewer expertise, legal clearance, invoice cost, provider behavior, live readiness, or protocol quality. A constructed fixture is not a provider result or a fresh benchmark.

Training remains on explicit hold. Before any future training work, the owner must be notified, provide an additional research topic, receive the resulting research and plan, and then give a separate training go-ahead. No coordinator artifact satisfies or bypasses that hold.
