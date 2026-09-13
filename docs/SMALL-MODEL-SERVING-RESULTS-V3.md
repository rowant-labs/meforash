# Pinned-cache startup test

September 13, 2026 UTC. Isolated `codex/hosting-first-small-model` branch. No training, adapter, production change or weight release.

## Result

**The pinned cache was assigned correctly, but this bounded first-start attempt returned no answer.** The native request remained queued while Runpod initialized the host-side model files. It was explicitly cancelled after approximately five minutes; endpoint and template teardown finished 317 seconds after submission. This is a hosting startup result, not a model-quality failure.

The CLI requested the same A5000 24 GB configuration as [v2](SMALL-MODEL-SERVING-RESULTS-V2.md); the created endpoint reported the `AMPERE_24` pool. Runtime GPU identity was not reached or verified. The setup retained the pinned worker image, native MXFP4 model, eager mode, 8K context and one engine sequence. Zero minimum / one maximum worker, 60-second idle timeout and 180-second execution timeout were configured. Queue waiting is separate from the execution timeout; an independent 15-minute cleanup process also guarded this test.

The official runpodctl v2.14.0 binary was verified against its release SHA256 checksum. Its documented `--model-reference` option attached:

```text
https://huggingface.co/openai/gpt-oss-20b:6cee5e81ee83917806bbde320786a8fb61efebee
```

The model-status API resolved exactly that hash and reported `ASSIGNED`, with no failure reason. System logs reported `image ready, model pending download`, then `image ready, initializing model files`. At the last observation, the worker remained `INITIALIZING`; the reported mount path was null. No engine startup logs or generated answer were available, so actual cache consumption and the effective engine revision were **not verified**. The environment revision pin alone does not prove execution.

There was no successful cache-hit, warm-answer or post-scale-down measurement in this attempt, and no repeated provisioning. The already successful v2 warm-serving measurements remain separate evidence.

## Interpretation

Runpod [documents](https://docs.runpod.io/serverless/endpoints/model-caching) that it delays worker startup when a host must download a cached model, without charging worker time for that download. Account running spend was zero at the in-progress check, consistent with that behavior. This does not establish a zero final charge or show how long the download would eventually take.

This configuration missed the one-minute first-answer target. It does not prove that a previously populated cache or FlashBoot resume would be equally slow. Before recommending sporadic public traffic, a separate bounded test must first establish completed cache preparation, then measure a confirmed cache hit and idle/resume behavior. Do not promise that caching removes cold starts. Longer initialization, a persistent warm worker, or a different model/provider are explicit tradeoffs rather than fixes established here.

## Cleanup and accounting

The request was cancelled. Endpoint and template deletion succeeded; subsequent GETs returned 404 for both. Account running spend was zero after cleanup, and only then was the independent cleanup process stopped. No persistent network volume was created.

Both legacy billing and the newer account-wide/serverless billing APIs still returned no usage records. Empty reports are not proof of free use. Retain the combined $2 provisional reservation for v1–v3 under the original $10 exploration ceiling until provider records reconcile; it is a local contingency, not a measured charge. Prior account-balance movement is evidence of spend but not an endpoint invoice.

Private configurations, CLI checksum, model-status receipts, sanitized system logs, cancellation and cleanup receipts are retained in ignored `runs/small-model-serving-v3/`. The existing 17 cost/probe checks passed; no application code was changed.

Next: resolve the startup strategy and prepare a separately authorized tiny adapter portability experiment. Full original-language adaptation and fresh biblical evaluation follow only after the export/load path works.
