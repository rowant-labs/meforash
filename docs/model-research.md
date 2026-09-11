# Models and fine-tuning research

**Scope update:** This file preserves the initial model and service research. The active recommendation is the [whole-Bible training plan](training-plan.md), which makes raw-text adaptation a central experiment. The optional-training/retrieval-first sequence below is superseded; the dated model, pricing, export, and hosting findings remain supporting research.

Verified September 5, 2026. Prices are USD and can change. This is a research recommendation; no training, paid inference, account creation, or purchase was performed. Provider benchmarks are not evidence of competence in Biblical Hebrew, Aramaic, Koine Greek, or textual criticism.

## Recommendation

Begin with a source-grounded application and a small model comparison, then train only if the comparison reveals a repeatable behavior problem. My practical starting baseline is **gpt-oss-120b through a token-priced provider**, with **Muse Glimmer 30B** as the current Meta alternative and **Nemotron 3.5 Lightning 30B** as the inexpensive candidate. If fine-tuning is valuable, **gpt-oss-20b or gpt-oss-120b on Tinker** are straightforward first experiments. **Inkling-Small** is a newer U.S. open-weight comparison worth testing, especially when eventual multimodal work matters, but its name disguises substantial self-hosting requirements.

This selection is an engineering judgment about price, availability, portability, and testability—not a finding that any one is the best biblical scholar. Spend a small amount comparing the exact same source packets before choosing. If U.S. origin is a preference rather than a hard constraint, add one current non-U.S. contender, **Qwen3.8-27B**, to test whether the preference costs appreciable task accuracy.

## What “Meta Spark 1.3” means

The initial model suggestion referred to a real model: **Muse Spark 1.3**, released **September 2, 2026**, accessible through Meta Model API and Muse Code. Meta's announcement describes its open-weight release as future work, so it is not presently the downloadable fine-tuning base for this project. It could serve as an API comparison. [Meta announcement](https://research.meta.ai/blog/introducing-muse-spark-1-3)

Meta also released **Muse Glimmer 30B on August 10, 2026**, with Apache 2.0 weights. It is explicitly intended for local agents, supports text and images, and was trained on data in over 100 languages. Meta says its quantized language weights are under 20 GB and target total 24 or 32 GB memory envelopes. The release discusses custom training through TorchTitan. This is the relevant *current Meta open-weight model*, ahead of choosing an older Llama simply because its name is familiar. [Meta Glimmer announcement](https://research.meta.ai/blog/introducing-muse-glimmer-open-agentic-model)

The Glimmer model card lists about 29.6B parameters, a context of 131,072+, and January 4, 2026 knowledge cutoff. Its quantized variants target 24/32 GB hardware; this does not establish that maximum context will fit at those sizes. Meta explicitly says not every language in pretraining has been evaluated. [Meta model card](https://huggingface.co/meta-models/Muse-Glimmer-30B)

## Shortlist and real constraints

| Model | Role in this project | Weight license / context | Practical constraint |
|---|---|---|---|
| OpenAI gpt-oss-120b | First larger baseline; inexpensive managed fine-tuning | Apache 2.0; 131,072 native; **32K default on Tinker**, separate 128K offering | 117B total / 5.1B active; fit in H100-class memory, not an ordinary inexpensive web host |
| OpenAI gpt-oss-20b | Lower-cost/local experiment and first small adapter | Apache 2.0; 131,072 native; **32K on Tinker** | 21B total / 3.6B active; lower capacity needs domain evaluation |
| Meta Muse Glimmer 30B | Current Meta open-weight comparison; plausible local serving | Apache 2.0; 131,072+ native | Not on the current Tinker model list; separate tuning workflow |
| NVIDIA Nemotron 3.5 Lightning 30B-A3B | Cheap retrieval/tool-use and answer candidate | OpenMDW 1.1; up to 1M native; **64K default / 256K on Tinker** | English-centric supported-language list does not establish Greek or Hebrew quality |
| Thinking Machines Inkling-Small | Newer U.S. generalist comparison; Tinker tuning | Apache 2.0; up to 1M native; **64K default / 256K on Tinker** | 276B total / 12B active; official NVFP4 deployment needs at least 180 GB aggregate VRAM |
| Google DeepMind Gemma 4 31B | Optional multilingual/local comparison | Apache 2.0; 256K | Google parent is U.S.; DeepMind is an international organization. Not on current Tinker list |
| Qwen3.8-27B | Optional non-U.S. challenge model | Apache 2.0; 262,144 native; **64K default / 256K on Tinker** | Dense model; more expensive Tinker training, unknown biblical-language superiority |

The gpt-oss details come from official [120b documentation](https://developers.openai.com/api/docs/models/gpt-oss-120b) and [20b documentation](https://developers.openai.com/api/docs/models/gpt-oss-20b). The native architecture context and the context actually sold by an inference/training provider are different limits; Tinker limits and prices are below. Tinker hosts these open weights; this is not OpenAI's hosted fine-tuning product.

OpenAI's local guide recommends at least 16 GB VRAM/unified memory for 20b and 60 GB for 120b, using their shipped MXFP4 quantization. These are inference sizing guides, not guarantees for long context, simultaneous users, or training. Reserve additional room for the operating system and working memory. [Official local guide](https://developers.openai.com/cookbook/articles/gpt-oss/run-locally-ollama)

NVIDIA released Lightning on **August 11, 2026**. The official model card describes a 30B-total/3B-active hybrid Mamba/attention/MoE model, supports English, Spanish, French, German, Italian, and Japanese, and specifies **OpenMDW License Agreement v1.1**. Do not apply older Nemotron license assumptions to this release. [NVIDIA model card](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard)

Inkling-Small was released **July 30, 2026**. Its official card gives 276B total/12B active, Apache 2.0, general multilingual support, and at least 600 GB aggregate VRAM for BF16 or 180 GB for NVFP4. It may be affordable by API even though self-hosting is a poor initial fit. [Inkling-Small model card](https://thinkingmachines.ai/model-card/inkling-small/)

Google's current Gemma 4 card lists 31B dense and 26B-A4B MoE variants, 256K context, Apache 2.0, and pretraining on over 140 languages. That is a reason to test it, not proof of ancient-language competence. [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4)

Qwen3.8-27B's publisher reports a 27B language model with native vision and controllable thinking, 262,144 native context expandable to 1M, and Apache 2.0. Its published gains in coding and agent tasks motivate including it as an optional challenger; those scores do not resolve this project's historical questions. [Qwen model card](https://huggingface.co/Qwen/Qwen3.8-27B)

Older Llama 4 Scout/Maverick remain downloadable, but are 109B/400B total, have a custom commercial license, and their officially supported languages do not include Greek or Hebrew. The 17B labels refer to active parameters, not the memory needed to hold their weights. [Meta Llama 4 card](https://github.com/meta-llama/llama-models/blob/main/models/llama4/MODEL_CARD.md) Tinker retired its Llama 3.x lineup on **June 12, 2026**, so old Tinker/Llama tutorials are not a current plan. [Tinker deprecations](https://tinker-docs.thinkingmachines.ai/tinker/model-deprecations/)

## Tinker: what it actually does

Tinker provides managed **LoRA fine-tuning**: a relatively small learned adapter changes how a frozen base model behaves. It does not currently offer arbitrary training from scratch or full parameter training. Its primitives support supervised learning and reinforcement-learning workflows, and saved checkpoints can be downloaded. The developer still supplies the dataset, learning objective, evaluations, and training loop; it is infrastructure, not an automatic biblical-research workflow. [Tinker documentation](https://tinker-docs.thinkingmachines.ai/)

### Verified current prices

All values are **per million tokens**, at the indicated default context. Prefill means inference input processing; sample means generated output; train covers forward **and** backward passes.

| Tinker base model | Default context | Prefill | Sample | Train |
|---|---:|---:|---:|---:|
| gpt-oss-20b | 32K | $0.18 | $0.45 | $0.396 |
| gpt-oss-120b | 32K | $0.33 | $0.84 | $0.737 |
| Nemotron 3.5 Lightning | 64K | $0.195 | $0.495 | $0.44 |
| Inkling-Small | 64K | $0.58 | $1.44 | $1.73 |
| Inkling | 64K | $1.87 | $4.68 | $5.61 |
| Qwen3.8-27B | 64K | $1.86 | $5.595 | $4.103 |

Lightning and Inkling-family prices shown have **temporary 50% discounts**; budget for possible doubling. Larger-context IDs have different prices: gpt-oss-120b at 128K trains at $2.33/M; Inkling-Small at 256K at $3.47/M. Prompt-cache hits receive reduced prefill rates. Checkpoint storage is $0.10/GB-month. [Tinker pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/) [Machine-readable prices](https://tinker-docs.thinkingmachines.ai/tinker/models.json)

**Illustrative calculation, not a provider quote:** 1,000 examples averaging 2,000 *complete rendered tokens* per example, processed for three epochs, is 6M training tokens. Forward/backward compute would be approximately $2.38 for gpt-oss-20b, $4.42 for 120b, $2.64 for Lightning, $10.38 for Inkling-Small, $33.66 for Inkling, or $24.62 for Qwen3.8-27B at the listed rates. Do not add a second prefill fee for the same forward/backward training operation. Separate validation, example generation, sampling, and optional reference-model passes are extra.

A 100-question evaluation averaging 4,000 prompt tokens and 2,000 **total generated** tokens would cost about $0.15 on gpt-oss-20b, $0.30 on 120b, $0.18 on Lightning, or $0.52 on Inkling-Small at Tinker's training-pool sampling rates. Real agent runs can cost more because each tool round invokes the model again.

### Token accounting and budget traps

- Count source passages, tool definitions/results, system instructions, conversation history, and formatting as input. English word counts are a poor estimate for pointed Hebrew and polytonic Greek: run each candidate's actual tokenizer.
- Count reasoning and visible answer tokens in generated output. Hiding a reasoning panel does not make those generated tokens free. Thinking Machines explicitly includes reasoning tokens in its cost comparisons. [Inkling-Small launch and costing notes](https://thinkingmachines.ai/news/inkling-small/)
- For training estimates, conservatively count the full rendered sequence, including context, repeated each epoch. Masking a prompt out of the learning loss does not mean it disappears from model computation. The reviewed billing schema says tokens processed by forward/backward passes, but does not precisely specify every masking/padding edge case. Verify a tiny calibration run against actual usage before extrapolating. [Training billing schema](https://tinker-docs.thinkingmachines.ai/tinker/api-reference/types/trainingbillingevent/)
- Monitor spend locally with a maximum examples/steps/token budget, not only a billing dashboard: Tinker's usage export may lag by a few hours and reports raw tokens/storage rather than dollar totals. [Billing documentation](https://tinker-docs.thinkingmachines.ai/tinker/cli/billing/)
- No introductory credits were verified. Do not make the plan depend on free credits. Annotation and qualified review will consume far more time than a small adapter's compute.

### Serving and export

For a personal experiment, Tinker's OpenAI-compatible checkpoint API is usable and avoids renting a continuously running GPU. It is explicitly **beta**, intended for testing, evaluations, and low internal traffic; latency and throughput can change. That fits an internal prototype but does not establish a dependable eventual public deployment. [Checkpoint inference documentation](https://tinker-docs.thinkingmachines.ai/tinker/compatible-apis/openai/)

Tinker's separately listed serverless beta currently supports **Inkling and Inkling-Small only**, and the provider discourages intensive production use. Inkling-Small serverless at 256K is $0.30 input/$1.20 output per million; this is a different service/price from training-pool sampling. Confirm the required checkpoint path and adapter support rather than assuming a cheap base-model endpoint accepts arbitrary adapters. [Serverless price data](https://tinker-docs.thinkingmachines.ai/tinker/serverless.json)

Saved sampler checkpoints can be downloaded and converted into PEFT adapters or merged Hugging Face models. The conversion remaps internal Tinker parameter names, so copying files directly to any host is not a reliable plan. The tutorial demonstrates export and vLLM/SGLang loading; it does not certify every architecture/quantization/host combination. Require one inexpensive **train → export → load → compare outputs** test with the exact selected model before investing in substantial data creation. [Weights management](https://tinker-docs.thinkingmachines.ai/tutorials/core-concepts/weights/) [PEFT export tutorial](https://tinker-docs.thinkingmachines.ai/tutorials/deployment/lora-adapter/)

An adapter depends on the exact base weights, tokenizer, and formatting. Preserve all versions and an export, not just a provider model name. Model retirements make this material: an adapter cannot simply be attached to a different model family.

## What to train, if the evidence supports training

For this project, original-language texts belong first in a retrievable source database, aligned with lemma/morphology annotations, translations, witness information, and rights metadata. The model can answer English questions using those tools without being retrained to read everything. Human-checked tools can supply exact Greek/Hebrew quotations and morphology, leaving the model to explain the evidence. This also lets users inspect where an answer came from.

Fine-tune on *how to use evidence*: choosing the right lookup, identifying which edition is quoted, separating a reading from an interpretation, explaining linguistic uncertainty, citing supplied evidence correctly, and declining claims that the evidence does not establish. A corpus of raw Bible verses is not equivalent to instruction examples demonstrating these behaviors. Repeating verses may teach memorization while leaving textual criticism and calibrated interpretation untouched.

A sensible first experiment is 300–1,000 reviewed, diverse examples, then one to three epochs with a small LoRA rank (e.g. 16 or 32), chosen as experimental starting points rather than universal optimal settings. Use the cookbook's model-specific renderer and learning-rate guidance. For reasoning models, preserve the expected reasoning/final channel format. Avoid creating large quantities of unchecked synthetic Greek/Hebrew analysis: confident errors will become training targets.

Compare four conditions on the same held-out questions:

1. Base model without evidence, to measure what it is guessing from memory.
2. Base model with the evidence tools and source packets.
3. Fine-tuned model with the same evidence tools and packets.
4. A stronger external reference model, reviewed by a person rather than treated as ground truth.

Hold out passages, question families, and close paraphrases—not random rows whose twin remains in training. A familiar verse may already occur in pretraining, so copying its English translation is weak evidence of generalization. Include unfamiliar/constructed linguistic tests and source packets that require the answer to follow the provided edition rather than memory. Evaluate exact quotation, morphology, witness attribution, citation support, misleading etymology, disputed interpretation, and appropriate uncertainty separately.

Do not infer historic neutrality from U.S. ownership, open weights, or an ancient-language fine-tune. Every general model reflects training choices, and the application's curated source selection is itself an editorial choice. Label those choices and make the evidence inspectable. Treat the final fine-tuning decision as conditional: if retrieval plus prompting already solves the problem, retaining the unmodified model may be the better product.

## Suggested model/training allocation within the initial budget

Reserve roughly $10–20 for comparing models, $10–30 for carefully bounded tuning/evaluation/export experiments, and keep the majority for source preparation, qualified review, deployment contingencies, and subsequent use. These are spending caps, not claims that expert review can be purchased comprehensively at this price. Do not buy hardware or pretrain a general LLM on a $200 budget. Choose the base model after measuring the historical questions that matter to the user, then check a concrete path to public hosting before committing to an adapter.
