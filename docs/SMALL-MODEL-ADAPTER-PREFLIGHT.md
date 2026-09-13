# Small-model adapter portability preflight

September 13, 2026. Research and offline converter testing only. No training, Tinker checkpoint download, adapter export, GPU adapter load, provider call, deployment, or model change occurred.

The earlier Runpod training/export proposal is preserved in [adapter proposal v1](SMALL-MODEL-ADAPTER-PROPOSAL-V1.md). Its proposed budget is historical, not authorization for a new run. This update considers the subsequently tested Modal L4 path.

## Decision

The proposed `openai/gpt-oss-20b` path is credible enough for a **no-training compatibility artifact**, but it has not passed the project's adapter gate.

- Tinker lists the exact ID `openai/gpt-oss-20b` as a trainable 32K reasoning MoE model. The catalog defines a Tinker ID as the string accepted by `create_lora_training_client`; this verifies service support for the model ID. It does not identify the Hugging Face commit used behind the service. [Tinker model catalog](https://tinker-docs.thinkingmachines.ai/tinker/models/)
- Tinker Cookbook 0.4.1 has GPT-OSS-specific PEFT conversion code and a unit fixture built from `openai/gpt-oss-20b` configuration. The fixture checks Tinker's `.attn` to Hugging Face `.self_attn` rename and expansion of Tinker's shared expert factor into per-expert PEFT keys. This verifies source-level converter support for that architecture. It is a reduced, unquantized fixture, not an exported production checkpoint or a vLLM load. [Tinker GPT-OSS adapter test](https://github.com/thinking-machines-lab/tinker-cookbook/blob/v0.4.1/tests/weights/test_adapter_gpt_oss.py), [converter implementation](https://github.com/thinking-machines-lab/tinker-cookbook/blob/v0.4.1/tinker_cookbook/weights/_adapter.py)
- vLLM 0.29.0 marks `GptOssForCausalLM` as LoRA-capable and includes an exact-model test that loads `openai/gpt-oss-20b` with LoRA on its native MXFP4 path. The test covers rank 8, one GPU, 1,024 model tokens, standard and Marlin MXFP4 backends, and two adapter identities. This is direct upstream evidence for the base-runtime combination. It does not name L4 hardware, use the project's 8,192-token setting, or use a Tinker-exported adapter. [vLLM 0.29.0 GPT-OSS LoRA test](https://github.com/vllm-project/vllm/blob/v0.29.0/tests/lora/test_gptoss_tp.py), [test fixture source](https://github.com/vllm-project/vllm/blob/v0.29.0/tests/lora/conftest.py)
- The project has separately run the unchanged pinned base at revision `6cee5e81ee83917806bbde320786a8fb61efebee` with vLLM 0.29.0, native MXFP4, 8,192 tokens, and one L4. LoRA was disabled in that measurement. See [Modal serving results v1](MODAL-SERVING-RESULTS-V1.md). No result currently combines that exact revision, L4, 8K context, and an adapter.

The retained Inkling B adapter cannot be attached to GPT-OSS. A future GPT-OSS adapter would be a distinct experiment with a fresh evaluation and explicit authorization; [the affordable-model exploration](AFFORDABLE-MODEL-EXPLORATION.md) already records this boundary.

## Verified and unknown

| Question | Status | Evidence and consequence |
| --- | --- | --- |
| Does Tinker train the exact model ID? | **Verified for the ID** | The current catalog lists `openai/gpt-oss-20b` and a training rate. Tinker's backing weight revision is **unknown** because the public catalog gives no commit hash. |
| Does the current stable Tinker converter recognize GPT-OSS? | **Verified in source-level fixtures** | Cookbook 0.4.1 tests attention renaming and one shared-expert expansion against a reduced GPT-OSS configuration. Its generic export workflow emits `adapter_config.json` and `adapter_model.safetensors` for vLLM `--lora-modules`. [Tinker PEFT export tutorial](https://tinker-docs.thinkingmachines.ai/tutorials/deployment/lora-adapter/) |
| Has an actual Tinker GPT-OSS checkpoint been exported here? | **Unknown / not run** | No Tinker checkpoint was downloaded or converted. The tutorial demonstrates Qwen3.5-4B, so its success is not an execution receipt for GPT-OSS. |
| Does vLLM 0.29.0 load LoRA over native GPT-OSS MXFP4? | **Supported upstream; not reproduced here** | The tagged test exercises the exact model ID, native MXFP4 and rank 8. vLLM also documents that LoRA works for models implementing `SupportsLoRA`, which GPT-OSS does. [vLLM LoRA guide](https://docs.vllm.ai/en/v0.29.0/features/lora/), [GPT-OSS implementation](https://github.com/vllm-project/vllm/blob/v0.29.0/vllm/model_executor/models/gpt_oss.py) |
| Does a Tinker-exported adapter load in that path? | **Unknown** | Tinker's converter test ends at PEFT files. Its vLLM-serving fixture still says its serving step is skipped based on older vLLM 0.18 behavior. The newer vLLM 0.29.0 test uses a separate community PEFT fixture. [Tinker vLLM fixture](https://github.com/thinking-machines-lab/tinker-cookbook/blob/v0.4.1/tests/weights/vllm_serving/test_gpt_oss.py) |
| Does it fit and complete on the project's L4 settings? | **Unknown** | The base-only L4 result leaves headroom, but adapter tensors, wrappers and workspace change memory use. The upstream adapter test's GPU model and memory measurements are not specified. |
| Is output-head adaptation portable? | **Unknown** | Tinker exposes `train_unembed`, but the exact GPT-OSS converter fixture and vLLM runtime test do not demonstrate it. Keep it off in the first portability probe rather than silently losing it. |
| Is the exact tokenizer and Harmony rendering preserved? | **Unknown end to end** | GPT-OSS requires its Harmony format. A loader success alone cannot establish token or response parity. [OpenAI GPT-OSS model card](https://huggingface.co/openai/gpt-oss-20b) |

## Tinker export and local PEFT are different paths

### Tinker LoRA export

Tinker offers three coarse target switches: attention, MLP (including MoE), and unembedding. Its defaults are all enabled and rank 32, so relying on defaults would exceed the narrowest supported probe and would include an unverified output-head target. [Tinker `ServiceClient`](https://tinker-docs.thinkingmachines.ai/tinker/api-reference/serviceclient/), [Tinker `LoraConfig`](https://tinker-docs.thinkingmachines.ai/tinker/api-reference/types/loraconfig/)

For the first authorized compatibility export, request rank 8 with `train_attn=True`, `train_mlp=True`, and `train_unembed=False`. Rank 8 matches the exact vLLM GPT-OSS test and is one of vLLM 0.29.0's supported maximum-rank settings. Configure `--max-lora-rank 8`; vLLM warns that a needlessly high maximum wastes memory. [vLLM LoRA configuration](https://github.com/vllm-project/vllm/blob/v0.29.0/vllm/config/lora.py), [vLLM rank guidance](https://docs.vllm.ai/en/v0.29.0/features/lora/#configuring-max_lora_rank)

Tinker documents a shared-outer factor for MoE adapters. Cookbook 0.4.1's GPT-OSS converter test expands that pattern into per-expert PEFT keys. vLLM 0.29.0 distinguishes per-expert 2D adapters from fused 3D PEFT adapters and warns that declaring the wrong layout can load without an error yet produce meaningless output. Therefore the actual exported key shapes must decide the vLLM flags. Do not infer the layout from the `.safetensors` filename or enable shared-outer handling automatically. [Tinker LoRA parameter accounting](https://tinker-docs.thinkingmachines.ai/cookbook/api-reference/hyperparam_utils/get_lora_param_count/), [vLLM MoE LoRA layouts](https://docs.vllm.ai/en/v0.29.0/features/lora/#mixing-2d-and-3d-moe-lora-adapters)

If the real converter output matches its per-expert 2D fixture, the candidate launch uses `--enable-mixed-moe-lora-format` and declares `is_3d_lora_weight: false` for that static module. A fused 3D PEFT artifact uses the model-driven default instead. A still-shared artifact is a third layout covered by vLLM's separate `enable_moe_shared_loras` option. These are mutually testable hypotheses, not interchangeable switches. [vLLM LoRA configuration](https://docs.vllm.ai/en/v0.29.0/api/vllm/config/lora/)

The converter accepts a Hugging Face model ID or a local model path, but it has no documented revision argument. Use the project's revision-bound local base directory when converting, and record the canonical model ID and commit separately. The generated `base_model_name_or_path` is metadata, not proof that Tinker's hidden training base and the serving bytes are identical. [Tinker `build_lora_adapter`](https://tinker-docs.thinkingmachines.ai/cookbook/api-reference/weights/build_lora_adapter/)

### Locally trained PEFT

A local PEFT run would write the serving format directly and would not test Tinker's converter. It also needs an explicit GPT-OSS target definition. PEFT's `target_modules` selects supported modules by name, while MoE weights represented as raw `nn.Parameter` values require `target_parameters`; `all-linear` excludes the output layer. [PEFT `LoraConfig`](https://huggingface.co/docs/peft/main/package_reference/lora)

OpenAI's local GPT-OSS example uses `Mxfp4Config(dequantize=True)`, BF16 compute, eager attention, rank 8, `all-linear`, and explicit `gate_up_proj`/`down_proj` expert parameters in only three layers. That is useful shape and target guidance, but it is a demonstration rather than evidence that the project's full intended target set trains within one L4. [OpenAI local fine-tuning notebook](https://github.com/openai/openai-cookbook/blob/main/articles/gpt-oss/fine-tune-transfomers.ipynb)

The local route must prove that attention and both expert projections are actually trainable and present in the saved adapter. It must separately decide whether `lm_head` belongs in the hypothesis and runtime. A locally saved PEFT adapter is not evidence that Tinker's shared-expert representation converts, and a Tinker export is not evidence that a chosen local PEFT training stack updates the intended expert tensors. Serving can retain the pinned native-MXFP4 base even if local training temporarily dequantizes it; the saved adapter still needs its own exact vLLM load test.

## No-training compatibility artifact

### Completed offline converter fixture

The first mechanical check completed locally with the exact `tinker-cookbook==0.4.1` wheel (SHA-256 `1776e82470534e47d8923378ea41d4c7e47a1ffdfcb1982507dfd0289ba9a70b`). A deterministic rank-8 synthetic adapter used eight nonzero, distinct source tensors: one 2D attention pair and three 3D expert pairs. The converter renamed `.attn` to `.self_attn`, expanded three experts, mapped `w1`/`w2`/`w3` to `gate_proj`/`down_proj`/`up_proj`, and produced 20 tensors with the expected shapes and target-module metadata. All 20 output tensors exactly equaled their intended source slice, including both supported sharing directions: shared A with per-expert B, and per-expert A with shared B.

Three negative cases also failed closed: a 2D expert tensor raised `WeightsAdapterError`; expert counts of two versus three and two one-expert factors each raised `WeightsMergeError`. Failed conversions left no output directory. The ignored receipt, exact synthetic shapes, dependency versions, package and upstream-test hashes are under `runs/adapter-portability-v1/`.

This result verifies only the 0.4.1 converter's rename, expansion and value preservation on small CPU tensors. The base was a hand-built unquantized header fixture. It does not test a real Tinker checkpoint, hidden-base equality, all GPT-OSS layers or targets, MXFP4, PEFT/vLLM loading, inference, L4 memory, or output behavior. No checkpoint, GPU, provider, credential or training operation was used.

### Remaining checks

Conversion is local; the later loader probe needs an authorized GPU runtime:

1. Pin `tinker-cookbook==0.4.1`, PEFT/safetensors versions, vLLM `0.29.0`, the existing model revision, and the exact test script hash.
2. Separately consider the adapter referenced by vLLM 0.29.0's official GPT-OSS test as a **loader fixture**. Before downloading it, bind its repository revision, hashes and license; an upstream test reference is not a rights grant. Reproduce vLLM's base-versus-adapter deterministic assertions first at its 1,024-token setting. This tests vLLM, not Tinker portability.
3. Only after the loader fixture also passes should a separately authorized GPU probe combine the synthetic converted artifact with the pinned native-MXFP4 base. Start with one adapter, one sequence, 1,024 tokens, eager execution and rank 8; then repeat at the project's 8,192-token L4 setting. Require startup success, complete tensor loading, enforced adapter selection (including rejection of an unknown alias), correct adapter identity, final-only response handling, bounded memory, clean restart and teardown receipts.

These artifacts can establish converter and loader mechanics. They cannot establish equality between Tinker's hidden base revision and the pinned Hugging Face revision. The decisive end-to-end gate still requires a tiny, disposable Tinker checkpoint exported through the pinned converter and loaded on the exact serving stack. That later operation is training/export/provider work and remains unauthorized.

## Gate before substantial adaptation

A tiny, disposable training-and-export compatibility probe requires its own owner notice and cost ceiling. Before proposing substantial adaptation, record the following:

- the Tinker session reports the exact model ID, target switches, rank and tokenizer/renderer;
- the adapter export binds converter version, base ID, local serving revision, all file hashes, rank, alpha, target list, tensor keys, tensor shapes and expert layout;
- every requested attention/MLP target is present after conversion, with no ignored or silently dropped weights;
- vLLM loads all expected adapter tensors over the pinned native-MXFP4 base and enforces adapter selection; controlled output or log-probability differences provide corroboration, while identical text alone does not establish failure;
- the L4 run stays within the measured memory and deadline envelope at 8K, survives restart, and keeps reasoning private while returning only final text;
- output-head adaptation is either independently proven or explicitly excluded from the proposed training hypothesis;
- the final original-language training method, fresh evaluation and cost ceiling receive owner approval.

Until then, report adapter portability as **promising upstream support with an unverified Tinker-to-vLLM boundary**, not as a runtime pass.
