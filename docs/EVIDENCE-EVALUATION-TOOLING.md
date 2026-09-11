# Offline evidence evaluation tooling

Prepared September 8, 2026. `bibleprep/evaluate_evidence.py` implements the constructed-fixture planning increment required by the [evidence evaluation entry contract](EVIDENCE-EVAL-ENTRY-CONTRACT.md). It validates exact evidence dependencies and creates a deterministic three-arm slot inventory without contacting a model. It is not a frozen evaluation protocol, live runner, retriever, review tool, source approval, pricing record or authorization to generate answers.

## Boundary

The planner accepts only inputs whose `fixture_kind` is `constructed`. It has no `--execute` option and contains no Tinker transport, tokenizer import, credential or environment access, network access, candidate collection, retry path, review masking, scoring or integration logic. The retained B checkpoint name is a logical offline reference. The declared input token limit is an unchecked setting until the native tokenizer and template are separately verified.

The planner rebuilds the `app_display` projection from the exact registry, validated draft records, citations, source snapshots and supporting review files. That rebuild uses `bibleprep/evidence_eligibility.py`, so changed or missing registry, record, component, citation, source or review dependencies fail before a plan is produced. The saved projection must have exactly the same canonical JSON content as the rebuild. Python-coercible type substitutions such as `true` for `1` do not compare equal under this check.

An `app_display: approved` registry value remains a recorded decision rather than proof that its rationale actually covers supplying source content to the inference provider. Separate verification of that use basis remains an explicit execution prerequisite; this tooling does not add a new requirement that every such decision be made by a human reviewer.

## Strict inputs

All input objects use schema version integer `1`, reject unknown fields and use stable identifiers. CLI JSON loading additionally rejects duplicate keys and nonfinite numbers. Direct API validation rejects nonfinite or boolean numeric settings. The CLI confines every input to ignored private locations under `runs/` or `data/evidence/`, confines evidence records to `data/evidence/`, and rejects symlink traversal.

The cases document has this shape:

```json
{
  "schema_version": 1,
  "suite_id": "constructed-suite-v1",
  "fixture_kind": "constructed",
  "cases": [
    {
      "case_id": "case-one",
      "question": "A synthetic question",
      "category": "greek",
      "general_control": false,
      "packet_component_keys": ["SYNTHETIC01/claim-Q1"],
      "lookup_key": "case-one-lookup",
      "private": {
        "expected_answer": "A synthetic expected answer",
        "scoring_criteria": ["A synthetic criterion"],
        "reviewer_instructions": [],
        "provenance": ["Constructed fixture only"]
      }
    }
  ]
}
```

Every non-control case explicitly selects at least one `RECORD/component` key for B-packet and names one lookup key. Missing or ineligible packet content blocks all three arms for that case; the planner never substitutes a memory-only comparison. A general-English control must declare an empty packet and a null lookup key. Its three slots are labeled repeat controls because all receive empty evidence.

Private expected answers, criteria, reviewer instructions and provenance are bound by a per-case hash. Their values are never copied into `model_input`, `evidence_content`, the Markdown plan or the evidence sidecar.

The settings document has this exact shape:

```json
{
  "schema_version": 1,
  "settings_id": "constructed-settings-v1",
  "checkpoint_id": "logical-retained-B",
  "system_prompt": "A constructed system instruction",
  "sampling": {
    "effort": 0.7,
    "temperature": 0,
    "seed": 20260908,
    "max_tokens": 256,
    "input_token_limit": 2048,
    "deadline_seconds": 30
  },
  "request_order": "case_then_arm",
  "stop_rule": "stop_after_uncertain_or_incomplete"
}
```

The fixed order and stop-rule names make the offline inventory compatible with a later prospective collection contract. They do not implement submission or failure handling.

The lookup policy is deliberately a fixture map rather than a Bible retriever:

```json
{
  "schema_version": 1,
  "policy_id": "exact-fixture-policy-v1",
  "kind": "deterministic_exact_component_key_fixture",
  "mappings": [
    {"lookup_key": "case-one-lookup", "component_keys": []}
  ]
}
```

A missing mapping is a configuration error. An explicit empty `component_keys` list is a valid deterministic lookup miss: B-lookup remains planned with `retrieval_status: "exact_fixture_miss"` and empty evidence. A returned component that is absent from the eligible projection blocks the case.

## Planner API and output

The in-process API is:

```python
build_offline_plan(
    root=project_root,
    cases=cases,
    settings=settings,
    policy=policy,
    registry=registry,
    saved_projection=projection,
    record_directory=record_directory,
    input_file_sha256=file_hashes_or_none,
)
```

`write_plan(plan, output_directory, root)` writes `plan.json` and `plan.md` to a new directory under `runs/`. It refuses an existing destination, lexical path escape and symlink ancestors. Newly created directories use mode `0700`; files use mode `0600`.

Each case produces exactly three ordered entries in `planned_slots`: B-memory, B-packet and B-lookup. Each slot has a simple `slot_id`, `case_id`, `arm`, category, status, retrieval status, the identical question and sampling settings, and hashes of the question, complete settings object, actual evidence bytes and complete model-input object. The same logical checkpoint applies to all three arms.

The model context contains only the system instruction, question and sanitized evidence. Evidence retains selected claim or reading values, attributions, alternatives, limitations, citations and parent factual coverage limits. It excludes registry decisions, scholarly-review artifacts, reviewer identities, unresolved workflow issues, local paths, hashes and internal component keys. A separate per-slot `evidence_provenance` sidecar binds record, component, citation and source hashes without entering the model context.

Top-level bindings include canonical content hashes for cases, settings, policy, registry, saved projection and rebuilt projection. CLI plans also bind exact input-file byte hashes. The plan binds the byte hashes of `evaluate_evidence.py`, `evidence_eligibility.py`, `evidence.py` and the project-root historical-evidence schema plan, because all four determine the result.

`engineering_readiness.status` is `not_ready` when the eligible projection is globally empty or any case names unavailable packet or lookup components. All slots remain in the denominator inventory and affected slots are `blocked_evidence_not_ready`. An empty global projection remains not ready even for an all-control suite, because controls alone are not an evidence comparison. A valid constructed plan uses `planned_offline`; general controls use `repeat_control_planned`.

`execution_readiness.status` is always `not_ready` in this increment. It lists the missing live native runner, protocol and inventory freeze, current provider pricing and cost bound, concrete execution permission, checkpoint/native-template verification, tokenizer-bound input validation, inference-provider use-basis verification, and masked review/collection integration.

## CLI

All arguments below must resolve inside private ignored directories, and the output name must be fresh:

```bash
.venv/bin/python -m bibleprep.evaluate_evidence \
  --cases runs/<private-input>/cases.json \
  --settings runs/<private-input>/settings.json \
  --policy runs/<private-input>/policy.json \
  --registry data/evidence/eligibility/<registry>.json \
  --projection runs/<private-projection>/projection.json \
  --directory data/evidence/drafts/v1 \
  --out runs/<new-private-plan>
```

The command prints only an output receipt and readiness summary. It does not print concealed questions or evidence.

## Verification and remaining entry-contract work

Eleven focused constructed tests cover deterministic three-arm planning, the legitimate empty lookup result, empty and missing evidence, refusal to substitute training approval for model-input use, app-display dependency rebuilds, type-sensitive projection comparison, strict fields/types/policies, general controls, private-field exclusion, sanitized context versus provenance, CLI file bindings, stable ordering, and safe private writes. They use the existing synthetic eligibility-record helper; they do not load the real corpus as an approved source set.

The separate [collection auditor](EVIDENCE-COLLECTION-ACCOUNTING.md) now tests uncertain submissions, partial finals and stop propagation using normalized synthetic events. Parent integration binds that auditor to this planner's six-slot constructed inventory: a simulated output limit preserves one complete answer, one partial answer and four unsubmitted slots; timeout and outstanding cases preserve five unsubmitted slots. This does not verify native transport facts. The live native adapter, receipt verification, masked review, label-key disclosure, completeness-gate decision and scoring integration remain open and need prospective validation before any candidate generation. Fresh real questions, source selections, checkpoint retention, native settings, pricing, cost allowance and external permissions also remain unresolved.

The actual pending-source CLI probe is retained at `runs/evidence-tooling-p3-v1/actual-pending-readiness/`. It contains one explicitly constructed readiness question and three blocked slots. It is neither a model run nor a fresh Bible evaluation. The reusable integration check and synthetic journals remain private under `runs/evidence-tooling-p3-v1/`.
