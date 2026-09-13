# Modal gpt-oss-20b serving results v1

Status: **completed bounded pilot** on September 13, 2026. The plain Modal serving baseline qualified with two completed scale-from-zero requests, a warm request, a warm streamed request and confirmed zero containers after baseline shutdown. The bounded snapshot attempt completed its internal preparation but exceeded the runner-startup deadline before any external probe or verified restore; it did not pass. All four pilot App records are stopped with zero tasks, the final provider-state check found zero active containers, and the pilot Volume was deleted. Invoice reconciliation remains open. These results do not authorize training, an adapter test, a production deployment, a model change or publication of weights.

## Scope and identity

This is a serving feasibility measurement for the unchanged `openai/gpt-oss-20b` base at revision `6cee5e81ee83917806bbde320786a8fb61efebee`. It uses the image `vllm/vllm-openai@sha256:082ca6f035279109041ffd3fe0695cb568b29bc580b35c4f297a66a08b216c1b`, vLLM 0.29.0, one NVIDIA L4, an 8,192-token context limit, one sequence, eager execution and a 0.85 GPU-memory target. Snapshots were disabled for the qualified baseline, and LoRA remained disabled throughout the pilot.

Private runtime evidence confirmed:

- the requested GPU was an NVIDIA L4 with compute capability 8.9 and 23,034 MiB reported memory;
- both the installed vLLM package and its local API reported version 0.29.0;
- the served ID and revision-bound local manifest matched the selected base;
- the engine selected `gpt_oss_mxfp4` quantization and the Marlin MXFP4 MoE backend;
- weight loading took 5.01 seconds; and
- the engine reported 13.8 GiB for model loading and 4.58 GiB available for its KV cache.

The preparation step fetched only the 13 allowlisted repository-root files. Their logical size was 13,789,263,104 bytes, and preparation plus verification took 213.270 seconds. Logical bytes are not a network-transfer or storage-billing measurement.

## Baseline measurements

| Measurement | Client elapsed | Local vLLM first event | Local vLLM first final content | Local vLLM total | Result |
|---|---:|---:|---:|---:|---|
| Corrected request from scale zero | 238.061 s | 1.434 s | 2.067 s | 2.919 s | HTTP 200, completed, stop |
| Immediate warm request | 2.105 s | 0.109 s | 0.695 s | 1.512 s | HTTP 200, completed, stop |
| Request after observed scale-to-zero | 205.060 s | 1.350 s | 1.934 s | 2.742 s | HTTP 200, completed, stop |

The cold numbers are submission-to-result and include Modal scheduling, container startup, engine initialization and inference. The local vLLM timings begin only after the method is running, so they are not cold-start-inclusive TTFT. All three completed `probe` requests returned the same final answer and the same token counts: 93 prompt, 32 completion and 125 total tokens.

The authenticated streaming method was also exercised while warm. Client-visible final text first arrived after 1.305 seconds and the stream completed after 2.082 seconds; the corresponding local vLLM timings were 0.100 seconds to first event, 0.682 seconds to first final content and 1.494 seconds total. This measures client-visible streaming separately from server-local work.

After the initial warm request, six private container observations covered about 79.4 seconds. The container was still visible through the fifth observation and absent by the sixth. The completed 205.060-second request was then submitted from that observed zero state. After baseline testing, the App was stopped and a separate provider-state check returned zero active containers. These observations establish one autoscale-to-zero event and confirmed baseline shutdown, not a guaranteed shutdown latency.

The baseline establishes successful serving and repeatability for one constructed engineering prompt. It is not a Bible-quality benchmark and makes no claim about the base model relative to retained Inkling B.

## Corrected setup failures

The first image build exposed a Python packaging mismatch: Modal could not determine the Python version in the pinned upstream image because its expected `python` executable link was absent. Adding a link to the image's existing `python3` made the private class deployable; this did not alter vLLM or model bytes.

The first serving attempt then stopped during engine startup because vLLM 0.29.0 rejected the obsolete `--disable-log-requests` flag. That attempt was cancelled and the App was stopped before retry. Replacing it with vLLM 0.29.0's `--no-enable-log-requests` form produced the measurements above. These were wrapper and command-line integration failures before a model answer, so they are not model-quality failures and provide no adverse inference result.

## Snapshot attempt

The snapshot App used the same pinned base, revision, L4, vLLM 0.29.0, native `gpt_oss_mxfp4` quantization, Marlin backend, context and concurrency settings as the baseline. Its internal preparation loaded 13.8 GiB of model memory, with weight loading taking 4.64 seconds, and completed all three constructed warmup requests with HTTP 200 responses.

The level-1 sleep operation then completed successfully. vLLM reported 18.42 GiB freed in total: 13.88 GiB backed up in CPU memory and 4.54 GiB discarded. It reported 20.549 seconds to enter sleep, and both the sleep request and the following sleep-state check returned HTTP 200.

Modal subsequently failed the runner for remaining in initialization for 390 seconds. No external probe completed, and the receipts contain no verified snapshot restore. The root operator cancelled the outstanding request and stopped the snapshot App rather than extending the bounded deadline. This is a bounded startup failure for this pilot configuration. It does not establish intrinsic L4, vLLM, gpt-oss or GPU-snapshot incompatibility, and it provides no restored-cold-start performance measurement.

## Cleanup and provisional billing

Final private provider-state receipts show all four pilot App records stopped with zero tasks, zero active containers and no remaining Volume. No pilot compute remains active, and no pilot Volume remains to accrue storage use. The snapshot attempt did not reach a verified restore; nothing in the qualified baseline or failed bounded snapshot startup demonstrates future adapter portability.

The billing snapshot reported **$0.42 metered**, **$0 billed** and a **$0.42 credit adjustment**. Its metered breakdown was $0.41625023 for deployed Apps, $0.00085253 for ephemeral Apps and $0 for Volume storage and model tokens. These values are a provider billing snapshot, not a final invoice: late-posted snapshot execution or storage usage remains possible. Keep the full **$5 ceiling reserved until final reconciliation** rather than treating the current $0 billed figure as final cost.

The authorization remains the separate $5 serving-test ceiling recorded in [the preflight](MODAL-PILOT-PREFLIGHT.md). Retained fine-tuned Inkling B remains the Bible model. No training, adapter loading, production migration or public deployment occurred in this pilot.

## Next gates before training

1. Diagnose the snapshot initialization deadline and separate file verification, engine startup, snapshot creation and restore timings. A future bounded attempt may need a longer creation timeout; do not silently extend this completed run or claim a speedup before a verified restore. Modal describes multiple creation starts before reuse, so one failed creation attempt is insufficient to assess steady-state restore behavior. [Modal memory snapshots](https://modal.com/docs/guide/memory-snapshots)
2. Demonstrate adapter loading and identity preservation on the selected inference stack before paying for a full adaptation. A base-model serving pass does not establish export compatibility or correctness after sleep/wake.
3. Freeze a prospective English Bible evaluation and compare the smaller base against retained B with matched source context. Keep quality and serving measurements separate; one engineering prompt tests neither biblical languages nor historical interpretation.
4. Present the exact training method, reviewed data, evaluation and cost ceiling to the owner before training. Production stays on B unless a later measured comparison and deployment review justify migration.
