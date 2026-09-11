# Checkpoint preservation

Launch follow-up, September 10, 2026: expiry was removed from both existing B checkpoints under the authorized hosted-launch work after an exact $2.02/month storage notice. A separate provider listing verified both unchanged references remain private and have no expiry. The original receipts and the proposal below are preserved. This establishes provider retention, not independent export or training-optimizer restoration. Private receipt: `runs/launch-v1/preservation-result.json`.

Status: read-only metadata finding and proposed operation, 2026-09-07 local time. No retention change, export, download, model inference, or training was performed. The redacted private receipt is `runs/checkpoint-preservation-v1/read-only-metadata.json`.

## Current evidence

A read-only metadata check at **2026-09-08 01:52:24 UTC** matched both exact private references in the original B receipt to the same owned Inkling run. The sampler is 5,042,146,156 bytes and expires **2026-10-06 15:58:33 UTC**. The training-state checkpoint is 15,125,192,278 bytes and expires **2026-10-06 15:58:28 UTC**. Both were reported available, private, unexpired, based on `thinkingmachines/Inkling`, and under a run reported as uncorrupted. Two read-only provider requests were made; provider mutations, archive requests, inference requests, and training requests were zero.

The API metadata does not prove byte-level content identity, optimizer-state completeness, successful restore or inference, archive availability or contents, tokenizer/renderer identity, or external serving and re-import compatibility. The distinction between the two checkpoint kinds remains material: Tinker documents sampler checkpoints for inference and training-state checkpoints for resuming training, including an optimizer-aware restore path.

The installed SDK is Tinker 0.27.1. Its local public interfaces match the current documentation:

- `RestClient.set_checkpoint_ttl_from_tinker_path(path, None)` removes an existing expiry; the CLI equivalent is `tinker checkpoint set-ttl ... --remove`.
- `TrainingClient.load_state(...)` restores weights only, while `load_state_with_optimizer(...)` and `ServiceClient.create_training_client_from_state_with_optimizer(...)` restore optimizer state from a Tinker checkpoint path.
- `RestClient.get_checkpoint_archive_url_from_tinker_path(...)` supplies a signed archive URL, and `tinker checkpoint download` downloads and extracts the archive.
- `ServiceClient.copy_weights(path, ttl_seconds=None)` can retain either checkpoint kind under a new non-trainable run without duplicating storage bytes. This is an alternative migration operation, not needed when TTL removal works on the existing owned checkpoint.

## Recommended operation

Before the recorded expiry, remove the TTL from **both existing checkpoints**, then re-list them and write a separate private post-operation receipt recording only redacted identities, types, sizes, privacy, new expiry state, SDK version, time, and prior receipt hash. This is the smallest operation that preserves both current inference and provider-side training restoration while leaving the historical receipts unchanged. It is a provider mutation and remains unexecuted pending the applicable allowance.

After provider retention is secure, a local download of the sampler archive is a useful second copy. Hash the archive contents and record the base-model identifier plus tokenizer and renderer dependencies. Treat this as artifact preservation only. Downloading does not prove that B can be re-imported into Tinker or served elsewhere.

## Cost

Tinker's current price is **$0.10 per GB-month** for checkpoint storage. Using provider-reported bytes as decimal GB, the sampler is 5.042146156 GB and the training state is 15.125192278 GB, for **20.167338434 GB total**. Indefinite retention is therefore estimated at **$2.016734/month** or **$24.200806/year** at the current rate.

This is a concrete storage estimate, not a quoted fixed-term price; usage duration and future rates can change the amount. The reviewed official pricing and download pages do not state a separate archive-generation, download, or network-egress charge; that cost is **unverified**, not assumed to be zero. A local download also needs enough temporary disk for both the archive and extracted files at once.

## Inkling portability limits

Official generic deployment instructions say a downloaded LoRA adapter can be converted to PEFT or merged with a Hugging Face-compatible base model. They require a Hugging Face model name or local base-model directory. The current Inkling documentation identifies the hosted Tinker model and its required `tml-renderers` prompt/token handling, but it does not identify a downloadable Inkling base-model artifact or demonstrate an Inkling adapter exported, merged, re-imported, or served outside Tinker. Therefore:

- TTL removal preserves B on Tinker.
- A sampler archive may preserve adapter bytes.
- Neither step establishes independent Inkling serving.
- The documented restore APIs accept Tinker checkpoint paths; local-artifact re-import remains unverified.

## Official sources

- [Models and pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/)
- [Checkpoint CLI: TTL, listing, download, and PEFT push](https://tinker-docs.thinkingmachines.ai/tinker/cli/checkpoint/)
- [Weights and checkpoint lifecycle](https://tinker-docs.thinkingmachines.ai/tutorials/core-concepts/weights/)
- [ServiceClient restore API](https://tinker-docs.thinkingmachines.ai/tinker/api-reference/serviceclient/)
- [Hugging Face model export requirements](https://tinker-docs.thinkingmachines.ai/cookbook/api-reference/weights/build_hf_model/)
- [Inkling renderer requirements](https://tinker-docs.thinkingmachines.ai/cookbook/inkling/tml-renderers/)
