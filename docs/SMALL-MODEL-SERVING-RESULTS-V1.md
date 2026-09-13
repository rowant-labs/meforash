# Small-model serving pilot: first live results

September 12, 2026 local date (September 13 UTC). Exploration branch `codex/hosting-first-small-model` only. The production app and retained Inkling B did not change. No training or adapter export occurred.

## Result

**Unchanged gpt-oss-20b runs and streams on the tested Runpod A40 setup. Initial startup misses the target badly; warm short requests are promising.** This establishes an infrastructure path for the base model, not portability of a future Tinker adapter, production readiness, or biblical accuracy.

| Measurement | Observed |
|---|---|
| First successful request | 267.957 seconds provider delay + 3.343 seconds execution; final answer complete |
| One warm streamed request | 0.670 seconds to visible content; 0.944 seconds total |
| Three simultaneous short requests | All complete; 1.336–4.197 seconds total |
| Ten simultaneous short requests | All complete; 1.522–13.803 seconds total |
| Five-turn follow-up sequence | All complete; 0.973–3.018 seconds each |
| Model loading memory in engine log | 13.8 GiB; not total runtime or peak memory |
| Teardown | Both disposable endpoints and templates deleted; endpoint absence verified; account running spend returned to zero |

The concurrent requests were queued through one configured worker with engine sequences limited to one. They do not establish ten parallel decoding streams. The streamed answers were tiny constructed jar questions, with roughly 18–101 visible characters; these timings cannot forecast long Bible answers. The fifth follow-up requested about 200 words and returned 1,084 characters in 3.018 seconds. Manual inspection of the first four follow-ups confirmed that the model tracked the supplied jar contents and the subsequent change correctly.

Worker logs confirmed vLLM 0.29.0, the pinned model/tokenizer revision and native MXFP4 loading. See [the pilot specification](SMALL-MODEL-SERVING-PILOT.md) for pins. Parameter-loading memory leaves a plausible route to 24 GB, but KV cache, graphs and concurrency require their own measurement. No 24 GB test occurred.

## What failed or remains uncertain

- The initial temporary endpoint was replaced before any answer after correcting the worker's logging configuration. Its one native request was cancelled, its endpoint/template deleted, and its evidence preserved. The replacement used `ENABLE_LOG_REQUESTS=false`, the current worker flag, rather than the old `DISABLE_LOG_REQUESTS` flag. The replacement also used the reasoning setting in the worker's actual sampling payload.
- The first stream attempt timed out locally at 60 seconds while initialization continued. Provider job totals later reached 21 completed: one native cold request, that timed-out stream, fourteen warm stream probes and five follow-ups. The timed-out stream was not locally received or verified. This demonstrates that client timeout did not cancel this remote request. A production integration must explicitly address cancellation and orphan accounting.
- First-time image/model loading and kernel warmup took minutes. The observed 271.3 seconds to first completed answer fails the proposed cold-start target. It is not a measured typical restart time.
- A repeat cold request was deliberately not submitted: the provider still reported an idle/ready worker even after running spend reached zero. That was insufficient evidence of a full cold restart. FlashBoot/standby behavior needs a separate controlled measurement.
- Warm tests showed structured reasoning separately from final content. No production browser integration was exercised. Reported reasoning-token counts were zero despite nonempty reasoning fields, so do not rely on those token details for accounting.
- Authentication, warm streaming, short follow-up context and a queued ten-request burst worked. Long-context saturation, deliberate overload failure, exact GPU peak allocation, final-only app integration and trained-adapter parity remain untested.

## Cost and evidence

The pilot used the $10 ceiling and independent 15-minute cleanup timer. Resources were manually deleted before that timer. Provider billing history still returned no records at teardown; this is **pending billing**, not free usage. Retain a $1 local reservation for this short campaign until the bill is reconciled; this is an estimate, not an invoice figure. Do not calculate cost per 1,000 answers from this tiny, startup-heavy sample or from changes in account balance alone.

Private receipts, redacted worker-log captures, the exact executed probe version and constructed outputs are in ignored `runs/small-model-serving-v1/`, with the replaced endpoint records under `attempt-1/`. Credentials, resource identifiers and raw provider records are excluded from this public report.

The reusable [stream probe](../tools/serving_stream_probe.py) defaults to dry-run, restricts credential destinations, stores timing/counts rather than answer or reasoning text, and refuses an existing output before making requests. Its post-pilot hardening was tested offline; paid results above used the preserved earlier version. Ten probe tests and seven cost-calculator tests passed. These are engineering tests, not model evaluations.

## Next bounded work

1. Reconcile the first bill. Improve startup through verified caching/warmup settings, then measure actual restart behavior and more representative answer lengths.
2. Repeat on an explicit 24 GB GPU without changing to BF16 or silently dropping adapter modules; evaluate the cost/latency tradeoff rather than selecting by hourly price.
3. Propose a tiny Tinker adaptation and exact export/load parity test. Stop for the pre-training notice before training. Only after portability works should we freeze a fresh quality comparison and run a full original-language adaptation.

No model promotion, main-branch merge, public weight release or change to the live inference provider is implied by these results.
