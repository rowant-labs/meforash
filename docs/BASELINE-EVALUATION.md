# Baseline evaluation kit

**Status: locally tested; live inference uses the [native Tinker runner](TINKER-BASELINE.md).** Substantive answer review remains separate from software validation. See the [current readiness report](PRETRAINING-READINESS.md) for execution and review status. This kit supports the whole-corpus original-language adaptation experiment in [the training plan](training-plan.md). It compares the unchanged model with later adapters on the same English tasks, rather than requiring a retrieval application first.

## What the pilot contains

[`evals/pilot-v1.jsonl`](../evals/pilot-v1.jsonl) contains 40 constructed development cases: 12 Hebrew, 12 Aramaic, 12 Greek, and four cross-language or general cases. The ordering interleaves languages so a small capped run does not test only Hebrew. Aramaic is deliberately oversampled; these are diagnostic results, not a corpus-weighted benchmark.

The set includes 12 focused grammar questions, three direct translation tasks, six historical-context questions, 12 language-group application questions, three constructed metadata/coverage fixtures, and four cross-language/general cases. The mixed cases include additional reflection and ordinary English instruction-following. Translation reviewers should check negation, agency, addressees, verbal force, clause relationships, lexical adequacy, omissions, and additions separately from fluency. Reflections should follow the [intent-based answer contract](PROJECT_CHARTER.md), remain useful and non-denominational, and distinguish reflection from an established ancient meaning.

Each case records its ID, issue family, category, language, prompt, source references, expected behavior, review criteria, source URLs, and review status. Original-language excerpts use pinned OSHB/WLC and SBLGNT revisions with attribution and extraction details in [`evals/provenance.json`](../evals/provenance.json). The OSHB excerpts join verse word elements after removing morphological slash separators and exclude notes/apparatus; they are not diplomatic manuscript transcriptions. SBLGNT editorial marks are preserved. Mark 16:9–20 references are labeled supplemental; the source distribution's inclusion is not manuscript attestation.

Substantive criteria are **unreviewed**, with no approved scholarly gold answers. The linked base texts do not establish every grammatical, historical, or interpretive conclusion; reviewers must consult suitable scholarship. No real witness attestations were invented for this set. The coverage/omission exercise explicitly uses synthetic records.

Three fixtures have mechanical JSON-shape and exact-field checks. These verify handling of values supplied in their prompts, **not biblical historical correctness**. Their factual lookup values are constructed inputs, not manuscript findings. All other substantive review remains human. A correct citation string alone does not show that a claim follows from its source.

## Run safely without an API key

From the repository root, with Python 3.10 or later:

```sh
python3 -m bibleprep.evaluate
```

The default is a dry run. It validates the dataset and input-size estimates and creates a manifest and summary under ignored `runs/`. It does not read `.env` or an API key, send a request, or generate model answers. Output artifacts cannot be directed outside that ignored directory. The command-line defaults target Groq's `openai/gpt-oss-120b`, but the model choice remains provisional and the provider revision is labeled unpinned unless supplied explicitly.

A priced plan for a later supplied-text comparison can be prepared without executing:

```sh
python3 -m bibleprep.evaluate \
  --run-dir runs/base-a-provided \
  --evidence-mode provided \
  --max-cases 40 \
  --max-input-tokens 6000 \
  --max-output-tokens 1500 \
  --input-price-per-million 0.15 \
  --output-price-per-million 0.60 \
  --budget-usd 0.25
```

The example prices reflect the September 5, 2026 [Groq catalog](https://console.groq.com/docs/models); verify rates and model access before execution. The full 40-request reservation at those caps is $0.072, excluding any external service charges or taxes. This is an upper planning estimate under the configured pricing and input-estimator assumptions, not a measured bill.

For local credentials, copy [`.env.example`](../.env.example) to `.env` in the repository root if it does not already exist, then fill only the chosen provider's key in your editor. Tinker uses `TINKER_API_KEY`; optional screening providers use `GROQ_API_KEY` or `FIREWORKS_API_KEY`. Install `requirements-prep.txt` into the project's `.venv` before API execution. The runner loads only this checkout's `.env` when `--execute` is present; exported shell variables take precedence. It does not search parent folders, expand variables, execute shell commands, or print credentials. The `.env` file is ignored by Git; the blank example is shareable.

Once paid execution is authorized and the chosen key is configured privately, repeat **the identical command** with `--execute --resume`, using `.venv/bin/python` in place of `python3` so the installed dependencies are available. Do not paste keys into commands, tracked files, or chat. `--api-key-env` accepts an environment variable's **name**, not its value. Execution requires explicitly supplied input/output prices and a positive budget; missing or invalid prices fail closed. Record live execution separately from local tests; local tests do not call the provider.

Use `--base-url` for an HTTPS OpenAI-compatible API root ending at the provider's API version, not `/chat/completions`; the runner appends that route. Set `--model`, `--model-version`, and `--api-key-env` as appropriate. Providers that require `max_tokens` instead of `max_completion_tokens` can use `--output-limit-field max_tokens`. Optional `--reasoning-effort low|medium|high` is sent only when specified. A Tinker-compatible endpoint may require a sampler checkpoint identifier such as `tinker://…`, rather than a base-model catalog name; confirm its current compatibility and availability before use. The runner does not create a Tinker sampler or checkpoint.

## Limits, billing, and resume behavior

- The runner has finite case, estimated-input, output, and request-time limits. It makes no automatic retries and rejects redirects rather than forwarding an authorization header elsewhere.
- Input size uses UTF-8 content bytes plus 256 tokens as a conservative proxy for byte-level tokenizers. It is **not exact provider tokenization or a universal mathematical bound for every tokenizer**. Rejecting an oversized prompt happens before any requests. Confirm actual accounting on a tiny authorized run; use the project's tokenizer measurements when calibrating the cap.
- Before each request, reserve the cost of the full configured input/output caps. A request is not sent if that reservation would exceed the run budget. Actual usage releases unused reservation when valid usage is returned. Reasoning tokens are recorded as a component of output, not added a second time to its cost.
- Every start is journaled and flushed before sending. Missing usage, network/provider errors, or a request whose completion is uncertain are charged the reservation locally and stop the run. A provider-reported cap breach also stops the run. This cannot guarantee the provider's final invoice when rates, metering, or limits differ from the assumptions; use provider-level spending controls too.
- `--resume` requires the same dataset hash, system prompt, model/settings, limits, prices, budget, and selected case IDs. It skips completed requests. It refuses to retry uncertain requests or a prior limit breach. Do not erase an uncertain journal to retry blindly: inspect the account bill first and record any new run's relationship to the earlier attempt.
- A dry-run manifest can be resumed with execution if all those settings match. Changing the model, budget, evidence mode, or dataset requires a new run directory so experiments are not silently mixed.

Artifacts are `manifest.json`, `events.jsonl` after execution starts, and `summary.json`. The manifest records the dataset and system-prompt hashes, selected IDs, operator-declared model revision, parameters, and prices. Events contain timestamps, latency, provider-returned model/fingerprint, input/output/reasoning usage, finish reason, truncation, mechanical-check results, and redacted raw provider responses. Provider error bodies and credentials are never logged. These files remain private and ignored; only reviewed aggregate findings belong in public reports.

`answer_complete` is false for length-limited or otherwise unfinished answers. Unknown finish reasons are not assumed successful. Truncation is a failure to complete, not a normal-quality answer. The runner records `human_review: pending` and never automatically assigns a historical correctness score. A shared model name and returned fingerprint may still fail to identify immutable weights; document that reproducibility limit.

## Compare before and after adaptation

Run arm A with `--evidence-mode none` to ask from the model's existing knowledge. Run a separate arm A with `--evidence-mode provided` to append original-language excerpts for the 12 grammar and three translation cases. Other prompts are unchanged, including fixtures whose necessary records are in the prompt itself. Do not interpret the supplied-text contrast as covering every context/reflection question.

Repeat these settings for arm B, the original-text-only adapter, retaining separate directories and the exact same evaluation dataset. Later arms C and D can use the same development set. Compare language, translation, context, reflection, instruction-following, completion, and cost separately. Examine whether lower training loss coincides with better English answers or merely more biblical recitation.

Reviewers should see the prompt, relevant source excerpts and context, and the answer, with model/arm identity hidden when feasible. Record reviewer expertise and interpretive perspective, pass/partial/fail, severity, supporting sources, and rationale for each substantive criterion. Resolve disagreements openly; do not treat one tradition's conclusion as the universal gold answer. Before making public quality claims, add separately reviewed high-stakes cases and a qualified review of contested historical claims.

This public pilot is a **development set, not a final holdout**. Keep its prompts, expected behavior, gold fixture values, rubrics, model answers, and later answer keys outside all training data and synthetic-target generation. Whole-corpus adaptation can contain the biblical passages themselves; new questions about those passages measure task performance on seen source text, not unseen-text generalization. Preserve separate passage/issue-family holdouts when testing transfer, and prepare final unseen question families once the recipe is settled. Public evaluation prompts and prior base-model exposure also limit contamination claims.

The runner allowlists only the system prompt, user prompt, and explicitly selected `provided_evidence` into requests. It never sends expected behavior, human-review criteria, gold answers, or source metadata implicitly. This boundary is covered by tests. A caller who manually puts an answer key in a prompt would defeat it; review dataset changes before use.

Run local verification with:

```sh
python3 -m unittest discover -s tests -p test_evaluate.py -v
```

The tests use mocked responses and constructed credentials. They exercise no paid API calls and establish software behavior, not model or scholarly quality.
