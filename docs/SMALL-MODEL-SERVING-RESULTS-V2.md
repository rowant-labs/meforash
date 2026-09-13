# A5000 24 GB serving qualification

September 12, 2026 local date (September 13 UTC). Isolated exploration branch only. Unchanged gpt-oss-20b; no training, adapter, production change or weight release.

## Findings

The native MXFP4 model ran on an explicit NVIDIA RTX A5000 with 24 GB, pinned to the same model/tokenizer and worker image revisions as [v1](SMALL-MODEL-SERVING-RESULTS-V1.md). This test enabled `ENFORCE_EAGER=true`, retained the 8,192-token context setting, 85% GPU-memory utilization and one engine sequence. There was one maximum Flex worker and no always-on worker. The account reported $0.69/hour running spend during the test.

| Test | Result |
|---|---|
| Original cold request | No answer before the bounded observation deadline; explicitly cancelled |
| Worker weight download | 226.967 seconds in the engine log |
| Weight loading | 1.08 seconds after download; model loading reported 13.8 GiB |
| Available KV cache memory | 5.88 GiB reported by the engine |
| Separate post-load streamed request | Complete in 2.380 seconds; first visible content at 2.160 seconds |
| Three-request batch | All complete in 0.827–3.134 seconds |
| Ten-request batch | All complete in 1.315–11.029 seconds |
| Five-turn conversation | All complete in 0.875–3.710 seconds per turn |

The cold request was cancelled before the post-load phase. Logs received at that boundary showed that weights had successfully loaded, providing new evidence for a separate post-load check rather than retrying the failed cold request. Nineteen post-load answers completed: fourteen streamed fixtures and five conversation turns. No automatic failed-request retry occurred.

The first four conversation answers were inspected and correctly tracked the constructed jar contents and a subsequent change. The last turn requested approximately 200 words and returned 1,294 characters in 3.710 seconds. This is engineering evidence, not biblical-language quality evaluation. Short streamed answers were used for the concurrency tests. The follow-up test was launched before the batch process had been explicitly reaped, so scheduling isolation is not asserted. One sequence means queued service, not ten simultaneous decoding streams.

## Interpretation and limits

**The 24 GB base-model route is feasible on this exact setup. Cold startup remains unacceptable for an ordinary chat experience.** Most of the observed delay was downloading weights. Eager mode did not remove that download, nor all kernel initialization. This was not a controlled comparison of eager mode: GPU, host and loading conditions also differed from v1.

Memory figures do not establish adapter fit, peak usage under long conversations or ten full-context users. The engine accepted an 8K setting, but the fixtures did not saturate that context. A different 24 GB GPU still needs its own test. No replacement quality claim or production recommendation is made.

The next infrastructure experiment should use the [pinned cache plan](SMALL-MODEL-CACHE-PLAN.md), verifying both the cache hash and effective engine revision. It must distinguish a first cache miss from a confirmed cache hit. Afterward, prepare the separate pre-training notice and export/load test for a tiny Tinker adapter. Keep the full original-language fine-tune behind that compatibility check and a fresh evaluation.

## Cleanup and costs

The native request was cancelled, all post-load requests finished, and the temporary endpoint/template were deleted. A subsequent GET verified endpoint absence and the account reported zero running spend. The independent 15-minute cleanup timer was stopped only after verified manual teardown. No persistent network volume was created.

Billing history still returned no rows, including a broader account-level date query. That is unresolved billing, not zero cost. Keep a $2 combined local reservation for v1/v2 under the original $10 ceiling pending provider reconciliation. Do not derive a per-question production price from these short initialization-heavy tests or from account-balance differences alone.

Private request/configuration receipts, log snapshots, cancellations and outputs are preserved in ignored `runs/small-model-serving-v2/`. The production branch, running model and application settings were not changed.
