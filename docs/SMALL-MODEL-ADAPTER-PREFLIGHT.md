# Small-model adapter portability preflight

Prepared September 13, 2026 on `codex/hosting-first-small-model`. **Proposal only:** no data has been selected or reviewed for this test, no training or export has run, and no provider resource or production setting has changed. Retained Inkling B remains the Bible model.

## Decision this test would support

The narrow question is whether a Tinker-trained, rank-8 `openai/gpt-oss-20b` LoRA can be exported as a private PEFT adapter and applied, without dropping trained tensors, to the pinned native-MXFP4 base on the already qualified Runpod A5000 configuration. It is not a model-quality experiment and cannot justify replacing B or starting a full small-model adaptation.

The smallest useful test is one optimizer update over a small batch of existing original-language **TRAIN-split** windows, followed by export and two matched serving pairs: four successful requests covering two prompts, each sent once to the unchanged base and once explicitly to the adapter alias. The test passes only when artifact, runtime and response evidence establish that the adapter was loaded and selected. An output difference alone is not identity evidence, and equal text alone does not prove the adapter was ignored.

## What current documentation establishes

- Tinker's current catalog lists `openai/gpt-oss-20b` as a 32K reasoning model available to `create_lora_training_client`, at **$0.396 per million training tokens**. Tinker's `LoraConfig` can select attention, MLP (including MoE) and unembedding LoRA components. [Models and pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/), [LoRA configuration](https://tinker-docs.thinkingmachines.ai/tinker/api-reference/types/loraconfig/)
- Tinker's current export tutorial downloads a sampler checkpoint and converts it with `weights.build_lora_adapter(...)` into PEFT `adapter_config.json` plus `adapter_model.safetensors`; it identifies this as the lightweight vLLM/SGLang path. The cookbook's model matrix specifically lists GPT-OSS 20B/120B adapter conversion and the `.attn` to `.self_attn` remap. [PEFT export tutorial](https://tinker-docs.thinkingmachines.ai/tutorials/deployment/lora-adapter/), [GPT-OSS export matrix](https://github.com/thinking-machines-lab/tinker-cookbook/blob/485726f55d3b2b5abe5fcb4a0d2f3e18e4599dfe/tinker_cookbook/weights/README.md)
- That cookbook matrix still says its vLLM 0.18 serving test was blocked by MXFP4 plus LoRA. Newer vLLM **0.29.0** has a GPT-OSS-20B LoRA test covering rank 8, native MXFP4, attention adapters, expert MLP adapters and a Marlin path at 1,024 context. This resolves an older engine-level blocker but does not test a Tinker-exported adapter, an A5000, this project's 8K setting or its exact tensor set. [Pinned vLLM test](https://github.com/vllm-project/vllm/blob/v0.29.0/tests/lora/test_gptoss_tp.py)
- Runpod worker **v2.27.0** pins vLLM 0.29.0. Its configuration accepts `ENABLE_LORA`, `MAX_LORAS`, `MAX_LORA_RANK` and JSON `LORA_MODULES`, passing the latter to vLLM's `--lora-modules`. vLLM lists loaded adapter aliases alongside the base at `/v1/models`, and requests select the adapter through the `model` field. [Pinned worker Dockerfile](https://github.com/runpod-workers/worker-vllm/blob/v2.27.0/Dockerfile), [pinned worker LoRA configuration](https://github.com/runpod-workers/worker-vllm/blob/v2.27.0/docs/configuration.md#lora), [vLLM LoRA serving](https://github.com/vllm-project/vllm/blob/v0.29.0/docs/features/lora.md#serving-lora-adapters)

These are compatible pieces, not an end-to-end result. The project's live base tests establish that pinned native MXFP4 loads and answers on one A5000 at 8,192 context with eager mode; they did not load an adapter. See [A5000 result](SMALL-MODEL-SERVING-RESULTS-V2.md).

## Proposed frozen test

### 1. Select and bind the input before any training notice

After a separate review, select at most **eight complete windows** from `data/prepared/v1/train.jsonl`, no more than **16,384 input positions** after retokenization. Require both selected editions and at least one Hebrew or Aramaic window and one Greek window. Every row must retain its original source, passage, language, layer and `split: train` metadata and must bind to the pinned OSHB/WLC or SBLGNT source bytes and notices. Do not draw from `validation.jsonl`, `all.jsonl`, English instruction data, historical-evidence drafts or user conversations.

The existing file was tokenized for gpt-oss-120b. Before freezing this test, retokenize the selected unchanged header/text with the pinned gpt-oss-20b tokenizer, compare the tokenizer vocabulary/special-token identity rather than assuming parity from the shared model family, and rebuild the shifted next-token targets and metadata mask. Record selected row IDs, source hashes, exact Unicode hashes, token IDs, target counts and order in a new private run manifest. **No rows have yet been chosen or reviewed for this proposed test.**

### 2. Make one disposable adapter update

Use exact Tinker ID `openai/gpt-oss-20b`, rank 8, a recorded initialization seed, one forward/backward operation and one optimizer step. Enable attention and MLP LoRA so the test covers the dense attention and MoE expert paths exercised by the pinned vLLM test. Set `train_unembed=false` for this first portability proof: the pinned vLLM test does not establish Tinker unembedding export/load compatibility. This choice limits the result; any later recipe that trains the unembedding layer needs another compatibility test.

Use summed cross-entropy with the existing header mask and a conservative fixed learning rate declared in the pre-training notice. Learning rate is a mechanics setting here, not a tuned Bible recipe. Save one sampler checkpoint only after the update completes with a known receipt. Stop on an uncertain update; do not retry it independently or extend to another step.

### 3. Export and reject dropped tensors locally

Download that exact sampler checkpoint privately and run the pinned `tinker-cookbook` `weights.build_lora_adapter(base_model="openai/gpt-oss-20b", ...)`. Keep the Tinker locator and any credentials out of public files. Record the cookbook commit, package lock and SHA-256/size of the downloaded archive, `adapter_config.json` and `adapter_model.safetensors` in the ignored run directory.

Before serving, require all of the following:

- PEFT configuration identifies `openai/gpt-oss-20b`, rank 8, no `modules_to_save`, the expected attention targets and expected expert target parameters.
- Every nonzero trained Tinker LoRA parameter has exhaustive coverage in the PEFT artifact through either a direct mapping or a documented lossless split/fusion transformation with compatible shapes; no unexpected, missing, duplicate or silently ignored parameter is allowed. Check the GPT-OSS attention-name and interleaved-expert transformations explicitly.
- At least one post-update B matrix is nonzero, and the final PEFT tensor inventory and hashes differ from a zero-initialized adapter. This establishes that a real update was exported, not that it improved the model.

If the converter rejects the tensors, includes an unsupported unembedding/output-head component, or cannot account for every trained key, stop. Do not merge to BF16 as a repair because that changes the 24 GB serving premise.

### 4. Place the private artifact by exact bytes

Use an access-controlled, immutable artifact location visible to the worker, with the adapter version resolved to the recorded SHA-256 before vLLM starts. A private, digest-pinned image or read-only mounted snapshot is preferable for this test. A moving Hugging Face branch name is insufficient because `LORA_MODULES` has no separate revision field. Do not publish the adapter or enable vLLM's runtime remote-adapter updater.

This transfer mechanism is not chosen yet. If the existing Runpod model cache cannot attach an arbitrary private adapter, choose and review a private repository, private image or mounted-volume path before provisioning. Stop if exact-byte placement would require an unreviewed public upload.

### 5. Load on the qualified serving stack

Retain the v2 base settings unless the independent cache result justifies a documented change:

```text
image: runpod/worker-v1-vllm:v2.27.0 at the previously recorded amd64 digest
MODEL_NAME=openai/gpt-oss-20b
MODEL_REVISION=6cee5e81ee83917806bbde320786a8fb61efebee
TOKENIZER_NAME=openai/gpt-oss-20b
TOKENIZER_REVISION=6cee5e81ee83917806bbde320786a8fb61efebee
MAX_MODEL_LEN=8192
GPU_MEMORY_UTILIZATION=0.85
MAX_NUM_SEQS=1
ENFORCE_EAGER=true
ENABLE_LOG_REQUESTS=false
ENABLE_LORA=true
MAX_LORAS=1
MAX_LORA_RANK=8
LORA_MODULES=[{"name":"bible-portability-r8-<artifact-hash-prefix>","path":"<immutable-private-local-path>","base_model_name":"openai/gpt-oss-20b"}]
```

Use one explicit A5000, zero Active workers, maximum one Flex worker and the existing teardown timer. Startup must report vLLM 0.29.0, native MXFP4, the pinned base revision, exact adapter path/hash, and successful LoRA load. Stop on OOM, key mismatch or fallback. Do not reduce the target tensor set, change the base to BF16, use another GPU automatically or raise worker count.

### 6. Prove selection and compare responses

After warm startup:

1. Query `/v1/models`; require both the base ID and the hash-named adapter alias, with the adapter parent tied to the base.
2. Submit an unknown adapter alias and require a clear failure. This checks that model selection is enforced rather than ignored.
3. Submit one short constructed English engineering prompt and one continuation prompt derived from a selected TRAIN excerpt, once to the base ID and once to the adapter alias. Use identical rendered tokens, temperature 0, seed, limits and final-answer extraction. Do not use a held-out evaluation question.
4. Require every request to finish successfully and each adapter response to report the adapter alias. Record request/response model IDs, input/output token hashes, finish reason, timing and exact equality or difference. If supported by the pinned request path, compare next-token log probabilities as a sensitive behavior check.

The gate requires artifact hashes, a complete tensor mapping, a positive load record, the models listing, alias-specific responses and the negative-control failure. A base/adapter token or log-probability difference is useful corroboration. These two prompts are exposed mechanics probes; their wording, fluency, latency and agreement do not measure biblical accuracy, retention or improvement.

## Proposed cost and stop rules

Proposed **$5 total incremental ceiling**, subject to a new exact pre-training notice and owner authorization:

| Reservation | Ceiling basis |
|---|---:|
| Tinker training, checkpoint, export and minimal native verification | $1.00; at most 16,384 training tokens cost about $0.0065 at the listed $0.396/M rate before sampling, storage or any provider minimum |
| Runpod A5000 adapter startup and matched probes | $3.00; hard stop at two cumulative worker hours, $1.38 at the previously observed $0.69/hour, leaving room for startup, idle and delayed metering |
| Private artifact/storage contingency | $1.00 |

The ceiling is a local guard, not a provider-enforced cap or invoice estimate. Recheck prices and reconcile the unresolved earlier Runpod billing before execution. Reserve the full amount before the first paid operation; stop at $3 observed or conservatively reserved spend, after two billed worker hours, on any uncertain provider result, or when acceptance is decided. Save only the one necessary Tinker sampling checkpoint, download it promptly, delete disposable Runpod resources, verify zero running spend and separately decide checkpoint retention.

## Pass, fail and remaining blockers

Pass means the exact nonzero Tinker-derived PEFT bytes load beside the pinned native-MXFP4 base on the explicit A5000, every trained tensor is accounted for, alias selection is enforced, and both base and adapter return complete matched responses. It establishes only a private adapter transport and execution path.

Fail or stop if any trained tensor is dropped; the adapter needs BF16 merging; the A5000 cannot load base plus adapter at 8K; the worker cannot access a privately pinned artifact; identity evidence is incomplete; billing or teardown is uncertain; or the Tinker operation outcome is uncertain. Preserve the failure rather than broadening the test.

Open blockers before execution are:

- Tinker exposes the model ID but not a provider base-weight commit in the cited interface. The Runpod base is pinned to a public commit, so exact training-base equality remains unverified even if the adapter loads.
- The Tinker exporter documents GPT-OSS conversion, while its older vLLM 0.18 compatibility note still records MXFP4 serving as blocked. The vLLM 0.29.0 test is newer engine evidence, not an end-to-end Tinker export result.
- The private immutable adapter transfer path and its startup hash check have not been selected or exercised.
- The pinned engine test uses 1,024 context and a public attention/expert adapter. A5000 memory with this exported tensor inventory at 8,192 context is unmeasured.
- Unembedding adaptation is deliberately excluded from this smallest test. A future recipe cannot add it and cite this result as coverage.
- No prospective quality dataset or evaluation is frozen for gpt-oss-20b. If portability passes, the next decision is whether to prepare such an evaluation and a separately reviewed full-training proposal; no training continuation, promotion, deployment or publication follows automatically.
