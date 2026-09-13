# Modal serving pilot v2

Owner-authorized bounded follow-up, September 13, 2026, only on `codex/hosting-first-small-model`. Separate $5 ceiling; no training, adapter upload, public endpoint or production change. Preserve all v1 evidence.

Hypothesis: the v1 snapshot creation limit prevented reaching the restore path. Repeated full weight hashing also imposed avoidable startup work. This test does not assume either change will establish a fast restore.

Keep the v1 model revision, native MXFP4, immutable vLLM 0.29.0 image, L4, two CPU cores, 32 GiB memory limit, eager mode, 8K context and one sequence. Change initialization allowance from 300 to 900 seconds. Fully hash model files during CPU preparation and require the exact v1 manifest hash; serving checks that manifest, file sizes and allowlist without rereading the weight shards. Use a separate read-only serving Volume and separate v2 Apps. Add per-stage timings and per-boot identifiers.

Root-only sequence: build from an isolated module-only directory; prepare pinned files; collect baseline cold and warm complete answers; stop baseline and verify zero containers; collect up to four snapshot-version answers, with observed zero containers between calls. Creation and restore are classified from provider logs, not inferred from response speed or hook names. Stop on failure rather than silently changing configuration or retrying indefinitely. Every submitted call receives a private receipt; completion is reconciled before cancellation and cleanup.

A 65-minute orchestration deadline and independent 70-minute stop watchdog bound execution. At most one GPU worker may run across test Apps at a time. The account's v1 rate for this allocation was $1.1506 per GPU-worker hour including CPU and memory; retain the full $5 ceiling pending final billing, including preparation/storage and provider timing uncertainty. Preparation has no GPU. No worker performs provider calls or reads credentials.

Success requires correct complete final content, matching model identity, verified restore evidence and measured startup-inclusive latency. A serving pass is not a Bible-quality benchmark or adapter-portability result. Delete the temporary Volume and verify stopped Apps/zero containers at the end. Keep credentials, private receipts and account IDs outside publication.

## Outcome

The bounded run completed all planned requests. Two snapshot creations succeeded, followed by two verified reuse starts taking about 24 and 121 seconds. All returned complete matching engineering answers. Cleanup was verified. See [v2 results](MODAL-SERVING-RESULTS-V2.md); startup latency remains variable and no training or production change occurred.
