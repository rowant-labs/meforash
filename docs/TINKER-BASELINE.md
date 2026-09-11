# Native Tinker baseline

The native runner evaluates the unchanged `openai/gpt-oss-120b` through `ServiceClient.create_sampling_client(base_model=...)`. It creates no training client, adapter, or weight checkpoint. `openai/gpt-oss-20b` is also accepted, subject to its tokenizer matching the pinned preparation tokenizer. The baseline is the first arm of the [training comparison](training-plan.md); generated answers still require review.

## Run it

Use Python 3.11 or later for Tinker (tested locally with Python 3.13). On a fresh checkout, first fetch the pinned assets with `python -m bibleprep.fetch`, following the [preparation setup](PRETRAINING-READINESS.md#reproduce-the-preparation). Install the separately pinned inference dependencies and configure `TINKER_API_KEY` in the ignored project `.env`. Do not put a key in a command, dataset, document, or issue.

```sh
.venv/bin/python -m pip install -r requirements-inference.txt
.venv/bin/python -m bibleprep.tinker_access --check
.venv/bin/python -m bibleprep.tinker_evaluate
```

The last command is a local dry run. It verifies pinned tokenizer/template asset hashes and records a plan, without loading credentials, initializing the SDK, or calling a provider. Execution requires `--execute`, explicit input/output prices, and a positive total budget. For example, at the checked gpt-oss-120b rates:

```sh
.venv/bin/python -m bibleprep.tinker_evaluate \
  --execute --max-cases 4 --evidence-mode provided \
  --input-price-per-million 0.33 --output-price-per-million 0.84 \
  --budget-usd 0.05 --run-dir runs/tinker-smoke
```

`--max-cases` selects the first N rows. The current interleaved dataset starts with H01, A01, G01, and M01: Hebrew, Aramaic, Greek, and a mixed/general question. After inspecting complete responses and usage, use 40 cases for the development baseline. Run `--evidence-mode none` and `provided` separately to distinguish recollection from interpretation of supplied text. The existing corpus is never sent as part of this baseline; only the selected question and explicitly supplied evidence are sent.

Defaults are low reasoning effort, temperature 0, seed 20260905, a 6,000-token input ceiling, a 4,096-token total generation ceiling, and a 120-second complete-operation deadline. `--prompt-date` pins the date used inside the official chat template. Keep it and all settings fixed across comparisons. Temperature and seed do not establish exact deterministic service behavior. Prices are operator-supplied and must be rechecked against [Tinker's model pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/).

## Formatting and provenance

The runner applies the official pinned Hugging Face `chat_template.jinja`, rather than encoding an unformatted English chat prompt. This template maps the application instructions to the developer message and explicitly sets the gpt-oss reasoning level. It uses the actual pinned Harmony markers, including `<|channel|>`, `<|return|>`, and `<|call|>`; the end-of-message marker alone is not a generation stop.

Before any sample, the runner compares the complete provider and pinned tokenizer vocabulary mappings and Unicode probes. Every rendered prompt is then encoded with both tokenizers, and token IDs must match exactly. This verifies the input representation used for the run. It does not establish a pinned provider weight revision; manifests label that revision as unavailable instead of treating the public Hugging Face tokenizer revision as proof of deployed weight identity.

Only explicit final-channel text is retained as the answer. An analysis-only or incomplete generation is not treated as an answer. Output-limit stops, malformed channel boundaries, and tool handoffs remain visibly incomplete. Analysis text is not retained, while its body-token count and the total generated-token count are recorded separately. The latter includes protocol and reasoning tokens.

References: [Tinker sampling client](https://tinker-docs.thinkingmachines.ai/tinker/api-reference/samplingclient/), [rendering tutorial](https://tinker-docs.thinkingmachines.ai/tutorials/core-concepts/rendering/), [pinned official template](https://huggingface.co/openai/gpt-oss-120b/blob/b5c939de8f754692c1647ca79fbf85e8c1e70f8a/chat_template.jinja), and [official Harmony renderer](https://github.com/thinking-machines-lab/tinker-cookbook/blob/main/tinker_cookbook/renderers/gpt_oss.py).

## Accounting, deadlines, and privacy

The shared [baseline runner](BASELINE-EVALUATION.md) reserves the configured maximum input/output cost before each case, journals the request before dispatch, and refuses automatic retries or resume when completion or accounting is uncertain. Successful native usage is the exact length of submitted prompt token IDs and returned generated token IDs. It is a local compute estimate, not a provider invoice. Prompt cache metadata is preserved when returned; estimates conservatively price the full prompt.

The application makes no automatic repeat attempt after a failed sample. HTTP retries and the SDK's outer sampling retry handler are disabled. However, SDK 0.27.1 also contains an internal submission retry/backpressure loop that these public options do not disable. Its retry count and any provider billing deduplication guarantee are not exposed here. The budget is therefore a bound on the application's planned requests, not a guaranteed provider invoice ceiling under transport failures. No undocumented idempotency claim is made. [SDK implementation](https://github.com/thinking-machines-lab/tinker/blob/main/src/tinker/lib/internal_client_holder.py)

A separate worker process covers account preflight, SDK startup, tokenizer checks, queue time, internal retries, and generation with one overall deadline. On timeout it is terminated, further SDK activity stops locally, and the full case reservation is retained as uncertain. This cannot cancel work already accepted remotely. Inspect the provider's usage before deciding whether a new run is appropriate.

Raw run artifacts stay inside ignored `runs/`. Credentials move through a local process pipe, never command-line arguments. SDK telemetry is disabled in the worker. SDK output and exception bodies are suppressed; only authored failure categories return. The shared journal redacts any echoed credential in successful responses. Prompts include only the allowlisted user question and optional evidence, never gold answers or review criteria. Public release should use reviewed examples and aggregates under the project's [publication practices](PUBLICATION.md).

Local tests cover rendering, Unicode parity failure, final/analysis separation, truncation, exact token accounting, asset tampering, dry-run isolation, billing preflight, and process timeout cleanup. These tests establish runner behavior; they do not establish biblical correctness or improvement from training. Record real run results separately after execution and review.

## Summarize local runs

The first executed runs are documented in the [baseline results](BASELINE-RESULTS-2026-09-05.md). To create a shareable aggregate from local journals without credentials or API calls:

```sh
.venv/bin/python -m bibleprep.summarize_evaluation \
  runs/tinker-smoke-120b-v1 \
  runs/tinker-baseline-120b-provided-v1 \
  runs/tinker-baseline-120b-none-v1 \
  runs/tinker-smoke-120b-high-v1 \
  --output reports/baseline-2026-09-05.json
```

The report separates complete final answers, incomplete responses, errors, and unattempted cases; a complete final answer is not necessarily correct. Token estimates and uncertain request reservations are separate. Dataset metadata is used only when its hash matches the run manifest. The aggregate contains hashes and safe settings, with no answer text or account information. Reports made while a run is active are snapshots and must be regenerated after it stops. Raw journals remain private.
