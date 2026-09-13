# Modal gpt-oss-20b serving results v2

Status: **completed bounded pilot** on September 13, 2026. The versioned v2 baseline and all four snapshot requests completed successfully. Provider logs distinguish two snapshot-creation runs from two subsequent reuse runs, and all four snapshot boots returned the same correct constructed answer from the same pinned model. Both v2 Apps are stopped with zero tasks, no active pilot container remains, and the pilot Volume was deleted. Billing is provisionally reconciled below. No training, adapter loading, production migration or public deployment is part of this serving test.

## Controlled configuration

V2 keeps the v1 serving stack unchanged: `openai/gpt-oss-20b` at revision `6cee5e81ee83917806bbde320786a8fb61efebee`, vLLM 0.29.0 in image `vllm/vllm-openai@sha256:082ca6f035279109041ffd3fe0695cb568b29bc580b35c4f297a66a08b216c1b`, one NVIDIA L4, two physical CPU cores, 32 GiB host memory, an 8,192-token context limit, one sequence, eager mode and native `gpt_oss_mxfp4` quantization with the Marlin backend. LoRA remains disabled.

The preparation function downloaded and fully hashed the same 13 allowlisted root files used in v1. Their 13,789,263,104 logical bytes reproduced the expected manifest SHA-256 `5f8255b4762b7dc5fe67c74e79db77e3d560f7d951231e74a5870803b2a136e4`; preparation and verification took 304.902 seconds. At serving startup, v2 checked that manifest hash, file allowlist, pinned sizes and weight index without rehashing the three large weight files.

## Baseline

| Measurement | Client elapsed | Manifest verification | Engine ready | Local first final content | Local vLLM total | Result |
|---|---:|---:|---:|---:|---:|---|
| Scale-from-zero baseline | 182.237 s | 0.034 s | 169.298 s | 4.128 s | 4.961 s | HTTP 200, completed, stop |
| Immediate warm baseline | 2.108 s | inherited | already ready | 0.701 s | 1.522 s | HTTP 200, completed, stop |

Both calls returned the expected correct answer for the same constructed engineering prompt, with the same 93 prompt, 32 completion and 125 total tokens. This confirms serving behavior for that prompt; it is not a Bible-quality benchmark or evidence that the base model is preferable to retained fine-tuned Inkling B.

The cold request's 182.237 seconds include provider scheduling, container startup, the 169.298-second engine-ready phase and inference. The local vLLM numbers begin only after the method is running and must not be reported as startup-inclusive TTFT.

## Snapshot measurements

| Run | Provider classification | Client elapsed | Restore-hook wake | Local vLLM total | Result |
|---|---|---:|---:|---:|---|
| Snapshot 1 | creation and restoration | 251.923 s | 1.635 s | 1.212 s | HTTP 200, completed, stop |
| Snapshot 2 | creation and restoration | 401.014 s | 1.821 s | 1.772 s | HTTP 200, completed, stop |
| Snapshot 3 | reuse | 24.012 s | 1.609 s | 0.942 s | HTTP 200, completed, stop |
| Snapshot 4 | reuse | 121.286 s | 1.839 s | 1.680 s | HTTP 200, completed, stop |

The first two runs were creation runs. Their provider logs each explicitly recorded `Snapshot created. Restoring Function from memory snapshot.` after a fresh engine start, three internal warmups and a confirmed level-1 sleep. Snapshot 1 recorded 0.038 seconds for verification, 147.279 seconds for engine readiness, 2.493 seconds for warmup and 15.149 seconds for sleep. Snapshot 2 recorded 0.147, 159.278, 3.913 and 13.163 seconds for the same phases. The 251.923- and 401.014-second client measurements therefore include creation work and are not reuse latencies.

The next two runs had provider restoration logs without another creation sequence. Their metadata repeated the captured verification, engine-ready, warmup and sleep values from the corresponding creation snapshots rather than logging those phases again. Only the restore-hook wake measurement was new for each boot. This, together with four distinct boot tokens across the four responses, distinguishes four container boots without treating a hook call alone as proof of provider restoration.

All four snapshot responses reported the same pinned revision, manifest, vLLM 0.29.0, NVIDIA L4 class, native MXFP4 configuration and 8,192-token limit. All returned the same correct final answer and the same 93 prompt, 32 completion and 125 total tokens. These are serving-identity and completion checks for one constructed prompt, not an evaluation benchmark.

Reuse latency varied substantially: 24.012 seconds and 121.286 seconds end to end. For the fourth request, the provider logged restoration at 11:39:38 and the local wake request about 110 seconds later; once wake began, the measured wake and health phase took 1.839 seconds. The receipts do not isolate what happened during that preceding interval, so they do not support a precise root-cause claim or a precise raw snapshot-restore duration.

## Interpretation

V2 reduced serving-time manifest verification to 0.034-0.147 seconds and avoided reading the three large weight files during startup. Its 182.237-second baseline cold request was lower than v1's 238.061-second corrected cold request, but this is not a controlled causal comparison. The runs used different physical L4 allocations and may also differ in provider scheduling, image state, filesystem caching and transient load. The evidence supports the narrow claim that v2's lightweight identity check completed quickly while preserving the expected manifest; it does not establish how much, if any, of the total cold-start difference that change caused.

Snapshot reuse worked twice, but the 24.012- to 121.286-second spread is too large to claim a stable cold-start target or a causal performance improvement from the snapshot setting. The next serving step should investigate that remaining startup variance with bounded provider-phase evidence before any training proposal. No result here evaluates Bible quality or establishes adapter portability.

## Cleanup and provisional billing

Final private provider-state receipts show both v2 Apps stopped with zero tasks, zero active pilot containers and no remaining Volume. No pilot GPU compute remains active, and no pilot Volume remains to accrue storage use.

The account billing snapshot was $0.42 metered before v2 and $0.78 metered after teardown, a **$0.36 observed increase during the v2 window**. The final snapshot showed $0 billed and $0.78 in cumulative credits. These account-level values are provisional rather than a final invoice: late-posted execution or storage usage remains possible. Keep the full **$5 ceiling reserved until final reconciliation** instead of treating credits or the current billed amount as zero final cost.
