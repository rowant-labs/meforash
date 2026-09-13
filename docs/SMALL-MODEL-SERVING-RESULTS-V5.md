# Longer idle test: startup-boundary completion race

September 13, 2026 UTC. Same pinned base/cache/worker configuration as [v4](SMALL-MODEL-SERVING-RESULTS-V4.md), on the isolated exploration branch. No training or production change.

## Intended measurement

After a completed startup request and warm streamed probe, leave the endpoint untouched for 120 seconds, then observe account spend and worker/job health at 120, 180, 240 and 300 seconds. Submit a single resume probe only after observing zero running spend, zero running workers and no queued/in-progress jobs. Otherwise remove the endpoint without a resume. This distinguishes actual scale-down from another warm response.

The preparation limit was six minutes from endpoint creation, with independent teardown after fifteen minutes. These limits and the measurement sequence were encoded before execution. No endpoint inspection calls were planned during the initial idle interval.

## Actual outcome and receipt limitation

**The idle test was not reached. The startup request completed at the stop boundary, but its answer was not retained.** The last saved status poll reported `IN_QUEUE`. The observer then called cancellation, whose receipt instead reported `COMPLETED` with `job is already completed`. Worker logs identify the same job and report generator completion and job finish at 05:37:32 UTC. These establish provider-reported completion; they do not establish correct or complete final answer content without the native result.

The observer incorrectly printed that preparation had stopped without a completed answer because it did not reconcile the cancellation receipt before cleanup. Preserve that diagnostic and the contradictory receipt; do not classify this as a confirmed cancelled job, inference failure or semantic failure. The endpoint was already removed when the race was identified, so no retrieval or repeat request was attempted. Future observers must inspect cancellation outcomes and fetch the final status/output when completion wins the race, before teardown. A transport timeout also requires reconciliation, not an automatic resubmission.

From local timestamps and worker logs, endpoint creation to logged job finish was approximately 361 seconds; submission to logged finish was approximately 348 seconds. These are cross-clock diagnostic intervals, not provider timing fields or streamed first-content measurements.

## Startup breakdown

| Log transition | Approximate interval |
|---|---:|
| Image ready / initializing model files (05:32:03) → model ready (05:34:54) | 171 s |
| Model ready → container creation (05:36:23) | 89 s |
| vLLM launch (05:36:25) → application startup complete (05:37:27) | 62 s |
| Loading the three weight shards, within engine startup | 1.17 s |

The model-status snapshot reported the exact pinned cache revision as `DEPLOYED` with a concrete mount path. Engine logs confirmed vLLM 0.29.0, the pinned model/tokenizer revision, native MXFP4 configuration, 13.8 GiB model memory and 5.88 GiB available KV cache. Runtime device memory was about 24 GB; the exact GPU product was not verified. As in v4, the CLI request selected the broader `AMPERE_24` pool.

This shows that slow first readiness extends beyond reading model weights. The 89-second platform gap is an observed interval, not a diagnosed scheduler bug. The approximately 41.3 GB repository layout remains a plausible contributor to preparation; transferred bytes were not measured. No kernel/precision/revision changes were made between v4 and v5.

## Decision and cleanup

Warm base serving remains demonstrated by v2/v4. Cold startup is variable, and this follow-up did not resolve idle shutdown or zero-cost resume. Do not recommend the present configuration for a sporadically used public chat on the assumption of consistently quick or precisely timed scale-to-zero behavior.

Stop repeating this unchanged setup. The next design should address platform preparation explicitly: compare a pre-provisioned worker with an agreed monthly budget, or a separately evaluated provider/artifact layout. Smaller runtime images or offline cache reads may reduce engine overhead but cannot be claimed to remove the observed pre-container delays. A future idle experiment must allow enough one-time preparation to actually reach idle, preserve completion/cancellation races, and retain a hard spending and teardown bound. No additional hosting purchase or training follows automatically from this diagnosis.

Endpoint and template deletion succeeded; both subsequent GETs returned 404. Final account running spend was zero, and the watchdog was stopped only after those checks. No persistent volume or active worker remains from this experiment. Billing records remain unreconciled: carry a $4 combined conservative reservation for v1–v5 under the original $10 ceiling, not a measured charge. Private receipts, the executed observer and sanitized logs remain in ignored `runs/small-model-serving-v5/`.
