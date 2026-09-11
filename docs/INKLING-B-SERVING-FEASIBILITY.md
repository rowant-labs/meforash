# Inkling B serving feasibility

Status: feasibility finding, reviewed **September 9, 2026**. This note records documentation and local SDK findings. It does not report an export, third-party deployment, public launch, or training run.

## Current conclusion

The retained original-text adapter **B** can be used through Tinker's authenticated inference API. B is a rank-8 LoRA sampler checkpoint built on the full `thinkingmachines/Inkling` model. Tinker documents sampler checkpoints as the checkpoint type used for inference, and its native `SamplingClient` accepts a saved checkpoint through `model_path` ([SamplingClient](https://tinker-docs.thinkingmachines.ai/tinker/api-reference/samplingclient/), [checkpoint types](https://tinker-docs.thinkingmachines.ai/tinker/data-model/)). The project's private preview and evaluations already use this native path.

Tinker's OpenAI- and Anthropic-compatible endpoints also document that any valid sampler checkpoint can be used as the model ([OpenAI-compatible inference](https://tinker-docs.thinkingmachines.ai/tinker/compatible-apis/openai/), [Anthropic-compatible inference](https://tinker-docs.thinkingmachines.ai/tinker/compatible-apis/anthropic/)). This establishes API-level access for private and low-traffic application work. It does not yet establish production-hosting suitability: Tinker labels the compatible endpoints beta, describes them as intended for testing and internal low traffic, and says latency and throughput may vary. That is performance guidance, not a documented legal prohibition on a public application.

A public website could keep B private and route requests through a credentialed backend. The browser must not receive the provider key or private checkpoint reference. Publishing a Tinker checkpoint is unnecessary for this architecture.

## Keep B distinct from the available base models

Three related artifacts must not be treated as interchangeable:

- **B:** the project's full-Inkling, rank-8 original-text LoRA checkpoint. Its training recipe enabled attention, MLP, and unembedding adaptation.
- **Full Inkling base:** `thinkingmachines/Inkling`, a 975B-total, 41B-active mixture-of-experts model. Thinking Machines now publishes its open weights and documents local serving through vLLM, SGLang, Transformers, and other runtimes ([Thinking Machines](https://thinkingmachines.ai/inkling/), [official model card](https://huggingface.co/thinkingmachines/Inkling)).
- **Inkling-Small:** a different model. Its lower cost or hardware requirements do not make it a serving substitute for B.

B was trained against Tinker's 64K full-Inkling entry, not the 256K `:peft:262144` entry. Fireworks' serverless Inkling is also the unchanged base, not B. A host serving the base model alone would silently remove the project's fine-tuning.

## Rendering, sessions, and capacity

The current application uses Inkling's native renderer and sends exact token IDs through `SamplingClient`. Tinker's compatible chat endpoint applies the model's default Hugging Face chat template and directs checkpoints that need a different renderer back to the native client. Until template parity is measured, the native path is the safer way to preserve B's established behavior.

A Tinker `ServiceClient` creates a session that lasts with the client. A session can hold multiple sampling clients, each targeting one sampler checkpoint ([data model](https://tinker-docs.thinkingmachines.ai/tinker/data-model/)). Public documentation does not give a stable per-checkpoint latency, cold-start, concurrency, or throughput figure for B. The current private application therefore remains conservative: one request at a time, a 24,000-token input ceiling, an 8,192-token output ceiling, and a 300-second deadline.

For an invite-only preview, a small architecture is:

- Vercel for the web interface;
- a long-lived Railway Python backend that retains the native renderer and Tinker client;
- Supabase only if authentication and coarse per-user usage controls are needed.

This keeps model access server-side and fits the existing Python implementation. Whether it is suitable for broader traffic depends on measured latency, concurrency, failure behavior, and provider capacity; a formal SLA is one possible operational improvement, not a categorical launch requirement.

## Export and self-hosting remain unverified for B

Tinker's cookbook now documents two generic export paths: converting a downloaded checkpoint into a PEFT adapter and merging an adapter with a Hugging Face base model ([PEFT adapter tutorial](https://tinker-docs.thinkingmachines.ai/tutorials/deployment/lora-adapter/), [`build_hf_model`](https://tinker-docs.thinkingmachines.ai/cookbook/api-reference/weights/build_hf_model/)). Full Inkling itself has public weights and documented local runtimes.

Those facts do not prove that B is portable. B's training record did not pin a provider base revision, so byte identity with the current Hugging Face revision is unknown. No recorded test has converted B, verified all attention/MLP/unembedding tensors, attached it to the exact base, or compared external inference with Tinker. The official full-Inkling BF16 repository is also about 1.9 TB, placing direct self-hosting outside an ordinary application-host budget.

## Fireworks distinction

Fireworks currently serves the unchanged full Inkling base at `accounts/fireworks/models/inkling`. Its model page lists a 1.04M context and **$1.00 input / $0.17 cached input / $4.05 output per million tokens** ([Fireworks Inkling](https://fireworks.ai/models/fireworks/inkling)). Those prices do not apply to B.

Fireworks marks managed fine-tuning for its Inkling base as unsupported. That field does not by itself answer whether an externally trained adapter can be imported. Separately, Fireworks documents external PEFT adapter import, but says only some base models support LoRA addons and requires imported adapters to use dedicated on-demand deployments ([custom models](https://docs.fireworks.ai/models/uploading-custom-models), [LoRA deployment](https://docs.fireworks.ai/fine-tuning/deploying-loras)). Its current supported-architecture list does not name Inkling, and its documented `lm_head` LoRA support list does not include Inkling. Because B trained its unembedding component, exact import compatibility remains unknown.

If exact compatibility is established later, Fireworks would price B through a dedicated GPU deployment rather than the base model's serverless token rates. Current September 2026 on-demand list prices begin at **$8 per GPU-hour for H100/H200**, with B200 at **$13**, B300 at **$15**, and GB300 at **$20**, billed per GPU-second ([pricing](https://fireworks.ai/pricing)). The required Inkling-B shape and GPU count are unknown, so no defensible total hourly price is available.

## Current Tinker cost basis

Tinker's September 9 pricing lists the 64K full Inkling entry at **$1.87/M prefill**, **$0.374/M cached prefill**, and **$4.68/M sampled output**, under a limited-time 50% discount. Checkpoint storage is **$0.10/GB-month** ([models and pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/)).

The last recorded read-only metadata showed a 5.042 GB sampler and a 15.125 GB training-state checkpoint. At the current storage rate, retaining only the inference sampler is about **$0.50/month**; retaining both is about **$2.02/month**. Their recorded October 6 expiry must be rechecked before continued serving. These are estimates from recorded bytes and current list prices, not reconciled invoices or fixed future rates.

## Smallest next verification

Continue with a staged, bounded non-training check:

1. Compare B's saved model ID, rank, target flags, and unpinned revision with the current Inkling configuration and converter target-key support. This local/read-only step can find a definite mismatch without weights or provider activity.
2. Refresh read-only checkpoint metadata and retention, then run a very small native-backend probe using constructed engineering prompts. Keep exact rendering, cap output, record latency and failure behavior, and do not retry uncertain requests.
3. If export becomes part of the agreed scope, download and hash only B's sampler archive, convert it offline, and verify the exact base reference, rank, target modules, and complete tensor coverage before attempting a merge.
4. If third-party deployment becomes part of the agreed scope, establish Fireworks' exact Inkling addon eligibility and deployment shape before uploading anything or reserving capacity.

Passing the first two steps would support a bounded private or invite-only web preview. It would not prove B export, Fireworks compatibility, high-traffic capacity, or production readiness.
