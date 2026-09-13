# Cached base startup and short idle observation

September 13, 2026 UTC. Exploration branch only; unchanged base model, no training or production change.

## Measured result

The pinned gpt-oss-20b cache reached `DEPLOYED` with a non-null path, and vLLM 0.29.0 successfully loaded the pinned model/tokenizer revision. Logs show three local safetensors shards loading in 1.17 seconds, 13.8 GiB model memory, 5.88 GiB available KV cache memory and kernel autotuning lasting about 17 seconds. This is consistent with use of prepared weights; actual downloaded bytes and filesystem-level cache reads were not instrumented. No multi-minute in-engine weight download was observed.

| Measurement | Result |
|---|---:|
| First native request, provider queue/startup delay | 135.187 s |
| First native request, provider execution | 1.518 s |
| First request combined | 136.705 s |
| Warm streamed request: first visible content / completion | 0.803 / 0.944 s |
| After 90 seconds idle: first visible content / completion | 1.086 / 1.313 s |

Endpoint setup preceded the first request by 52.186 seconds, so the approximate creation-to-first-completion interval was 188.891 seconds. The request time must not be presented as the full endpoint preparation time. The native request was polled rather than streamed, so its first-visible-token latency was not measured.

All three constructed engineering requests completed. The two streamed probes returned just 34 visible characters each; these are not representative long Bible answers or quality evaluations. No failed request was automatically retried.

## What improved, and what remains unresolved

The cache now reached successful model execution, unlike [v3](SMALL-MODEL-SERVING-RESULTS-V3.md). Remaining initialization includes platform startup, Python/engine startup and GPU kernel warmup. The first answer still missed the one-minute target. Placement, prior host preparation and runtime hardware are not controlled across attempts, so this is not a causal speedup percentage.

**The 90-second idle check did not demonstrate scale-to-zero or FlashBoot resume.** Before and after that interval, health reported one running worker, two completed jobs and no queued or active jobs; account running spend remained $0.69/hour. A configured 60-second idle timeout was echoed by the endpoint. The second streamed answer therefore measures another warm request, not an unbilled suspended worker waking up. A longer observation is needed to determine when this setup actually stops billing, followed by a request only after an observed shutdown.

The CLI requested A5000, but it selected the broader `AMPERE_24` group. The retained endpoint receipt records the group rather than an exact runtime GPU product. Runtime logs establish approximately 24 GB device memory, not the exact GPU product name. Do not label this an independently verified A5000 repeat. Zero minimum / one maximum worker was retained. The final model-status snapshot exposed two additional idle worker records, but only one running worker was observed; these records do not establish simultaneous paid execution.

## Boundaries and cleanup

The preparation budget was ten minutes from endpoint creation, guarded by independent deletion at fifteen minutes. Success occurred within that window. The observer ran one warm request, waited ninety seconds, ran one more request and removed the endpoint and template. Both deletion receipts were followed by HTTP 404 checks; final account running spend was zero. The watchdog was stopped after teardown verification. No persistent volume was created.

Provider billing remains unreconciled; initial v2 billing queries still returned no records. Retain a $3 combined conservative reservation for v1–v4 under the original $10 exploration ceiling, including a $1 incremental reserve for this attempt. This is not a measured charge or a per-question price.

Private configuration, timing, probe, log and cleanup evidence is retained in ignored `runs/small-model-serving-v4/`. See the [cache diagnosis](SMALL-MODEL-CACHE-DIAGNOSIS.md) for repository-size and path findings. The next serving question is actual idle shutdown/resume behavior; adapter training remains separate and unstarted.
