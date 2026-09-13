# Inference options for retained Inkling B

Researched September 12, 2026. Research only: no weights exported, provider contacted, paid endpoint created, or live model changed. Streaming implementation is a separate, unfinished integration task.

## Recommendation

Seek a shared, usage-priced service that explicitly accepts the existing adapter before renting dedicated GPUs. Together, Fireworks and Baseten are credible providers to ask, but none of the documentation reviewed establishes a self-service, pay-per-token deployment for our exact B adapter. The inexpensive published Inkling API prices describe the standard model; they are not quotes for Meforash's trained model.

Keep a Thinking Machines production-serving inquiry as a parallel option. Its [pricing page](https://tinker-docs.thinkingmachines.ai/tinker/models/) separately lists an Inkling NVFP4 serverless beta at $1/M input and $4.05/M output, but discourages intensive production use and offers a production waitlist. Moving our existing checkpoint onto that offering, including adapter compatibility, requires confirmation. It is distinct from our current unsuffixed checkpoint path. Do not silently change precision or serving configuration.

## What must move

The retained model is full `thinkingmachines/Inkling` plus the original-text-only B adapter. Our [training record](INKLING-TRAINING.md) specifies rank 8 with attention, MLP and unembedding updates enabled. A host must apply all trained components; omitting unsupported output-head or expert tensors would change the model. B cannot simply be attached to Inkling-Small or another architecture.

The official [model card](https://huggingface.co/thinkingmachines/Inkling) identifies Apache 2.0, open weights, third-party product integration, 975B total parameters and 41B active per token. Open weights make external hosting plausible; active parameter count does not mean only 41B weights need memory. Preserve the applicable model/source notices and review the linked acceptable-use terms before migration.

## Hosting comparison

| Option | Confirmed capability | Exact B status / practical fit |
| --- | --- | --- |
| Together AI | Standard Inkling API; imported external adapters for dedicated inference | Candidate for a provider-assisted deployment. Inkling adapter eligibility, complete target support and deployment price remain unconfirmed. |
| Fireworks | Standard Inkling serverless and on-demand deployment; external PEFT import | Dedicated route documented. Inkling addon support and unembedding support need confirmation. |
| Baseten | Standard Inkling API, custom deployments and documented multi-LoRA engines | Ask about serving B on shared infrastructure. General multi-LoRA support is not confirmation of an Inkling pool or exact adapter compatibility. |
| vLLM on Modal, Runpod or another GPU host | Inkling serving and LoRA are documented by vLLM; rented hardware gives runtime control | Most controllable engineering route, but very high dedicated compute cost. Exact export/load parity still needs testing. |

[Together's adapter guide](https://docs.together.ai/docs/dedicated-endpoints/adapter) requires PEFT files and an eligible dedicated base. Its [Inkling page](https://www.together.ai/models/inkling) establishes base-model availability, not our adapter's eligibility. The public pages reviewed did not establish an Inkling serverless adapter pool.

[Fireworks' Inkling page](https://fireworks.ai/models/fireworks/inkling) lists standard serverless and on-demand use. Its [deployment guide](https://docs.fireworks.ai/fine-tuning/deploying-loras) routes trained models to dedicated deployments. Its [import requirements](https://docs.fireworks.ai/models/uploading-custom-models) accept rank 4–64, but document output-head LoRA for certain families without explicitly naming Inkling. This is an unresolved compatibility question, not proof that an assisted deployment is impossible.

[Baseten's pricing](https://www.baseten.co/pricing/) lists standard Inkling at $1/M input and $4.05/M output. Its [LoRA engine guide](https://docs.baseten.co/engines/engine-builder-llm/lora-support) describes runtime adapter switching and constraints on rank/modules. Neither establishes a price or supported import for B on the standard API.

## Economics

Together's [published standard-model pricing](https://www.together.ai/pricing) also lists $1/M input and $4.05/M output. At those rates, a hypothetical request with 2,000 input and 1,000 billable output tokens costs $0.00605; 1,000 such requests cost $6.05. This is arithmetic for a base API, not a custom-adapter quote or an observed average. Reasoning tokens, growing conversation context, caching and actual usage change costs.

For dedicated hosting, Hugging Face's [deployment guidance](https://huggingface.co/blog/thinkingmachines-inkling) estimates approximately 2 TB VRAM for BF16 and 600 GB for NVFP4; it lists four B300/GB200 GPUs for the latter. Adapter and concurrent-request memory need headroom. Quantized serving must be evaluated rather than assumed equivalent to our Tinker configuration.

For scale illustration only, [Modal lists](https://modal.com/pricing) B300 at $0.001972/GPU-second. Four cost about $28.40/hour, or $20,446 for 720 continuously warm hours, before CPU, RAM, storage and other charges. This is not a validated B deployment or capacity quote. Even ten warm hours would be about $284 in GPU compute. Scaling to zero can reduce billed time but introduces startup delay; we have not measured loading this model or adapter. A free, lightly used chat app is a poor fit for keeping this entire model exclusively allocated.

## Compatibility evidence and next steps

The [vLLM Inkling recipe](https://recipes.vllm.ai/thinkingmachines/Inkling) explicitly includes LoRA support and multi-GPU deployment. That establishes an engine-level route worth testing. The [Tinker export tutorial](https://tinker-docs.thinkingmachines.ai/tutorials/deployment/lora-adapter/) describes PEFT conversion, but its example is Qwen. The current [converter implementation](https://github.com/thinking-machines-lab/tinker-cookbook/blob/main/tinker_cookbook/weights/_adapter.py) warns that some MoE expert adapter serving remains experimental. General recipes do not prove our exact checkpoint works unchanged.

1. Obtain provider confirmation of full Inkling plus a private, imported rank-8 Tinker adapter including attention, MLP/experts and unembedding. Ask for shared billing first, minimum spend, concurrency, cold-start behavior, context limits, reasoning controls, retention and price.
2. Establish the matching base revision and supported precision. Our training records do not pin an exposed provider base-weight revision.
3. After owner approval, export privately and inspect all tensors, scaling, names and tokenizer/rendering assets. Reject missing or silently ignored components.
4. Run a separately budgeted private load/parity test against retained Tinker B. Check original-language handling, final-only streaming, usage accounting, latency and ten concurrent requests. Evaluate quantization separately if used. Do not require byte-identical sampling across different numeric runtimes, but do require complete adapter loading and investigate material behavioral differences.
5. Only then change the app backend, provider disclosures and cost controls, retaining the previous configuration for rollback.

No public weight release is needed for any of these routes. A private adapter can power a publicly accessible application. A smaller-model fine-tune is a separate future experiment if no affordable exact-B host emerges; it is not an inference-only migration and is not authorized by this research.
