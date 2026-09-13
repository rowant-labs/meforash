# Startup alternatives after the Runpod pilots

Research checked September 13, 2026. Isolated exploration branch only. This is a provider comparison and proposed experiment, not a deployment or training authorization. No new provider resources were created for this research.

## Recommendation

Test **Modal with pre-staged weights first, then GPU memory snapshots if compatible**. Keep Baseten as the managed alternative. Continue with the same unchanged gpt-oss-20b revision initially, so a provider change is not mixed with a model change. Neither route has been measured here, and neither establishes future Tinker adapter compatibility.

The reason for choosing Modal is its explicit ability to snapshot initialized CPU/GPU state, addressing library and engine initialization as well as cached files. Our Runpod tests found fast local weight loading but variable pre-container and engine startup. Modal is a different preparation mechanism worth testing, not a promise of faster startup. Its GPU snapshot feature is **alpha**; storage-bound loading and platform scheduling can still dominate. [Snapshot guide](https://modal.com/docs/guide/memory-snapshots), [LLM inference guide](https://modal.com/docs/guide/high-performance-llm-inference).

## Costs in context

Arithmetic scenarios below use total billed replica hours, including charged startup and warm-idle periods. They are not website uptime, active-user hours or a measured monthly bill. Storage, build costs, transfer, regional premiums and the existing application services are excluded. Plans/account eligibility must be verified before a paid pilot.

| Configuration | Planning hourly cost | 20 billed hours | 100 billed hours |
|---|---:|---:|---:|
| Modal L4, GPU only | $0.7992 | $15.98 | $79.92 |
| Modal L4 + allowance for 2 physical CPU cores and 32 GiB RAM | $1.149264 | $22.99 | $114.93 |
| Baseten L4:4x16, includes 4 vCPUs and 16 GiB host RAM | $0.8484 | $16.97 | $84.84 |

Modal lists $0.000222/GPU-second, $0.0000131/physical-core-second and $0.00000222/GiB-second. The resource-inclusive row assumes those CPU/RAM quantities are billed for the full interval; actual resource use and requirements need measurement. Starter lists $30 monthly compute credits with no plan subscription fee. Do not count shared credits twice or assume they cover storage. [Modal pricing](https://modal.com/pricing).

Baseten lists $0.01414/minute for L4:4x16. Its host RAM is half the Modal allowance, so the rows are not equivalent capacity or throughput comparisons. The exact model's peak host RAM and adapter fit on that SKU are unknown; a larger supported SKU could cost more. [Baseten instance table](https://docs.baseten.co/deployment/resources).

Modal charges retained warm resources during its scale-down window. Baseten's default scale-down delay is 900 seconds and is configurable from 0 to 3,600 seconds; startup is billable and replica billing is by the minute. A low hourly rate is not sufficient if scattered visitors repeatedly incur long startup/idle windows. [Modal cold-start billing](https://modal.com/docs/guide/cold-start), [Baseten scaling](https://docs.baseten.co/deployment/autoscaling/overview).

## Preparation mechanisms and limitations

**Modal:** download only the pinned root safetensors shards, index, configuration and required tokenizer assets into a versioned volume during preparation; exclude the separate Metal and original-format weight copies. Hash the selected files and retain notices. Use an explicit local snapshot path with complete tokenizer/configuration assets, then verify offline loading before relying on it. This removes an upstream model download from request handling, but does not remove the cost/time of the initial preparation.

Run a plain cached baseline before enabling GPU snapshots. Snapshot construction should use fixed engineering warmup prompts, never user conversations. Restore a clean model state and verify that warmup KV state does not appear in subsequent requests. Volume contents changing does not automatically invalidate Modal snapshots. Use immutable artifact paths plus an explicit code/configuration version change whenever model, tokenizer, engine or adapter bytes change; rebuild and verify the snapshot. Modal's published vLLM snapshot example uses a different model, H100 hardware and vLLM 0.15.1; do not copy it unchanged into the project's vLLM 0.29.0 native-MXFP4 configuration. The example also exposes unauthenticated service access and internal sleep/wake facilities, which must not be carried into a public-facing pilot. [Official example](https://modal.com/docs/examples/lfm_snapshot).

**Baseten:** its weight delivery network mirrors and caches weights near replicas and supports custom containers. This could improve the platform preparation stage without introducing GPU snapshots, but does not guarantee fast engine initialization. A private custom vLLM container is the candidate path for a future adapter; an unchanged-model catalog API does not serve our adapter. Tune and measure actual scale-down rather than leaving the default fifteen-minute delay. [Weight delivery network](https://docs.baseten.co/development/model/bdn), [cold starts](https://docs.baseten.co/deployment/autoscaling/cold-starts).

**Always-on serving:** keeping a worker ready avoids scale-from-zero latency but trades away the main low-traffic saving. Even the $0.7992/hour Modal GPU alone is about $575 for 720 hours, before host resources. A separately priced dedicated GPU or scheduled warm hours could be considered if traffic justifies them; this review has not established an always-on offer within the owner's earlier approximate $100 scale. Do not equate 100 billed hours with a continuously warm month.

## Proposed next measurement

Prepare one authenticated Modal service with one maximum L4 container, zero minimum containers, explicit resource limits, a short documented scale-down window and a hard external teardown guard. Keep 8K context, one engine sequence, native MXFP4, low reasoning and the pinned base/engine initially. Confirm L4 kernel support and snapshot compatibility before paid execution; do not substitute a larger GPU automatically.

Snapshots require deployed Apps; an ephemeral `modal run` does not test restoration. Compare two otherwise identical configurations sequentially, keeping at most one test GPU active: snapshot off, then snapshot on. Modal documents that GPU snapshot preparation can need two or three starts per GPU type. Require an actual restore receipt; do not count those creation runs as restored cold starts. L4 is a supported Modal GPU choice but the exact L4/snapshot/gpt-oss/vLLM combination is unverified.

Measure these separately: first artifact preparation; cached plain startup; snapshot creation if supported; up to three verified fresh cold starts per configuration within the budget, distinguishing snapshot restorations from snapshot creation; warm response; and response after **observed** scale-down. Record complete answer receipts, first-visible content, finish time, host/GPU memory, billed runtime and shutdown. Reconcile a completed job when cancellation races with completion, preserving outputs before teardown. Never infer zero cost from a short answer or zero minimum containers alone.

Use constructed fixtures only. If the plain baseline fails, stop before snapshots. If snapshots fail, preserve that outcome and assess the plain baseline; no silent engine downgrade. Adapter export/load testing and fresh Bible quality evaluation remain later gates. In particular, verify adapter identity and nonzero adaptation before and after sleep/restore; an alias alone does not establish that LoRA tensors survived. An [upstream report](https://github.com/vllm-project/vllm/issues/53888) describes silent LoRA loss after sleep/wake on a different version and hardware/quantization setup; it is a reason to test, not proof that our proposed setup fails.

A proposed $5 pilot ceiling needs a current account/resource preflight and allocation before execution. The previous Runpod $4 conservative reservation remains separate and unreconciled; this note does not silently reset or expand that campaign's spending guard. Production stays on retained Inkling B, and no weights need to be published for this comparison.
