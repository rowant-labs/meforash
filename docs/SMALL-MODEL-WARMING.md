# Smaller-model warming flow

September 13, 2026. Exploration branch only. The owner accepted preparing early warming after the hosting review. The live app remains on Inkling B; there is no public wake endpoint and no new provider deployment in this increment.

## Intended experience

Begin an optional wake when an eligible visitor first focuses the composer or types. Do not send their draft or generate a throwaway answer. A page load only retrieves inexpensive app status; passive visitors, link previews and refreshes must not automatically start a GPU. Multiple visitors share the same in-progress wake.

While actual model startup is confirmed, show “Waking up the model. You can keep writing your question.” If the visitor submits before readiness, preserve the existing draft/conversation and accepted request, continue automatically when ready, and distinguish warming from queueing and generating. Show elapsed time rather than an invented percentage or deadline. Use an accessible polite status region. A slow answer from the current Tinker service is not evidence of a cold start and must not receive this label.

The future gateway keeps provider credentials private and checks access, remaining question allowance, origin/CSRF protections and global spending availability before dispatch. A wake does not consume a question, but does consume hosting budget. Cap global wake frequency, coalesce across visitors, enforce maximum one pilot container and avoid recurring browser keepalives. Start with a five-minute provider idle window for a bounded integration comparison, not a promised production default. Read-only status checks must not invoke a remote GPU function or reset its idle timer.

## Offline implementation

`bibleprep/warmup_gate.py` is a deliberately unconnected, single-process coordination prototype. It returns one private dispatch ticket, tracks confirmed warming/ready/asleep and unknown states, limits wake attempts, and rejects stale callbacks from previous attempts or out-of-order observations within the same attempt. Readiness expires based on observation time rather than delayed callback arrival. Unknown provider outcomes and expired readiness require reconciliation rather than silently launching another wake. Its tests cover simultaneous visitors, denied access, polling, stale callbacks, timeout uncertainty and attempt limits.

This is not an HTTP implementation, billing guard, durable queue or provider adapter. `eligible` is supplied by the future gateway after its checks; it must never be trusted directly from browser input. Gate state loss on process restart requires provider reconciliation before allowing another wake. Multiple gateway processes require a shared durable lock and attempt ledger. Readiness must verify the configured model and adapter, not merely a live container. Serving invocations can still race with scale-down, so generation needs its own startup/error handling even after a ready observation.

## Remaining integration acceptance

After live adapter loading passes, add the disabled-by-default gateway integration and composer status on this branch. Test one wake across concurrent visitors, expired sessions/quotas, repeated focus, reloads, blocked budgets, startup failure, disconnect/reconnect, preserving an already submitted question, and a provider that scales down immediately after reporting ready. Confirm no draft leaves the browser until submission, no status poll keeps compute warm, and startup failure settles request quota without duplicate inference. Measure cost for visitors who leave without submitting as well as completed questions.

## Evidence and alternatives

Our six verified Modal snapshot restores took 31–109 seconds to first text (median 84 seconds): [v3 results](MODAL-SERVING-RESULTS-V3.md). Early warming overlaps that delay with reading/typing; it does not eliminate it. Modal bills retained idle resources: [cold-start documentation](https://modal.com/docs/guide/cold-start).

Baseten explicitly supports waking a scaled-to-zero deployment in anticipation of interaction: [wake operation](https://www.baseten.co/resources/changelog/wake-scaled-to-zero-models/). It remains an untested fallback, not a demonstrated faster host for this adapter. Fireworks directs custom LoRA models to on-demand deployments, and Together documents dedicated adapter endpoints: [Fireworks](https://docs.fireworks.ai/serverless/overview), [Together](https://docs.together.ai/docs/dedicated-endpoints/adapter). No verified inexpensive shared custom-adapter alternative was identified in this review.
