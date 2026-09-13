# gpt-oss cache startup diagnosis

Research checked September 13, 2026 on `codex/hosting-first-small-model`. This note interprets public documentation and the preserved v3 receipts. It was prepared during v4; the completed measurement is recorded separately in [v4 results](SMALL-MODEL-SERVING-RESULTS-V4.md).

## Findings

The v3 cache reference used the syntax documented by runpodctl v2.14.0:

```text
--model-reference https://huggingface.co/openai/gpt-oss-20b:6cee5e81ee83917806bbde320786a8fb61efebee
```

The created endpoint echoed that exact reference, and `runpodctl serverless model-status` resolved the same revision hash. This verifies the requested reference and control-plane resolution. It does not prove that the files were completely downloaded, mounted or consumed by vLLM. [Pinned create command reference](https://github.com/runpod/runpodctl/blob/v2.14.0/docs/runpodctl_serverless_create.md), [pinned model-status reference](https://github.com/runpod/runpodctl/blob/v2.14.0/docs/runpodctl_serverless_model-status.md)

Runpod documents its Hugging Face cache at `/runpod-volume/huggingface-cache/hub/`. The pinned worker-vLLM v2.27.0 image sets `HUGGINGFACE_HUB_CACHE` to that directory and passes `MODEL_NAME` plus `MODEL_REVISION` to `vllm serve`; it has no separate cached-model discovery routine. The platform mount and Hugging Face's ordinary cache lookup are therefore expected to meet at the documented path. No path mismatch is visible in the configuration. [Runpod cached-model paths](https://docs.runpod.io/serverless/endpoints/model-caching), [pinned worker Dockerfile](https://github.com/runpod-workers/worker-vllm/blob/v2.27.0/Dockerfile), [pinned worker entry point](https://github.com/runpod-workers/worker-vllm/blob/v2.27.0/src/main.py)

The pinned Hugging Face revision contains three large weight representations:

| Files | Logical bytes |
|---|---:|
| Root `model-00000-of-00002.safetensors`, `model-00001-of-00002.safetensors`, `model-00002-of-00002.safetensors` | 13,761,316,904 |
| `original/model.safetensors` | 13,761,300,984 |
| `metal/model.bin` | 13,750,886,400 |
| Tokenizer, configuration and other small files | 27,961,228 |
| **Repository total** | **41,301,465,516** |

These are Hugging Face metadata sizes at the pinned revision: **logical repository bytes, not measured network transfer or disk allocation**. Chunk deduplication, compression, partial reuse and the platform's implementation are not exposed, so the actual downloaded bytes cannot be inferred. OpenAI identifies the root checkpoint as the vLLM input, the `original/` checkpoint as the Torch/Triton reference input and `metal/model.bin` as the Apple Metal input. Only the root 13.76 GB weight set is needed by this vLLM configuration. [OpenAI implementation and weight-layout notes](https://github.com/openai/gpt-oss#download-the-model), [pinned Hugging Face tree](https://huggingface.co/openai/gpt-oss-20b/tree/6cee5e81ee83917806bbde320786a8fb61efebee)

Runpod states that when one repository contains multiple quantization versions it currently downloads all versions; its model-reference interface exposes no include/exclude pattern. The gpt-oss repository's multiple full weight representations therefore make approximately 41.3 GB the conservative logical-size assumption for cache preparation. This is an inference from the repository tree and Runpod's stated limitation, not a receipt for transferred bytes. [Runpod cache limitation](https://docs.runpod.io/serverless/endpoints/model-caching#current-limitations)

## Status interpretation

Runpod defines an `INITIALIZING` worker as downloading the image, loading code or downloading cached models, and lists that state as unbilled. Its model-status command separately returns the resolved version, machine assignment status, failure fields and mount path. The command explicitly does **not** expose download or mount progress or the container's effective model environment. `FAILED` may carry `download_failed`, `mount_failed`, `startup_failed` or `cuda_failed`. [Worker states](https://docs.runpod.io/serverless/workers/overview#worker-states), [model-status limits](https://github.com/runpod/runpodctl/blob/v2.14.0/docs/runpodctl_serverless_model-status.md)

In v3, the worker remained `INITIALIZING`; model status was `ASSIGNED`, its mount path was null, and no engine startup log appeared before the approximately five-minute stop. There was no reported failure. Given the repository size and absence of progress telemetry, v3 is an inconclusive bounded cache-preparation attempt rather than evidence of a broken revision, successful cache hit or worker path mismatch.

At this note’s v4 research cutoff, `DEPLOYED` with a non-null `/runpod/model-store/...` path is stronger evidence that the platform assigned and reported a mounted model version. The worker was still `INITIALIZING` and no container or vLLM engine log had appeared. **Neither `DEPLOYED` nor a non-null mount path alone proves that worker-vLLM consumed the cache or loaded the pinned model.** Subsequent successful execution and the 90-second idle limitation are recorded in the result document.

## Evidence needed for a cache result

A successful cache-use finding requires the exact resolved revision and non-null mount evidence together with container logs showing vLLM 0.29.0 starting from the pinned model, native MXFP4 loading, engine readiness and a complete response. Startup timing must distinguish platform model preparation from container and engine loading. A subsequent post-idle request can measure resume behavior only after that first success.

If the bounded attempt stops while the worker is still initializing, preserve the status and timing as another incomplete preparation result. Do not call it a cache miss, cache hit, free run or proof that a longer wait would succeed. Avoid changing the model revision, cache path, precision or GPU within the same measurement.
