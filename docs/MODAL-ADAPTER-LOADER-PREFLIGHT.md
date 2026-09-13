# Modal adapter loader preflight

September 13, 2026. Primary-source review and test design only. No adapter weights were downloaded, no GPU or provider was called, and no training, export, deployment, or model change occurred.

## Decision

Do **not** execute vLLM's referenced GPT-OSS adapter fixture in the project. The fixture is technically well matched to a narrow loader check, but its reuse rights and exact training-base revision are unresolved. The Hugging Face repository has no model card, declared license, or license file. Its `adapter_config.json` names `openai/gpt-oss-20b` but sets `revision` to `null`. A public repository and an upstream test reference are not a license grant.

Use the new project-owned synthetic adapter for the first live loader probe instead. It removes the third-party-rights dependency and binds the serving base to the project's revision. It tests loader mechanics and a representative GPT-OSS attention/MoE layout; it does not inherit the community fixture's SQL assertions or establish Tinker transport.

## Project-owned loader fixture

[`tools/build_gptoss_loader_fixture.py`](../tools/build_gptoss_loader_fixture.py) deterministically creates a rank-8 PEFT adapter beneath ignored `runs/`, using only project-authored arithmetic values. It performs no training, model-weight download, provider call, or GPU operation. The generator uses the already preserved `tinker-cookbook==0.4.1` converter and wheel hash, a tiny state-name header, and the exact logical dimensions from the pinned `openai/gpt-oss-20b` configuration at revision `6cee5e81ee83917806bbde320786a8fb61efebee`:

- layer 0 `q_proj`: A `[8, 2880]`, B `[4096, 8]`;
- layer 0 `down_proj`: 32 expert pairs, each A `[8, 2880]`, B `[2880, 8]`;
- alpha 16, with every output tensor containing nonzero BF16 values of magnitude below `0.001`.

The converter changes `.attn.q_proj` to `.self_attn.q_proj` and expands Tinker's 3D expert tensors into 32 independent 2D PEFT pairs. The generator then asserts the complete 66-key set, every shape, exact source-to-output value equality, rank, alpha, target list, and nonzero content before writing `manifest.json`. It replaces the converter's temporary local base path with the immutable model ID and revision in the final adapter configuration.

The hardened local build used Python 3.13.1, PyTorch 2.8.0 and safetensors 0.6.2. Before import, the generator verified the converter wheel against SHA-256 `1776e82470534e47d8923378ea41d4c7e47a1ffdfcb1982507dfd0289ba9a70b`, extracted that verified wheel into a temporary directory, and imported the converter from that extraction. It refuses optimized Python execution so its integrity assertions cannot be disabled. The build produced:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `adapter_config.json` | 469 | `606b0b3f906d4ad1217de5725e671717e29815d5284d88a00fe734bfd25b6291` |
| `adapter_model.safetensors` | 3,069,904 | `fe03f9c6880180460f57a335ea7fe80b96363a5448dfc1f19fe04cc6aa9deaf8` |

These hashes bind the generated artifact under `runs/gptoss-loader-fixture-v1/`; the public script, dimensions, construction rule, and assertions make it reproducible without publishing the ignored binary. A live loader must verify these hashes before GPU startup.

This fixture should replace, rather than follow, the community SQL fixture in the smallest live test. Since synthetic low-magnitude tensors have no expected natural-language answer, the live pass condition centers on successful complete loader accounting. Token log probabilities from a fixed constructed prompt may corroborate an effect, but the BF16/MXFP4 path may round this deliberately small perturbation below observable precision. A zero measured delta is inconclusive and does not prove that weights were dropped. Text inequality is neither required nor sufficient.

The narrower upstream result remains useful context: vLLM 0.29.0 has an Apache-2.0 test that loads its rank-8 attention-and-MoE fixture over `openai/gpt-oss-20b` on native MXFP4 and checks exact greedy SQL prefixes. The project should not download, cache, redistribute, or build a paid Modal run around those community weights until the author supplies a compatible license.

## Exact upstream fixture

The vLLM tag `v0.29.0` resolves to commit `98dff2a81d747d1dba01a47f939f48c3526d4206`. Both relevant source files carry SPDX `Apache-2.0` notices under the repository's Apache-2.0 license.

| Artifact | Immutable identity | SHA-256 or content identity |
| --- | --- | --- |
| vLLM GPT-OSS test | [`tests/lora/test_gptoss_tp.py` at `98dff2a`](https://github.com/vllm-project/vllm/blob/98dff2a81d747d1dba01a47f939f48c3526d4206/tests/lora/test_gptoss_tp.py) | `7611f5cfff4d38ade45bd8f07c1cf9f02674739a30ce05483c4c9580e566c3aa` |
| vLLM LoRA fixtures | [`tests/lora/conftest.py` at `98dff2a`](https://github.com/vllm-project/vllm/blob/98dff2a81d747d1dba01a47f939f48c3526d4206/tests/lora/conftest.py) | `f59bae7a74ea0e698e3def55c0302e61e3084f12a4d2cd6a5c076723047ab277` |
| Community adapter repository | [`jeeejeee/gpt-oss-20b-lora-adapter-text2sql` at `350316a`](https://huggingface.co/jeeejeee/gpt-oss-20b-lora-adapter-text2sql/tree/350316a431685d3c5efd01df389c98e0d9d70aa7) | repository commit `350316a431685d3c5efd01df389c98e0d9d70aa7` |
| Adapter configuration | [`adapter_config.json` at `350316a`](https://huggingface.co/jeeejeee/gpt-oss-20b-lora-adapter-text2sql/blob/350316a431685d3c5efd01df389c98e0d9d70aa7/adapter_config.json) | SHA-256 `33eac498f4d8574ed0e98791a3d6ebd3c3fe834fb0c630e21394d66d6a3e2e04`; Git blob `0cf3bc8f00ae40d8d6abaabe07622e7d70b37957` |
| Adapter tensors | `adapter_model.safetensors` at the same repository commit | 182,263,768 bytes; LFS SHA-256 `4ec07655976e7d36fcde100516ff64550d6e0d47a028ba75d8d9e5bd7ea3d696` |

The repository contains only `.gitattributes`, `adapter_config.json`, and `adapter_model.safetensors`. The current commit was created October 31, 2025 after an initial commit about one minute earlier. The absence of explanatory and licensing files is therefore not a model-card rendering problem.

The adapter declares PEFT LoRA rank 8, alpha 32, no bias, no modules-to-save, attention targets `q_proj`, `k_proj`, and `v_proj`, and raw MoE target parameters `mlp.experts.gate_up_proj` and `mlp.experts.down_proj`. This is useful coverage for the project's intended attention-plus-MLP boundary. It omits `o_proj` and the output head and cannot validate either one.

## What the official test actually asserts

The single-GPU test constructs `vllm.LLM` with model ID `openai/gpt-oss-20b`, `max_model_len=1024`, LoRA enabled, maximum rank 8, up to four loaded adapters, two sequences, 2,048 batched tokens, and CUDA graph LoRA specialization disabled to avoid out-of-memory failure. It runs both automatic and Marlin MoE/linear backends and both values of `specialize_active_lora`. The project-relevant branch is Marlin on one GPU.

For one adapter path, the test sends three fixed Harmony-formatted text-to-SQL prompts at temperature 0 with at most 64 generated tokens. It invokes the same path twice under numeric LoRA IDs 1 and 2. After stripping output, it accepts either an exact expected prefix or the same prefix after normalizing whitespace and comma spacing:

1. `SELECT avg(Working_Horses) FROM farm WHERE Total_Horses > 5000`
2. `SELECT max(Cows) , min(Cows) FROM farm`
3. the same maximum/minimum query for a paraphrased prompt

The test does **not** generate a base-model control, compare logits, verify an unknown adapter alias is rejected, bind the base repository to a commit, inspect every loaded tensor, report GPU memory, test restart, test 8,192 tokens, or prove that LoRA IDs 1 and 2 contain different weights. The two IDs deliberately point to the same adapter path. Calling this a base-versus-adapter assertion would overstate the source.

On ROCm only, the test also enables vLLM's batch-invariant mode and spawned workers because split-K atomic accumulation can perturb exact greedy output. That setting is not part of the CUDA path, but recording platform and backend is necessary when interpreting an exact-string failure.

## Smallest live design with the project fixture

Use the existing immutable vLLM 0.29.0 image and prepare the project's pinned base revision `6cee5e81ee83917806bbde320786a8fb61efebee` in a new temporary or separately named volume; the prior serving volume was deleted. Create a separate, ephemeral Modal entry point; do not change the serving v3 tool or enable snapshots. Stage only the generated adapter files, verify both SHA-256 values before GPU startup, and reject any unexpected file. Use one L4, eager mode, native `gpt_oss_mxfp4`, Marlin, one sequence, `max_model_len=1024`, `max_lora_rank=8`, and one loaded adapter.

The first and smallest execution is one engine boot and one fixed constructed prompt, generated once without the adapter and once with it under greedy sampling. Require a successful complete load with no ignored keys; record token log probabilities for a possible delta without making a nonzero delta mandatory. In the same boot, require an unknown adapter identity to fail and bind the successful alias to the verified adapter directory and hashes. Capture engine version, base revision and manifest, adapter config and tensor hashes, GPU class, load errors and warnings, peak memory if available, and final-only outputs.

Only if that 1,024-token run passes and retains enough measured memory should the same artifact receive a second boot at the project's 8,192-token setting. Re-run the constructed prompt, then restart once and repeat it to test clean reload. Stop on an out-of-memory error, missing or ignored tensor, hash mismatch, adapter-load failure, identity failure, or deadline. Do not silently alter quantization, adapter layout flags, model revision, rank, context, engine version, or GPU.

This design is intentionally a loader test. Its constructed output is not quality evidence. An adapter/base log-probability difference would be useful corroboration, but only loader accounting can establish that no adapter key was ignored; even that does not prove a useful numerical effect.

## Pass criteria and limits

The compatibility fixture passes only if all of the following hold:

- both project-generated adapter file hashes match the recorded manifest;
- vLLM 0.29.0 loads the pinned base and all adapter tensors on one L4 with rank capped at 8 and no ignored, unexpected, or shape-mismatched keys;
- a fixed base/adapter probe records token log probabilities and clearly labels either a repeatable delta or an inconclusive below-precision result;
- an unknown adapter identity fails closed and the successful receipt identifies the verified adapter;
- measured memory permits the second stage, and the 8,192-token boot plus one clean restart complete without configuration drift;
- outputs expose only final content and teardown leaves no live test GPU or public endpoint.

A pass establishes only that this project-created PEFT layout loads on the project's vLLM/Modal base stack. Although the pinned converter produced the fixture, it is constructed data rather than a provider checkpoint: a pass does not establish a real Tinker export path, equality with Tinker's hidden training base, output-head support, Bible quality, production readiness, or authorization to train.

## Unresolved rights and provenance

The vLLM source is reusable under Apache-2.0, and the OpenAI base model separately carries Apache-2.0 terms. Those licenses do not automatically cover a third party's adapter weights. The adapter repository exposes no license metadata or license text, so the adapter's copying and execution terms are unclear. Ask its author to add an explicit license and state the exact `openai/gpt-oss-20b` training revision, training stack, data rights, and whether the published tensor hash is the artifact used to obtain the asserted outputs.

If that information is not supplied, replace the fixture. A suitable replacement must have an explicit compatible license, immutable repository revision and tensor hashes, a pinned GPT-OSS base revision, rank no greater than 8, declared attention and MoE expert targets, and deterministic prompts with expected outputs or logits. A project-created synthetic PEFT adapter can establish loader mechanics without external weight rights, but it must include nonzero tensors with a controlled measurable effect; the completed CPU converter fixture alone is not loadable proof over the real quantized model.
