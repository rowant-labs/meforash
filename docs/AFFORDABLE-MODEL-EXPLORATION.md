# Hosting-first smaller-model exploration

Research checked September 12, 2026. Proposal only. Branch `codex/hosting-first-small-model`, forked from `4a0d6c0` on `codex/launch`. This work can be abandoned without changing the deployed app. Retain Inkling B; no training, checkpoint export, provider messages, hosting purchase or production migration has occurred in this exploration.

## Working recommendation

Investigate a single-GPU model served through an authenticated vLLM endpoint on Runpod Serverless or Modal. Keep Railway as the application gateway for authentication, quotas and streaming. Start with gpt-oss-20b and Qwen3.5-9B as candidates, not selections. Prove the exact adapted-model serving path before a substantial training run.

A cheap catalog API for the unchanged base does not establish cheap hosting for our adapter. Current [Fireworks serverless documentation](https://docs.fireworks.ai/serverless/overview) directs custom models to on-demand deployment; [Together's adapter upload](https://docs.together.ai/docs/dedicated-endpoints/adapter) is a dedicated-endpoint route. Neither establishes a shared per-token price for our future fine-tune. Keep these as managed alternatives if a specific affordable offer becomes available.

## Economics before model choice

These are GPU-only arithmetic scenarios, not measured Meforash bills or capacity promises. Hours mean total billed worker hours across all replicas, including applicable startup and warm-idle time. They do not mean hours the website is available. A month below is 720 hours.

| Example hardware | Hourly GPU rate | 20 billed hours | 100 billed hours | Always ready, one GPU |
|---|---:|---:|---:|---:|
| Runpod Flex 24 GB group | $0.69 | $13.80 | $69.00 | $496.80 at listed rate |
| Runpod Flex A40/A6000 48 GB | $1.22 | $24.40 | $122.00 | $878.40 at listed rate |
| Hugging Face AWS L4 | $0.80 | $16.00 | $80.00 | $576.00 |
| Modal L4 | $0.7992 | $15.98 | $79.92 | $575.42 |
| Modal A10 | $1.1016 | $22.03 | $110.16 | $793.15 |
| Modal L40S | $1.9512 | $39.02 | $195.12 | $1,404.86 |

[Modal pricing](https://modal.com/pricing) additionally bills CPU, RAM and storage. Its Starter plan lists $30 monthly compute credits; calculations above deliberately exclude credits. Region and execution options can add premiums. Railway, Supabase and email remain separate costs.

[Runpod pricing](https://docs.runpod.io/serverless/pricing) groups L4/A5000/3090 hardware in its 24 GB tier. Flex can scale to zero; Active stays warm. Billed time includes initialization, execution and the configured idle timeout; storage is extra. Its [vLLM configuration](https://docs.runpod.io/serverless/vllm/environment-variables) explicitly supports LoRA modules, subject to architecture compatibility. **This remains the lowest listed 24 GB rate in this comparison**, with Modal as the alternative. Current [Runpod rates](https://www.runpod.io/pricing) supersede the earlier $0.684/hour estimate; current billing docs direct Active-worker discounts to sales, so the earlier $336.96/month Active estimate is withdrawn. Start the compatibility pilot on explicit A40 48 GB, then test a 24 GB configuration. A GPU group is not a guarantee of identical performance across devices.

[Hugging Face endpoint pricing](https://huggingface.co/docs/inference-endpoints/pricing) lists the AWS L4 rate above. Its [autoscaling documentation](https://huggingface.co/docs/inference-endpoints/guides/autoscaling) describes scale-to-zero and cold-start responses; the default one-hour inactivity window can be expensive for scattered traffic. Standard merged checkpoints fit its model-repository workflow; separate adapter packaging may require a [custom container](https://huggingface.co/docs/inference-endpoints/engines/custom_container). It is a managed fallback, not the first low-traffic cost choice.

Scale-to-zero makes a lightly used app plausible at tens of dollars in GPU usage, but this is conditional on traffic and measured runtime. Keeping even one GPU warm continuously costs hundreds. [Modal's cold-start guide](https://modal.com/docs/guide/cold-start) describes startup taking seconds to minutes and charging for resources retained during warm-idle windows. Cache weights before serving, then measure actual startup. Do not promise instant first answers.

For illustration, 1,000 isolated requests each using 30 GPU seconds plus 60 billed idle seconds consume 25 GPU hours: about $19.98 at the L4 rate, before initialization and other resources. This is an assumption, not an observed generation speed. Spread-out visitors can cost more than clustered visitors because startup and idle periods are less amortized. Ten simultaneous users also do not necessarily require ten GPUs: batching may share one GPU, subject to memory and latency tests.

## Candidate shortlist

| Candidate | Why investigate | Main unresolved issue |
|---|---|---|
| `openai/gpt-oss-20b` | U.S. developer preference; OpenAI documents 21B total / 3.6B active parameters and fine-tunability; currently available for Tinker adaptation | Quantized weights, adapter target coverage, serving kernels and reasoning overhead must be tested together; active parameter count alone does not determine memory |
| `Qwen/Qwen3.5-9B` | Smaller dense challenger; Apache-2.0 model card with vLLM serving instructions; Tinker lists this exact post-trained model | Non-U.S. developer; hybrid architecture and export/quantization compatibility need proof; biblical-language quality unknown |
| `Qwen/Qwen3-8B` | Tinker-listed fallback if the newer architecture makes deployment difficult | Older candidate, not presumed equivalent in quality; test only if the first two paths fail or justify comparison |

Sources: [OpenAI gpt-oss-20b documentation](https://developers.openai.com/api/docs/models/gpt-oss-20b), [Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B), [Tinker model catalog](https://tinker-docs.thinkingmachines.ai/tinker/models/). This is a portability shortlist, not a claim that these are the newest or strongest small models. Broad English or coding benchmarks cannot establish Hebrew, Aramaic and Greek competence.

Target a 24–48 GB GPU envelope initially. A 9B dense model's BF16 parameters alone are approximately 18 GB; cache, adapter and runtime memory come in addition. Do not assume ten long conversations fit in 24 GB. A tested quantized build may lower memory, but requires its own quality comparison. Inkling-Small is not a substitute for this small-GPU investigation; see [the existing full-model hosting review](INFERENCE-OPTIONS.md).

## Training approach

Use a capable post-trained model and perform original-language continued pretraining with LoRA, preserving the project's raw-text objective and approved editions. This is actual training. Starting a general English/Bible LLM from random weights is not a credible route within the project's budget and data scale. Inkling B's adapter cannot simply be attached to a different architecture.

Tinker lists training rates of $0.396/M tokens for gpt-oss-20b, $1.463/M for Qwen3.5-9B and $0.44/M for Qwen3-8B. At an illustrative 3.5M input positions, one pass is roughly $1.39, $5.12 and $1.54 respectively. Retokenization, validation, sampling, storage and export tests are extra; these are not complete experiment quotes. [Rates](https://tinker-docs.thinkingmachines.ai/tinker/models/).

Tinker's [adapter export tutorial](https://tinker-docs.thinkingmachines.ai/tutorials/deployment/lora-adapter/) provides a route toward external serving, not proof that every target combination works. Check exact base revision, tokenizer/template, attention/MLP/output-head coverage and conversion before choosing a recipe. If necessary, train through a local rented-GPU stack matching the serving architecture instead. Do not silently drop trained modules to make an export load.

## Execution gates

1. **Serving specification:** choose one provider/hardware pair; pin engine and base revisions; define authenticated endpoint, no prompt logging, output/reasoning limits, maximum replicas and shutdown procedure. Resolve current pricing and account access. Prepare an explicit paid-test ceiling before provisioning.
2. **Unchanged-model smoke test:** measure startup, first visible answer, total latency, peak memory and billed runtime at 1/3/10 requests. Test streaming, disconnects, overload and restart recovery. These are engineering fixtures, not an accuracy benchmark.
3. **Adapter portability proof:** after a pre-training notice and bounded authorization, make a tiny disposable adaptation or use a rights-cleared compatible fixture, export/load it, verify target modules and compare outputs across training/serving engines. A fixture does not establish our final recipe's compatibility.
4. **Quality baseline and prospective evaluation:** use existing disclosed questions only for development screening. Freeze new questions, rubric and failure rules before full adaptation; isolate them from training authors. Include Hebrew, Greek, Aramaic, manuscript uncertainty, English explanations, follow-ups and life applications. Follow [EVALUATION-RUNBOOK.md](EVALUATION-RUNBOOK.md); keep raw receipts/review packets private and publish reviewed summaries.
5. **One bounded fine-tune:** present exact data, objective, target modules, recipe and complete cost ceiling first. Compare the smaller unchanged model, its adapted version and retained B. Separate training effects from model-size changes. Keep retrieval inputs matched; also test source-text retention separately. Use blinded case-level review; label AI judgments accurately.
6. **Decision:** require acceptable answer quality, verified portability and measured operating cost. Reject the idea if these fail. No automatic promotion, merge, deployment or weight publication. Public weight release remains a separate owner decision after rights and model-card review.

Before any eventual migration, update provider disclosures and verify data-retention settings. Public weights are not necessary to run a private custom endpoint. Preserve the current README's statement that overall English-answer improvement remains unestablished.

## Prepared pilot

See [SMALL-MODEL-SERVING-PILOT.md](SMALL-MODEL-SERVING-PILOT.md) for model/image pins, the proposed $10 ceiling and the 1/3/10-request sequence. An offline [cost calculator](../tools/hosting_cost.py) converts provider-billed hours into cost per 1,000 completed questions. Credentials and live measurements remain pending.
