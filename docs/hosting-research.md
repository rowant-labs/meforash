# Bible project: hosting and recurring costs

Research checked **September 5, 2026**. USD, excluding tax, domain registration, paid source licenses, and human review. This is a planning estimate, not a provider quote; no account was created, service deployed, or money spent. Current direct pages sometimes differ materially from search snippets and older guides.

## Recommendation

Build the first version as a private, authenticated Next.js app on Vercel with Supabase Postgres/Auth, and call a managed open-weight model API. Use the existing database for source records, verse/lemma lookups, text search, and optionally pgvector; do not add a separate vector database, Railway service, or GPU merely to start. Ingestion and evaluation can run locally. The app owns the sources, retrieval rules, citations, prompts, and evaluations; the model remains replaceable.

This can realistically stay below **$20/month for personal use**, provided the corpus and traffic fit the free application/database tiers. Reserve **$5–15/month** for inference/embeddings/evaluation, with a $20 stop threshold. Private login does not mean all processing stays on the user's machine: selected evidence and questions go to the inference provider.

## Worked token costs

Assume one model request per question, **6,000 billed input tokens and 1,000 total billed output tokens**, with no caching discount. 500 questions = 3 million input + 0.5 million output tokens; 3,000 questions = 18 million + 3 million. This is a cost comparison, not a quality ranking. Evaluate ancient-language performance separately.

| Model/provider | Input / output per million | 500 questions | 3,000 questions |
|---|---:|---:|---:|
| GPT OSS 120B, Groq | $0.15 / $0.60 | $0.75 | $4.50 |
| GPT OSS 120B, Fireworks Standard | $0.15 / $0.60 | $0.75 | $4.50 |
| GPT OSS 120B, Together | $0.15 / $0.60 | $0.75 | $4.50 |
| Gemma 4 31B, Together | $0.39 / $0.97 | $1.66 | $9.93 |
| Llama 3.3 70B, Together | $1.04 / $1.04 | $3.64 | $21.84 |

Rates: [Groq models](https://console.groq.com/docs/models), [Fireworks serverless pricing](https://docs.fireworks.ai/serverless/pricing), [Together pricing](https://www.together.ai/pricing). Together also lists Muse Glimmer 30B at $0.35/$1.50; Fireworks lists NVIDIA Nemotron 3.5 Lightning 30B A3B at $0.05/$0.20. These are additional candidates for the model evaluation, not automatic recommendations.

Crucial caveats: the 1,000-output assumption includes any billable reasoning tokens. If actual output is 4,000 tokens per answer, GPT OSS 120B rises to **$1.65 / $9.90** for the two scenarios. A second verification call, retries, query expansion, and long conversation history also add cost. Greek/Hebrew token counts must be measured with the chosen tokenizer; English word counts are not a reliable estimate. Record token usage per request and bound context, output, tool calls, and retries.

**Do not reuse the old Groq Llama 3.3 quote of $0.59/$0.79.** The directly opened current model catalog marks Llama 3.3 70B and Llama 3.1 8B as enterprise/contact-sales; GPT OSS 120B and 20B retain public self-serve prices. Groq's 120B endpoint ID is `openai/gpt-oss-120b` and is listed as production.

Together currently requires a **minimum $5 credit purchase** and says it does not offer a free trial. This is prepaid usage, not an additional monthly hosting fee. [Together billing support](https://support.together.ai/articles/1862638756-changes-to-free-tier-and-billing-july-2025).

## Application and database bill

| Component | Personal MVP | When the budget increases |
|---|---|---|
| Vercel | Hobby $0; personal, noncommercial use | Pro $20/month base, usage/extra seats can add cost |
| Supabase | Free: 500 MB database, 1 GB file storage, 5 GB egress; two active projects | Pro $25/month for one Micro project under included allowances |
| Railway | Omit initially | Hobby minimum $5/month includes $5 usage; excess resource usage costs more |
| Model API | ~$1–10/month for the illustrated workloads | More questions, larger context, reasoning and evaluation |

Vercel's [Hobby documentation](https://vercel.com/docs/plans/hobby) restricts it to personal noncommercial use; [current pricing](https://vercel.com/pricing) gives the Pro base. Free limits are ceilings, not unlimited hosting.

The project targets an eventual public app. Public availability alone does **not** require Vercel Pro: a personal noncommercial public pilot may still fit Hobby, subject to its terms and usage limits. Start with private development, then an invite-only public pilot with per-user quotas. Paid or otherwise commercial operation, stronger database reliability, or higher usage justifies the paid stack. A fully open anonymous endpoint needs rate limits and abuse controls before launch because inference bills can rise independently of ordinary page traffic.

Supabase Free pauses after a week of inactivity and has no automatic backups. Pro includes $10 compute credit, enough for one Micro instance; additional projects and larger compute can increase the bill. A corpus with multiple editions, morphology and embeddings may outgrow 500 MB, so measure actual database/index size before promising the free tier. [Supabase pricing](https://supabase.com/pricing).

Railway is useful later for a persistent Python ingestion worker or API. Its $5 Hobby amount is a minimum with included usage, **not $5 plus the first $5 of compute**. [Railway pricing](https://railway.com/pricing). Set spending and resource limits if added. [Railway cost controls](https://docs.railway.com/pricing/cost-control).

Practical monthly totals using GPT OSS 120B: personal Free+Free stack at 500 questions can budget **$5–10**, and at 3,000 questions **$10–20**, allowing for embeddings/reasoning/evaluation. Once paying for both Vercel Pro and Supabase Pro, the fixed base is **$45/month before inference**. If reliability requires Supabase Pro while personal Vercel Hobby remains suitable, budget **$30–40/month**. These are recommended envelopes, not service guarantees.

## Why inexpensive fine-tuning does not imply inexpensive hosting

An adapter changes a model's behavior but still needs its exact base model at inference. Before training, confirm the **exact base revision, adapter format, rank, supported modules, quantization, and serving price** for the intended host. A small downloadable LoRA file is not a complete model that can run in an ordinary Vercel function.

| Provider | Current adapter path | Implication for this budget |
|---|---|---|
| Together | Current overview directs fine-tuned models to dedicated GPU endpoints | Do not promise cheap per-token custom LoRA hosting based on old guides |
| Fireworks | Current serverless/model docs require on-demand deployments for custom LoRAs | Base-model API prices do not establish the total private-adapter bill |
| Groq | LoRA is enterprise-only; public-cloud pay-per-token option exists but pricing requires sales | Not a verified low-budget self-serve path |
| DeepInfra | Documented LoRA uploads over supported hosted bases | Potential option; supported base list is in the logged-in upload form and public guide does not establish the exact hosting tariff |
| Modal / Runpod | Run compatible serving software with private base weights and adapter | Flexible experimentation; billed GPU time, engineering work, cold starts |

[Together inference overview](https://docs.together.ai/docs/inference/overview) and [custom-model deployment](https://docs.together.ai/docs/dedicated-endpoints/custom-models). There is an inconsistency worth preserving: the [Together upload API](https://docs.together.ai/reference/upload-model) still describes a `base_model` field for a serverless pool. This is insufficient evidence of currently purchasable self-serve serverless LoRA access for the selected model. Verify in the account before choosing a training route.

Fireworks [cost structure](https://docs.fireworks.ai/faq/billing-pricing-usage/pricing/cost-structure) says LoRAs require dedicated deployment; its older marketing language about serving fine-tunes at base-model rates should not be read as a promise of zero fixed GPU cost. [Deployment docs](https://docs.fireworks.ai/guides/ondemand-deployments) say the default scales to zero after an hour, returns HTTP 503 during wakeup, and deletes zero-minimum deployments after seven idle days. This is materially different from a warm shared API.

Groq currently documents only Llama 3.1 8B for LoRA, exact base versions, ranks 8/16/32/64, and enterprise pricing/access. It does not offer LoRA training; adapters are uploaded. [Groq LoRA docs](https://console.groq.com/docs/lora).

DeepInfra's current [LoRA guide](https://docs.deepinfra.com/private-models/lora) demonstrates a Llama 3.1 8B adapter and accepts a private Hugging Face repository token. The complete supported bases and exact price could not be verified publicly in this research. Treat it as an investigation lead, not a committed hosting solution. Public [GPT OSS 120B model page](https://deepinfra.com/openai/gpt-oss-120b) did not expose a readable price to the research tool; third-party quotes were therefore excluded.

## Private GPU alternatives and cold-start costs

Modal Starter is $0 plus compute and currently advertises $30/month credits. L4 costs **$0.000222/second ≈ $0.80/hour**, A100 80 GB **$0.000694/second ≈ $2.50/hour**. CPU and RAM are separate. [Modal pricing](https://modal.com/pricing). Keeping a GPU warm is billable; the default scale-down window is 60 seconds, configurable, and a minimum container count prevents scale-to-zero. [Modal cold starts](https://modal.com/docs/guide/cold-start). Do not interpret container startup marketing as guaranteed end-to-end model readiness.

Runpod lists a 24 GB flex-serverless category (L4/A5000/3090/MIG) at approximately **$0.69/hour**, and always-on RTX A5000 Pods at **$0.27/hour** (availability varies). Standard persistent network storage under 1 TB costs **$0.07/GB/month**. [Runpod pricing](https://www.runpod.io/pricing). Serverless bills startup/model loading, execution, and post-request idle time, rounded to seconds; default idle timeout is five seconds. Flex workers scale to zero; active workers remain running. [Runpod billing mechanics](https://docs.runpod.io/serverless/pricing).

Illustrative private **small-model** experiment, not a measured performance result: if each isolated request costs 60 GPU seconds including loading/idle, 500 requests = 8.33 GPU hours, and 3,000 = 50 hours. At Modal L4 that is **$6.66 / $39.96 plus CPU/RAM** before any credits. At Runpod's ~$0.69 category it is **$5.75 / $34.50 plus storage**. Batching sessions can reduce cold-start overhead; longer model loads or idle windows can raise costs sharply. A 24 GB device is not assumed suitable for every 20B–120B model at the desired context length.

An always-on $0.27/hour A5000 is **$197.10/month at 730 hours**, before storage. Hugging Face AWS L4 endpoints are **$0.80/hour = $584/month** if kept on; A100 80 GB is $2.50/hour. It bills initialization/running time by the minute. [Hugging Face pricing](https://huggingface.co/docs/inference-endpoints/pricing). Its scale-to-zero default is one idle hour; waking may take minutes and return 503s. [Hugging Face autoscaling](https://huggingface.co/docs/inference-endpoints/guides/autoscaling). These are suitable deployment options, but poor initial economics for a lightly used personal Bible app.

## Local computer and U.S. preference

The hardware scenario considered here is an **8 GiB development computer**. Use it for development, text processing and evaluation orchestration. It is a poor fit for the main 20B+ model shortlist. A smaller quantized model can be a learning sandbox after benchmarking memory and latency, but buying replacement hardware is not justified by this initial budget. API inference avoids the purchase and enables comparison with much larger models.

Keep three requirements separate: (1) U.S.-origin model developer, (2) U.S.-based inference company, and (3) guaranteed U.S. processing/storage. They are not interchangeable. Groq states retained customer data is in U.S. GCP buckets and makes zero-data-retention controls available; that statement alone is not an inference-location guarantee. [Groq data policy](https://console.groq.com/docs/your-data). Fireworks has explicit [U.S.-only endpoints](https://docs.fireworks.ai/serverless/us-only-serverless), but the presently documented list is selected Kimi, DeepSeek and GLM models, not the proposed U.S.-origin shortlist. If U.S.-only processing is a firm requirement, verify the exact endpoint contract or use a selected U.S. deployment region rather than infer residency from company headquarters.

## Implementation guardrails for the plan

- Authenticate the app and allowlist the initial user; keep API keys only on the server.
- Bound retrieved context and total billed output; retain source identifiers through generation and verify citations against stored text.
- Log request token totals, model/provider/version, latency, retrieval IDs, and estimated cost; avoid unnecessary personal-question logging.
- Use a database-backed daily question cap and monthly stop threshold, plus provider spending controls. A provider's broad default resource limit is not an adequate $20 hobby budget.
- Keep source/ingestion snapshots locally because the free database has no managed backup. Measure embeddings/index size before expanding beyond the pilot corpus.
- Keep a provider interface so a model can be replaced without rewriting retrieval or the frontend. Preserve tested model revisions/settings in evaluation records.
- Run a small hosted base-model benchmark first. Spend on a custom adapter only after measuring a specific repeatable deficiency, confirming a compatible serving path, and showing improvement on held-out questions.
