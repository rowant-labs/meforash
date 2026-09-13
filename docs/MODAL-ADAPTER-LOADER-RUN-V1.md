# Modal synthetic adapter loader run v1

September 13, 2026. Owner accepted continuing the isolated exploration. This is one bounded, no-training GPU compatibility test; production remains on retained Inkling B.

## Scope and prospective acceptance

Use the project-created layer-0 rank-8 adapter from [loader preflight](MODAL-ADAPTER-LOADER-PREFLIGHT.md), with the recorded configuration and tensor SHA-256 values. One L4, two physical CPU cores, 32 GiB host memory, one sequence, native MXFP4/Marlin, vLLM 0.29.0, the previously pinned gpt-oss-20b revision, snapshot disabled and 1,024-token context. Base preparation restores the deleted temporary volume using pinned source bytes. Stage only reviewed serving source and the two synthetic adapter files; never the repository or environment file.

Collect one base and one adapter response to a constructed engineering prompt, model/adapter identity, the unknown-alias rejection, tensor load accounting where supported, memory and timing. Outputs contain final text only. A successful answer or alias alone does not prove complete adapter application. Missing/ignored keys, unsupported configuration or incomplete tensor accounting remain failures or unresolved evidence, not a silent pass. Low-magnitude BF16 changes may leave text or log probabilities unchanged. No Bible quality conclusion follows.

Stop after this short-context result. A later 8K/restart check requires reviewing this receipt; do not automatically broaden the test, change hardware, omit expert tensors or train to fix a failure. No community adapter is downloaded.

## Budget and resource limits

New incremental ceiling: **$5**, declared before paid execution. This is a local ceiling, not a provider-enforced account cap. Account preflight found no apps or active containers. Metered account total before the test was $1.40, covered by credits; final billing can lag and earlier reservations remain separate.

One maximum GPU worker, zero minimum workers, no automatic retries. Limit the whole pilot to 45 minutes with an independent local watchdog; leave three minutes for teardown in the orchestration deadline. Client calls stop after 1,080 seconds with cancellation on uncertain timeout. Startup and function limits remain 900 and 600 seconds respectively. CPU preparation has no GPU. At the previously checked resource rates this leaves substantial room under the ceiling; stop on unexpected additional resources or uncertain cleanup. Never count credits as permission for unlimited work.

Persist private call receipts and logs under ignored `runs/modal-adapter-loader-v1/`. Finally stop the app, verify zero pilot containers, delete the temporary volume, and capture billing. No public endpoint or weights publication is part of the run.

## Frozen implementation and offline verification

The deployed source is `tools/modal_adapter_loader_pilot_v1.py`. The private budget receipt binds its SHA-256 before deployment. Independent review checked fixture delivery, model manifest compatibility, identity checks, final-only responses, bounded resources and verified teardown. Four reproducible offline receipt/schema tests pass. The wrapper deliberately returns `loaded_unverified` when it can establish working responses but not positive runtime accounting for every tensor; this is not a full compatibility pass.

## Completed result: startup compatibility failure

CPU preparation completed in **157.278 seconds**, verifying the pinned base manifest and the synthetic adapter. The requested L4 engine never became ready. Provider logs bind two failed initializer containers to the same assertion in vLLM's LoRA Triton shrink path: `lora_shrink_op.py`, `_lora_shrink`, `assert inputs.is_contiguous()`.

The call stack goes through `determine_available_memory`, `profile_run`, `_dummy_run`, the model forward path and the LoRA linear wrapper. Thus the observed failure is in startup profiling, before the base/adapter HTTP probes execute. It is not an answer-quality failure, an observed out-of-memory error, or proof that the synthetic tensor values are invalid. No base or adapter answer, alias control result or complete runtime tensor accounting was collected. The 8K and restart stages did not run.

Although the function's request retry setting was zero, Modal replaced failed initializer containers while the pending call waited. Two initializer failures are captured; a subsequent pending container was observed before the operator stopped the app. This distinction matters: zero request retries did not prevent lifecycle replacement. The original narrow one-boot intention was not achieved; preserve the repeated failure evidence rather than describing this as exactly one engine start. No client generation call was resubmitted and no configuration was changed during the run.

The operator stopped the app as soon as repeated startup failure was identified in the logs. The caller returned a remote error and the cleanup routine verified the app stopped with zero tasks, zero pilot containers and no remaining Volume. Account metering increased from **$1.40 to $1.53**, an observed **$0.13** increment covered by credits. This is provisional account metering, not a final invoice; retain the $5 reservation until reconciliation. No paid resources remain active.

## Implications

Do not train or migrate on the assumption that the smaller adapted model now serves. The unchanged base worked in prior tests; this exact adapter-enabled startup configuration failed. Next inspect the pinned engine's profiling/layout path and review a narrowly scoped fix or configuration change before another paid attempt. Add early lifecycle-failure detection or move risky engine initialization into a no-retry method in the next version so failed `enter` hooks cannot keep replacing containers unnoticed. Preserve this module and all private receipts as v1.

### Source-level diagnosis and candidate retry

The pinned engine passes a flattened activation view from `PunicaWrapperGPU.add_shrink` into a kernel that asserts contiguity. The recorded stack reaches this through GPT-OSS attention `qkv_proj` in the dummy profiling forward. This identifies the immediate activation-layout contract failure, not its full upstream cause or a bad adapter value. Sources: [pinned Punica wrapper](https://github.com/vllm-project/vllm/blob/98dff2a81d747d1dba01a47f939f48c3526d4206/vllm/lora/punica_wrapper/punica_gpu.py), [pinned shrink kernel](https://github.com/vllm-project/vllm/blob/98dff2a81d747d1dba01a47f939f48c3526d4206/vllm/lora/ops/triton_ops/lora_shrink_op.py).

The smallest candidate configuration retry removes `--enforce-eager` while retaining disabled LoRA CUDA-graph specialization. The [pinned upstream GPT-OSS adapter test](https://github.com/vllm-project/vllm/blob/98dff2a81d747d1dba01a47f939f48c3526d4206/tests/lora/test_gptoss_tp.py) uses default compilation with that specialization disabled. This is a hypothesis, not a confirmed workaround: no exact upstream issue establishing this assertion/configuration pairing was identified. Compilation may change startup time and memory use. Do not patch the kernel, change GPU, retrain, or remove adapter targets as an automatic repair. A future version must separately bind its configuration and stop behavior before execution.
