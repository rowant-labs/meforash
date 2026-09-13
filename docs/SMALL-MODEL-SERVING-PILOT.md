# Small-model serving pilot: preparation

First execution results are recorded separately in [SMALL-MODEL-SERVING-RESULTS-V1.md](SMALL-MODEL-SERVING-RESULTS-V1.md). The preparation below is preserved as the pre-run plan.

September 12, 2026. Exploration branch only: `codex/hosting-first-small-model`. No production changes or paid requests. This is an engineering pilot, not a fine-tuning run or a biblical accuracy benchmark.

## Scope and starting configuration

Start with unchanged `openai/gpt-oss-20b` if the selected GPU and pinned engine support its native MXFP4 weights. Keep `Qwen/Qwen3.5-9B` as the comparison candidate. The first test may reject a configuration; do not automatically rent a larger GPU or convert precision to keep it running.

Model repository revisions observed through the public Hugging Face API:

| Repository | Revision |
|---|---|
| `openai/gpt-oss-20b` | `6cee5e81ee83917806bbde320786a8fb61efebee` |
| `Qwen/Qwen3.5-9B` | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |

Use an authenticated Runpod Serverless endpoint, zero Active workers, maximum one Flex worker, one GPU per worker and initially a 60-second idle window. First select an explicit A40 48 GB at the currently listed $1.22/hour. After a successful baseline, test an explicit A5000 or 3090 24 GB at the listed $0.69/hour; test L4 separately. Do not treat the GPU group as identical hardware. Set maximum engine sequences to one initially; increase deliberately for the concurrent phases if memory permits. Start with an 8,192-token total context and a 2,048-token generation ceiling; reject oversized requests instead of silently truncating them. Reasoning uses the same output allowance and must not be shown as the final answer. Try low reasoning for the initial gpt-oss engineering test, recording the actual accepted configuration.

The [Runpod worker repository](https://github.com/runpod-workers/worker-vllm/releases/tag/v2.27.0) reports v2.27.0 as the latest release at preparation time. Its release Dockerfile defaults to vLLM v0.29.0 and checks the installed version at build time. The registry resolves `runpod/worker-v1-vllm:v2.27.0` to index digest `sha256:fd9e5c55c996361aad2543d96d9d85ca055625ee5d1fcefa2d213141deb45e17`, with Linux amd64 digest `sha256:9547ad83fd9c6947d0b03749fe43839b360b1a7be188a4bd76249da63cddc5e6`. The release README supports `MODEL_REVISION` and `TOKENIZER_REVISION`; set both explicitly. These are metadata checks, not a successful runtime test. Verify the installed engine version at startup and use the digest rather than a moving tag. The [vLLM recipe](https://github.com/vllm-project/recipes/blob/main/OpenAI/GPT-OSS.md) documents Ampere support using Triton attention and Marlin MXFP4, but its A100 example does not prove an L4/3090 memory or throughput result.

The [vLLM GPT-OSS LoRA test](https://github.com/vllm-project/vllm/blob/main/tests/lora/test_gptoss_tp.py) exercises native MXFP4 with rank 8 under short-context settings. That is evidence of an adapter path, not verification of our future Tinker adapter at 8K context. Preserve compressed weights and separate adapter modules: merging into BF16 would require approximately 42 GB for parameters alone and defeat a 24 GB configuration. This first pilot uses no adapter; an authorized portability experiment comes later.

## Budget and shutdown

Proposed first-pilot ceiling: **$10 total incremental infrastructure cost**, including initialization, idle time and storage. Not a recurring subscription or training authorization. Confirm the account's actual rate before starting; the earlier rate table is an estimate awaiting account verification. Stop at $5 observed/reserved cost to leave room for delayed billing and teardown, or after two cumulative billed worker hours, whichever comes first. A single short campaign can have multiple phases; do not leave it running unattended overnight.

Maximum one worker limits multiplication of costs, but is not a dollar spending cap. Provider bills are authoritative. Request timeouts and killing a local client do not guarantee the remote job stopped. Cancel pending jobs, scale workers to zero, remove the disposable endpoint and unneeded storage, and verify no active workers or continuing charges. If cancellation or billing is uncertain, submit no further requests until reconciled.

## Test sequence

1. Record model revision, image digest, engine version, GPU identity/memory, region, price, worker limits and starting billing totals. Disable request-body logging and use only constructed, nonsensitive prompts. No user chat history or production credentials.
2. Start from zero workers and send one question. Measure request-to-first-visible-content and request-to-completion separately. Record provider queue/start/execution timing where exposed, GPU peak memory and the exact finish reason. Empty final text or token-limit termination is not a successful answer.
3. Repeat while warm with five short requests, including a two-turn conversation. Record input/output token counts, reasoning counts when available and visible output length. Do not infer billed seconds from tokens.
4. Submit batches of three and ten requests, once each, with the single-worker limit unchanged. This tests batching/queue behavior, not ten replicas. Report every slot, including timeouts, failed requests and partial answers. Stop on out-of-memory or repeated initialization failure rather than retrying automatically.
5. Disconnect one stream, verify remote cancellation behavior, then test a new question. Check that no reasoning text reaches the final-content stream. Confirm overload produces a bounded wait or an explicit error rather than indefinite hanging.
6. Let the worker actually scale to zero, then repeat a cold request. Do not infer a cold start merely from elapsed idle time. Compare a short idle window against the 60-second setting only if remaining budget permits.
7. Tear down and reconcile billing. Calculate cost per completed question and per 1,000 completed questions from total billable worker time, including failed work. Report cold and warm latency separately; a tiny sample is not a reliable production percentile estimate.

Use simple repeated engineering prompts such as explaining a supplied short paragraph and answering a follow-up about it. These fixtures establish response handling and timing, not whether the model understands original biblical languages. A separate prospective quality evaluation follows only after serving feasibility is established.

## Pass conditions and next decision

Required: authenticated access; correct model/revision; complete final answers; working streaming and follow-up context; bounded overload; understood cancellation/billing; successful teardown; no private content in public artifacts. Record ten-request completion and memory behavior without assuming it must pass on the first GPU.

Working experience targets, to be evaluated rather than promised: warm first visible content within 10 seconds, warm short answers within 30 seconds, cold first visible content within 60 seconds, and a measured workload projection within roughly $100/month. If latency or cost misses these targets, report the tradeoff and revise the configuration before training. Do not lower answer-quality requirements to hit a hosting price.

Next, verify a compatible adapter export/load path under a separate bounded training notice, then freeze a fresh quality evaluation. Keep B as the reference; neither this pilot nor an unchanged-model test is a replacement for original-language fine-tuning.

## Access and artifacts

Runpod credentials were not present in the process environment or project `.env` at preparation time. The owner can add `RUNPOD_API_KEY` to the ignored local `.env`; never publish it. Live execution remains pending access and the final pinned configuration. Use ignored `runs/small-model-serving-v1/` for receipts and raw engineering outputs, and publish only reviewed aggregate results. Do not configure a public inference endpoint or change Railway's production provider.

References: [Runpod deployment](https://docs.runpod.io/serverless/vllm/get-started), [worker configuration](https://docs.runpod.io/serverless/vllm/environment-variables), [OpenAI-compatible interface](https://docs.runpod.io/serverless/vllm/openai-compatibility), [billing phases](https://docs.runpod.io/serverless/pricing), [hosting-first research](AFFORDABLE-MODEL-EXPLORATION.md).

## Offline cost calculation

Example with hypothetical billing, not pilot results:

```sh
python3 tools/hosting_cost.py --billed-gpu-hours 2 --gpu-hour-rate 1.22 --completed-questions 100 --monthly-questions 1000
```

The projection assumes the measured traffic pattern, answer lengths and cold-start frequency remain representative. It excludes other service bills. Measure failed work in the billed-hours numerator, but count only completed answers in the denominator.
