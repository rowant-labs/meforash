# Modal gpt-oss-20b serving results v3

Status: **completed bounded pilot** on September 13, 2026. The resumed campaign completed eight classified starts: two snapshot-creation starts followed by six verified snapshot-reuse starts, reaching the prospective six-reuse goal within the ten-start limit. The valid creation result from the original collector run is preserved separately. Both v3 App records are stopped with zero tasks, no active pilot container remains, and the pilot Volume was deleted. Billing is provisionally reconciled below.

## Purpose and controlled change

V3 keeps the v2 model and serving configuration unchanged: the same pinned `openai/gpt-oss-20b` revision and manifest, vLLM 0.29.0 image, NVIDIA L4 class, native MXFP4 path, two physical CPU cores, 32 GiB host memory, 8,192-token context, one sequence, eager mode, snapshot preparation and constructed prompt. LoRA remains disabled.

Only measurement attribution changed, along with versioned App and Volume names. The streaming method now attaches runtime identity to its terminal event inside the same remote call and writes a content-free completion marker carrying that request nonce and boot token to the provider's container log. The private client persists each final-text event as it arrives and measures three client-observed network boundaries:

- **first content**: arrival of the first final-answer text fragment;
- **last content**: arrival of the last final-answer text fragment; and
- **terminal**: arrival of the terminal event after same-call runtime metadata is collected.

The last-content-to-terminal interval includes stream finalization and runtime same-container metadata work; it is not hidden model reasoning or a raw provider snapshot duration.

## Measurements

| Campaign start | Classification | First content | Last content | Terminal | Last-content to terminal | Result |
|---|---|---:|---:|---:|---:|---|
| Original start 1 | snapshot creation | 245.477 s | 245.764 s | 245.912 s | 0.149 s | HTTP 200, completed, stop |
| Resumed start 1 | snapshot creation | 269.506 s | 269.836 s | 269.908 s | 0.072 s | HTTP 200, completed, stop |
| Resumed start 2 | snapshot creation | 451.548 s | 452.106 s | 452.207 s | 0.100 s | HTTP 200, completed, stop |
| Resumed start 3 | snapshot reuse | 56.166 s | 57.013 s | 57.015 s | 0.002 s | HTTP 200, completed, stop |
| Resumed start 4 | snapshot reuse | 95.295 s | 95.963 s | 96.302 s | 0.339 s | HTTP 200, completed, stop |
| Resumed start 5 | snapshot reuse | 30.954 s | 31.719 s | 31.817 s | 0.098 s | HTTP 200, completed, stop |
| Resumed start 6 | snapshot reuse | 108.840 s | 109.451 s | 109.566 s | 0.115 s | HTTP 200, completed, stop |
| Resumed start 7 | snapshot reuse | 82.653 s | 83.272 s | 83.375 s | 0.103 s | HTTP 200, completed, stop |
| Resumed start 8 | snapshot reuse | 86.013 s | 86.751 s | 86.855 s | 0.104 s | HTTP 200, completed, stop |

All eight resumed starts returned the same correct final answer and token counts for the fixed constructed engineering prompt and reported the same pinned model, revision, manifest and runtime configuration. Each receipt nonce matched its provider completion marker, and all eight nonces and boot tokens were unique. The two resumed creation logs explicitly recorded snapshot creation followed by restoration before the external response. Those creation measurements include fresh engine startup, warmups, sleep, snapshot creation, restoration, wake and inference, so they do not count toward the reuse goal. The next six logs recorded restoration without another creation sequence and were classified as verified reuse.

Across the six reuse starts, client first content ranged from **30.954 to 108.840 seconds**, with a median of **84.333 seconds**. Client terminal arrival ranged from **31.817 to 109.566 seconds**, with a median of **85.115 seconds**. These are descriptive summaries of six bounded observations, not formal latency statistics; no p95 or population estimate is reported.

## Collector interruption and resume

The original collector received and durably saved a complete 245.912-second response. Its immediate log fetch did not yet contain the completion marker, so the collector correctly refused to bind the response to a provider container, marked the classification step failed and ran cleanup. A later captured provider log contains the matching marker. That late evidence establishes the original response as a valid snapshot-creation result; the failure was log-availability lag in the collector workflow, not an inference or model failure.

The resumed collector tolerates bounded log delay. It classified its first two starts as 269.908- and 452.207-second creation runs, then obtained all six required reuse starts in its next six attempts. The root operator subsequently stopped both historical v3 App records, verified zero tasks and active containers, and deleted the Volume.

## Current limits

The v3 same-call receipts and provider markers confirm that snapshot reuse functions, while its 31.817- to 109.566-second terminal range confirms substantial start-to-start latency variance. V2's 24.012- and 121.286-second reuse results show the same broad pattern under the earlier instrumentation. These measurements do not explain the variance or establish a service-level target.

Base serving and snapshot functionality are now confirmed well enough to stop repeating the same base-only measurement. After cleanup, the next technical serving experiment should be a separately bounded live adapter-loading check against the same pinned base, with exact adapter identity and base-versus-adapter behavior controls. That is a portability recommendation, not authorization for full training. No adapter ran in v3. The fixed prompt remains an engineering fixture rather than a Bible evaluation, and these measurements provide no model-quality or production-readiness proof.

## Cleanup and provisional billing

Final private provider-state receipts show both v3 App records stopped with zero tasks, zero active pilot containers and no remaining Volume. No pilot GPU compute remains active, and no pilot Volume remains to accrue storage use.

The account billing snapshot was $0.78 metered before v3 and $1.39 metered after final teardown, a **$0.61 observed increase across the original and resumed v3 campaign**. The final snapshot showed $0 billed and $1.39 in cumulative credits. These account-level values are provisional rather than a final invoice: late-posted execution or storage usage remains possible. Keep the full **$5 v3 ceiling reserved until final reconciliation** instead of treating credits or the current billed amount as zero final cost.
