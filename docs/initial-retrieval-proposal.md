# A practical plan for a historical Bible research assistant

**Scope update:** The user's clarified objective is whole-Bible model training. The active recommendation is now the [whole-Bible training plan](training-plan.md). The document below preserves the earlier retrieval-first proposal and supporting architecture/cost research; its narrow pilot and optional-training sequence are superseded.

Research date: **September 5, 2026**. Budget: **up to $200 to explore and establish a prototype**, followed by modest operating costs. Intended outcome: an eventual public app answering English questions about the earliest recoverable biblical texts and their historical context. A U.S.-developed model is preferred, with alternatives allowed if they perform better.

**Recommendation: build a small, evidence-based research assistant using an existing open-weight model and a curated source library. Reserve a separate $10–30 experiment for fine-tuning through Tinker. Choose the production model by testing it on historical questions, and retain a fine-tune only if it improves the answers.**

This budget can support software, API use, and small training runs. It cannot fund a newly pretrained general-purpose LLM or comprehensive professional biblical scholarship. The enduring work will be the organized evidence, editorial method, and evaluation set. These remain useful when the underlying model changes.

All prices below are planning estimates in USD, excluding tax, human labor, domains, and optional paid source licenses. No model was benchmarked, trained, purchased, or deployed during this research. Availability and prices were checked against current primary sources; account-level access and actual performance remain implementation checks.

## 1. Define what the assistant should know—and what an answer should establish

“The earliest recoverable Bible” is a worthwhile research aim, but it is not one surviving document that can be uploaded. The app needs to distinguish five related questions:

| Question | Evidence needed |
|---|---|
| What does this surviving manuscript actually read? | An identified witness, location in the manuscript, transcription, corrections, and gaps |
| What reading does a scholarly edition print? | A named edition, its version, and its editorial method |
| Which earlier wording is best supported? | Comparison of witnesses and versions, plus explicit scholarly arguments and uncertainties |
| What might the wording have meant in its setting? | Grammar, vocabulary, genre, immediate context, and period-appropriate historical evidence |
| How was it understood later? | Dated reception and interpretive sources, identified separately from original context |

Treat the Hebrew Bible, including its Aramaic portions, and the Greek New Testament as the initial textual scope. The Septuagint matters both as an ancient Greek text and as evidence relevant to Hebrew textual history. Canonical collections, book order, and verse numbering must be explicit; later expansion can add other Jewish and Christian texts without silently treating one modern canon as the only ancient collection.

A manuscript's age, the age of the reading it preserves, and the date of composition are different things. Missing material is not an attested omission. A modern critical edition is not itself an ancient manuscript. Early evidence does not automatically settle every reading, and competing literary editions can matter alongside individual word variants. Source references and fuller qualifications are in the [biblical sources research](source-research.md).

My proposed editorial rule is historical and philological: explain the evidence and its limits, represent serious disagreements in proportion to their support, and label theological reception when relevant. U.S. ownership and open weights do not establish scholarly neutrality. Neither does a Greek/Hebrew fine-tune.

The ordinary answer should provide a short English explanation, the relevant original-language wording with an identified source, the evidence for any disputed reading, the historical interpretation, and clear uncertainty where needed. Exact quotations should be displayed from the database. The model should explain the evidence it was given, and say when the library cannot establish a claim.

## 2. Use retrieval first, with a deliberate training experiment

| Approach | What it changes | Fit for this project |
|---|---|---|
| Pretraining from scratch | Creates the model's language and reasoning abilities | Outside this budget for a useful general assistant |
| Continued pretraining on raw Greek/Hebrew texts | Adjusts prediction of domain text | A later research option if language tests identify a clear gap; not the starting plan |
| Supervised fine-tuning, preferably LoRA | Learns from examples of desired responses and tool use | Affordable experiment for evidence handling, response structure, and uncertainty |
| Retrieval-augmented generation, or RAG | Supplies relevant source material at question time | Foundation of the app |
| Harness | Coordinates searches, evidence packets, model calls, citation checks, and cost limits | The most useful custom software to build first |

You can ask questions in English without first training a model on the entire Greek and Hebrew Bible. English translations and glosses can lead to the relevant passage; structured verse and word identifiers then retrieve the original-language text and annotations. This route does not depend entirely on a general model's ability to translate ancient languages from memory.

Fine-tuning is still a real part of the plan. Its first objective should be something measurable, such as correctly distinguishing a surviving reading from a reconstruction, identifying missing evidence, or using the right source lookup. Simply repeating the biblical text during training does not supply the manuscript histories, linguistic argument, or historical scholarship necessary for those tasks.

Research comparing factual knowledge injection found retrieval stronger than unsupervised fine-tuning in its tested settings. That supports this starting hypothesis, not a rule that retrieval always wins. [Ovadia et al.](https://arxiv.org/abs/2312.05934) Ancient-language adaptation can help on specific tasks, but success translating Ancient Greek into Modern Greek does not demonstrate historical understanding in English. [Mavromatis et al.](https://aclanthology.org/2026.lrec-1.684/)

## 3. Compare a short list of current models

Your remembered **Muse Spark 1.3** is real. Meta's September 2 announcement makes it available through its API and says open weights are still forthcoming. It is therefore an optional hosted comparison, rather than the downloadable training base today. [Meta's Spark 1.3 announcement](https://research.meta.ai/blog/introducing-muse-spark-1-3)

Meta's relevant current open-weight option is **Muse Glimmer 30B**, released under Apache 2.0. Its quantized configuration targets systems with substantially more memory than the assumed development computer. [Meta's Glimmer announcement](https://research.meta.ai/blog/introducing-muse-glimmer-open-agentic-model)

| Candidate | Why test it | Decision |
|---|---|---|
| **gpt-oss-120b** | Apache-licensed U.S. open weights, inexpensive managed inference, Tinker support | First baseline for the app |
| **Muse Glimmer 30B** | Current Meta open-weight option | Main Meta comparison; separate tuning workflow |
| **Nemotron 3.5 Lightning 30B-A3B** | Low inference cost and Tinker support | Test whether the inexpensive option is adequate |
| **gpt-oss-20b** | Smaller open-weight base and cheap adapter experiments | First small-model training candidate |
| **Inkling-Small** | Newer Thinking Machines open weights and integrated training tools | Add if the first comparisons leave a quality gap |
| **Qwen3.8-27B** | Non-U.S. open-weight comparison | Optional challenge to the U.S. preference |

The shortlist is an engineering recommendation, not a ranking of biblical-language ability. No verified model card establishes which candidate is best at Biblical Hebrew, Aramaic, Koine Greek, or textual criticism. General benchmark claims do not resolve that question. Exact licenses, context limits, and model-card links appear in the [model research](model-research.md).

Start by comparing the first three on the same 30 questions and evidence packets, then add at most one challenger. Choose the least costly model that passes the source-support and historical-reasoning tests. Use a stronger hosted model as a comparison when helpful; its answers must also be checked against evidence.

“Active parameters” measures only the part of some models used per token. It does not mean all other weights disappear from memory. For example, Inkling-Small has 276B total parameters and requires large aggregate GPU memory even in its official low-precision deployment. It can be an affordable API experiment while remaining an expensive machine to host. [Inkling-Small model card](https://thinkingmachines.ai/model-card/inkling-small/)

## 4. Build a source library suitable for eventual public use

The first library should have a source registry with edition, author/editor, rights, version or commit, acquisition date, and an immutable snapshot. Store text and annotations with their separate licenses. Free website access, a permissive software license, and permission to redistribute a database are different things.

| Source | Initial use | Rights and scope |
|---|---|---|
| **Open Scriptures Hebrew Bible** | Hebrew/Aramaic text, lemma and morphology lookup | WLC text is public domain; OSHB annotations CC BY 4.0. It supplies a Masoretic base, not a complete reconstruction of earlier Hebrew forms. [Repository](https://github.com/openscriptures/morphhb) |
| **SBL Greek New Testament** | Named Greek reading text | Current license is CC BY 4.0. Its apparatus compares editions and is not an exhaustive manuscript apparatus. [License](https://sblgnt.com/license/), [edition](https://sblgnt.com/) |
| **Selected MACULA and STEPBible data** | Linguistic annotations, glosses, and numbering mappings | Use fields whose upstream permissions are clear; exclude third-party semantic fields until their grant is established. [MACULA Greek](https://github.com/Clear-Bible/macula-greek), [STEP data](https://github.com/STEPBible/STEPBible-Data) |
| **World English Bible** | English navigation and a readable parallel text | Public domain. Treat it as its own translation and textual tradition; do not present it as an exact English rendering of SBLGNT. [WEB](https://ebible.org/web/) |
| **VarApp** | Seed records for selected NT variants and witnesses | CrossWire lists CC0. Check its older records against further evidence and preserve underlying text attribution, including SBLGNT. Linked third-party commentary is separate. [CrossWire module](https://www.crosswire.org/sword/modules/ModInfo.jsp?modName=VarApp) |
| **CNTR manuscript transcriptions** | Selected early Greek witness readings | CC BY-SA 4.0; preserve corrections and damage markers. Distinguish transcriptions from CNTR's own reconstructed edition. [Transcriptions](https://github.com/Center-for-New-Testament-Restoration/transcriptions) |
| **Original research notes and selected licensed scholarship** | Historical context and competing arguments | Author concise cited notes; import third-party prose only when permitted. Check permissions per work and edition. |

For historical context, assemble a small collection of original notes addressing the period, political setting, literary setting, and relevant Jewish and Greco-Roman evidence for each pilot passage. Use independently identified scholarly sources with different perspectives when a question is contested. Public-domain older scholarship can be useful but should not be presented as the current state of research.

Selected Perseus texts can provide ancient comparanda after checking their individual licenses and editions. A public website displaying a modern translation does not automatically authorize copying it into this app. Likewise, manuscript images should initially be external links unless redistribution rights are clear. [Perseus texts and licensing](https://github.com/PerseusDL/canonical-greekLit)

Keep **BHSA/ETCBC data and ETCBC Dead Sea Scrolls data out of the commercial-ready default corpus** because their data licenses are noncommercial. Do not assume NA/UBS/BHS/BHQ apparatuses, BDAG/HALOT, or manuscript photographs are reusable because the underlying ancient words are old. The source research documents the relevant distinctions and possible later permission paths.

This research did not establish a comprehensive commercially reusable apparatus covering the Hebrew Bible, Dead Sea Scrolls, and Septuagint. The first Hebrew case studies therefore require individually checked evidence, permissions, and explicit coverage limits; the base Hebrew text alone cannot supply this history.

Use CNTR's share-alike material as an attributed, separately maintained source collection. Preserve redistribution obligations for adaptations. Keep it out of the first training dataset until the intended derived-data and model-distribution treatment is resolved; the initial training examples can use owned explanations and clearly permissioned evidence instead. This is a simplifying project choice, not a claim that share-alike automatically licenses the entire app or determines the status of model weights.

For each disputed passage, create a reviewed **evidence dossier**: passage identifier; variant readings; witnesses; manuscript dates or ranges with sources; first hand versus correction; attested omission versus missing evidence; edition choices; scholarly arguments; uncertainty; and bibliographic links. Start with 15–25 dossiers. A checked small collection is achievable; comprehensive coverage of all biblical textual history is a much larger project.

## 5. Keep the software simple and the evidence structured

Use **Next.js on Vercel, Supabase Postgres/Auth, and a managed model API**. Your existing stack fits. Run source ingestion and experiments from the development machine initially. Add Railway only when a persistent background worker becomes useful.

```mermaid
flowchart LR
  Q[English question] --> H[App coordinates lookup]
  H --> D[Texts, words, witnesses and historical notes]
  D --> E[Selected evidence with source IDs]
  E --> M[Replaceable model API]
  M --> V[Citation and quotation checks]
  V --> A[English answer with inspectable evidence]
```

The database should keep these separate: works/editions; passage text; word tokens and annotations; verse mappings; manuscripts and transcription coverage; variant readings and attestations; historical notes and bibliographic sources; and evaluation results. A single table of anonymous text chunks would make it too easy to mix witnesses, dates, or editions.

Route explicit verse references directly to database records. Route word studies through lemma/morphology indexes. Route textual-history questions to variant dossiers plus witnesses. For broader questions, search English translations, glosses, and context notes, then retrieve linked original-language passages. Preserve paragraph context around matched verses.

Start with exact lookup and keyword search. Add semantic search when the development questions demonstrate a benefit. Supabase supports combining text search with pgvector, so a separate vector service is unnecessary. Its built-in text-ranking example is PostgreSQL full-text search, not BM25. [Supabase hybrid-search guide](https://supabase.com/docs/guides/ai/hybrid-search)

If adding embeddings, index a compact English search representation linked to the source records. Test retrieval quality on the pilot before embedding the full multilingual library. A small hosted English embedding service is sufficient to test this design; ancient-language embeddings should be a separate comparison. Keep the embedding provider replaceable. Source labels and metadata should come from the records, not from an unchecked model-generated reconstruction.

Preserve exact original Unicode text for display and quotations, and maintain separate normalized search fields. Handle Hebrew directionality, accents, vowel marks, Greek diacritics, token alignment, and numbering differences explicitly. Do not silently remove meaningful marks from displayed evidence.

Give the model only a bounded evidence packet, and require references to IDs in that packet. The app resolves those IDs into real links and exact quoted spans. Check that cited records were supplied and that quoted words match. Human evaluation must still check whether the cited evidence actually supports the explanation.

For a public pilot, use sign-in, server-held API keys, per-user quotas, bounded context/output/retries, and a shared spending counter. Corpus text must never be interpreted as system instructions. Keep user research history private by default. Log enough version, evidence, cost, and latency data to reproduce failures without keeping unnecessary personal information.

## 6. What it should cost to run

At current Groq pricing, **gpt-oss-120b costs $0.15 per million input tokens and $0.60 per million output tokens**. The table assumes one call per question with 6,000 billed input tokens and 1,000 total billed output tokens, including any reasoning. [Groq model catalog](https://console.groq.com/docs/models)

| Monthly questions | Inference only | Practical budget with free app/database tiers |
|---|---:|---:|
| 500 | $0.75 | $5–10 |
| 3,000 | $4.50 | $10–20 |

These practical budgets leave room for additional tokens and small evaluations; they are estimates, not fixed bills. If output grows to 4,000 billed tokens, the inference figures become $1.65 and $9.90. Extra verification calls, long history, retries, embeddings, and changed prices add cost. Measure the chosen model's actual token usage for Greek and Hebrew.

Vercel Hobby is restricted to personal noncommercial use. A public personal pilot can still qualify; a commercial app needs an appropriate plan. Supabase Free has a 500 MB database ceiling, can pause after inactivity, and lacks automatic backups. Several text editions, morphology, and vector indexes may exceed that ceiling. Keep snapshots and measure space. [Vercel Hobby](https://vercel.com/docs/plans/hobby), [Supabase pricing](https://supabase.com/pricing)

If paying for both **Vercel Pro and Supabase Pro**, the base is approximately **$45/month before inference**, with additional usage possible. Budget roughly $50–65 for a small paid-stack pilot under these assumptions. Railway Hobby is a $5 minimum including $5 usage when a worker is needed; it is optional. [Vercel pricing](https://vercel.com/pricing), [Railway pricing](https://railway.com/pricing)

Owning open weights does not require operating a private GPU. A modest always-on GPU at $0.27/hour is already about $197/month before storage. Scale-to-zero GPU hosting can be cheaper, but model loading and idle time are billable, and first requests can be slow. [Runpod pricing](https://www.runpod.io/pricing), [billing mechanics](https://docs.runpod.io/serverless/pricing)

The hardware scenario used in this plan assumes an **8 GiB development computer**. It is useful for building this app and preparing sources. It is a poor fit for the main 20B+ model shortlist; a smaller quantized model would be a separate learning experiment. Do not buy hardware within this budget.

A U.S. model developer, U.S. service company, and guaranteed U.S. processing are separate choices. Because origin is a preference here, select providers on measured quality, cost, and appropriate data terms. If residency becomes a firm requirement, verify the exact endpoint and region rather than infer it from headquarters.

## 7. A bounded Tinker experiment

Tinker supplies managed LoRA training infrastructure. The first experiment should use **gpt-oss-20b or gpt-oss-120b**, with the same source packets used in the app. LoRA produces an adapter that still depends on its base model. It is not a complete model that runs in a Vercel function. [Tinker overview](https://tinker-docs.thinkingmachines.ai/)

For illustration, 1,000 examples averaging 2,000 fully rendered tokens, processed for three epochs, means 6 million training tokens. At current **32K default-context** Tinker rates, forward/backward compute is about **$2.38 for gpt-oss-20b or $4.42 for gpt-oss-120b**. Pin those offerings: the separate 128K gpt-oss-120b offering costs more. Additional validation, example generation, sampling, and storage are separate. Do not add a second inference-prefill fee for the same training operation. Count actual tokens in a tiny calibration run before extrapolating. [Tinker pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/)

Begin with 100–300 reviewed examples; the larger calculation above illustrates costs rather than prescribing a dataset size. Train citation behavior, interpretation of supplied annotations, uncertainty, and evidence-aware explanations. Include conflicting sources and missing evidence. A first attempt of one to three epochs is a testable starting point, not a known optimum. Avoid reinforcement learning until supervised learning and evaluation are working.

Tinker's checkpoint inference API is beta and aimed at evaluation and low internal traffic. It can serve a private experiment, but should not be assumed to be a dependable public production service. [Checkpoint API](https://tinker-docs.thinkingmachines.ai/tinker/compatible-apis/openai/)

Before investing heavily, prove a tiny **train → export → load → compare** cycle with the exact base revision and intended serving software. Save the source data, adapter, tokenizer, model template, and versions. Use the model-specific training renderer and channel format. Loading a 20B+ model for this check requires temporary remote compute on the assumed 8 GiB development computer; include that in the experiment cap. [Tinker adapter export](https://tinker-docs.thinkingmachines.ai/tutorials/deployment/lora-adapter/)

The reviewed Together and Fireworks documentation directs custom models toward dedicated deployments; Groq LoRA requires enterprise access. A cheap shared base-model API does not establish a cheap private-adapter endpoint. Keep the untuned model plus retrieval as a production fallback, and adopt a trained adapter publicly only after verifying its full serving cost. Details and provider-specific evidence are in the [hosting research](hosting-research.md).

## 8. Spend in stages and use evidence to decide what comes next

| Stage | Deliverable and exit condition | Proposed cash cap |
|---|---|---:|
| 1. Scope and evidence sample | Pilot passages, source manifest, five checked dossiers, and 30 development questions | $0–10 |
| 2. Model comparison | Three candidates tested with identical evidence; errors classified | $10–20 |
| 3. Working private assistant | Lookup, English answers, exact quotations, source links, usage caps | $10–20 |
| 4. Evaluation and source review | 100 reviewed questions, including a held-back comparison set; 15–25 dossiers | $0–50 reserved, plus human time |
| 5. Optional training experiment | Tiny calibration, LoRA, exported checkpoint, comparison, serving decision | $10–30 |
| 6. Hosting and contingency reserve | Initial operating room and any necessary paid-tier transition | Remaining budget, up to $70 |

These caps can total $200 at their upper bounds. They are not a suggestion to spend the full amount. A useful first milestone should be reachable with **$20–50 of services** and your development/research time. The source-review allocation buys only a limited contribution if paid help is available; it does not promise a scholar-reviewed corpus for $50.

Assuming hands-on development assistance, allow roughly **two to four weeks of part-time work for a narrow prototype**, with source review potentially taking longer. This is a planning estimate. Do not tie a public launch to the calendar before the evidence is ready.

Proposed first scope: **Mark, plus selected Hebrew Bible case studies**. Build exact text lookup broadly if easy, but claim researched historical coverage only for reviewed dossiers. Start with five examples that demonstrate the full path, including a manuscript dispute, a linguistic ambiguity, a historical-context question, and an answer the library cannot yet support. Expand to 15–25 before an invite-only pilot.

The [evaluation plan](evaluation-plan.md) contains 30 seed questions and a proposed 100-question protocol. Compare the same model without evidence, with manually selected evidence, with automatic retrieval, and after fine-tuning. This tells us whether the next dollar should go to sources, search, a stronger model, or training.

Release targets should include all quotation/source IDs resolving correctly, strong claim-level support on reviewed samples, and no critical invented witness details in the pilot test. Passing a small test does not guarantee correctness outside that sample. Have contested dossiers reviewed by a qualified reader, or keep the public claims correspondingly limited.

If retrieval already produces satisfactory results, keep the base model. If correct evidence is retrieved but the same behavioral failures recur, test fine-tuning. If the model misreads well-prepared evidence, test a stronger model and narrower task. If the needed source is missing, no prompt or adapter can make the app substantiate it.

## 9. The first concrete milestone

Build a private demonstration that answers **30 historical research questions**, shows the original-language text and its edition, opens the evidence behind each claim, and stays within a small measured API budget. Use **gpt-oss-120b as the baseline**, compare **Muse Glimmer and Nemotron Lightning**, and retain the model choice as provisional until that comparison is complete.

For the public product, the strongest identity is an **evidence-based guide to biblical textual history**: an English interface to inspectable scholarship, with original languages and manuscript records available when they matter. A successfully trained adapter can improve that product, but the evidence and evaluation method should carry its authority.

Further research and implementation checks are recorded in [biblical sources](source-research.md), [models and training](model-research.md), and [hosting and recurring costs](hosting-research.md).
