# Large model comparison before adaptation

Experiment dates: September 5–6, 2026 local time; event journals use UTC. The design, question set, prospective review notes, and software snapshot were frozen before sampling. All three runs are now finished; no training occurred.

**Recommendation: keep full Inkling as the first adaptation candidate, and retain Kimi K2.6 as the closest challenger. No additional broad model-size comparison is needed before the training experiment.** Inkling offers the strongest practical balance in this run: all answers completed, the strongest earlier language group, competitive fresh-language performance, lower sampling cost, and the project's U.S.-developer preference. Kimi is often better on individual fresh and application questions, but does not provide a clean overall replacement; two difficult Aramaic questions remained incomplete. This is a choice for the next experiment, not a claim of universal superiority or demonstrated benefit from training.

The earlier [five-model screen](MODEL-COMPARISON.md) provisionally favored full Inkling, but included only one model at approximately a trillion total parameters. This final comparison tests two other large families before choosing the base for the original-language adaptation experiment. It does not assume that parameter count establishes biblical competence. No training occurs in this experiment.

## Measured results

| Model | Complete final answers | Incomplete | Estimated token cost | Median request time |
|---|---:|---:|---:|---:|
| Full Inkling, medium reasoning | 24/24 | 0 | $0.179676 | 21.8 seconds |
| NVIDIA Nemotron Ultra 550B, thinking on | 24/24 | 0 | $0.254640 | 22.5 seconds |
| Kimi K2.6, thinking on | 22/24 | 2 | $0.524357 | 62.8 seconds |

The **72 requests cost an estimated $0.95867225**, approximately 96 cents, versus a $4.50 combined application budget. All requests returned; none timed out or ended with an accounting error. Kimi's A02 (Daniel 3:17) and A15 (Daniel 6:11, supplied MT numbering) reached the 8,192-token output limit. A02 returned a partial final answer; A15 returned no final answer. Both remain incomplete, and neither was selectively repeated with a larger allowance. All sampling processes have stopped.

The [aggregate report](../reports/model-comparison-large-v1.json) records 25,965 input tokens and 164,413 generated tokens, including reasoning and protocol. It contains no answer text, credentials, or personal account identifiers. The 72 observations concern 24 unique questions. “Complete” means a final answer was delivered, not that it was historically or linguistically correct. Token estimates have not been reconciled to a provider invoice.

Request times include local setup, queueing, reasoning, and generation. Kimi was slower in this Tinker experiment; these figures do not establish comparative speed under other providers, settings, or production hosting. The output limits are identical token counts, not equal amounts of computation or language content.

## Source-checked findings

The earlier-language reviewer preferred **Inkling, then Kimi, then Nemotron Ultra** on the nine retained language cases. The application reviewer leaned **Kimi, then Inkling, then Nemotron Ultra** on the seven general/application cases. These are qualitative judgments from source checks, not numerical scores. The fresh-language reviewer narrowly preferred Kimi over Inkling on the completed explanations, while treating their overall ordering as close and sensitive to Kimi’s missing answer. Both were ahead of Ultra. These group preferences do not establish one unambiguous model-wide accuracy ranking.

| Candidate | Findings that matter to this project |
|---|---|
| **Full Inkling** | Strongest practical starting point. Correctly preserved the supplied plural ketiv in Daniel 3:18 and completed every question. It still offered a spurious infinitive alternative in Daniel 2:20, misidentified forms in Daniel 6:11, and added unsolicited reflections to several focused textual questions. Its forgiveness answer invented a protective-distance interpretation of Joseph settling his family in Goshen. |
| **Kimi K2.6** | Closest challenger. Especially good on the fresh Hebrew agency/context questions, John 1:1, manuscript/edition definitions, and several reflections. It nevertheless replaced the supplied Daniel 3:18 plural ketiv with singular qere while misdescribing the evidence. Daniel 3:17 was partial and Daniel 6:11 had no final answer. Its forgiveness answer invented a Greek word in Luke 17:3–4. |
| **Nemotron Ultra** | Many core translations were correct, but additional explanation introduced the most conspicuous concentration of source and grammar errors: a singular Hebrew addressee became a group, a masculine noun was called feminine and explained using an invented agreement exception, and Daniel's kneeling became blessing. Historical-reception tables included false quotations and attributions. The larger NVIDIA tier did not displace the other finalists. |

A few examples make the evaluation criteria concrete:

- **Ruth 2:8 and 1 Samuel 1:13:** OSHB identifies Ruth's **תדבקין** as second-person feminine singular with a paragogic nun. In Hannah's scene, **קולה** consists of a masculine noun, “voice,” with a feminine possessive suffix, “her.” Kimi and Inkling handled the central relationships correctly; Ultra invented a plural addressee and an exceptional passive-agreement explanation. [Pinned Ruth](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Ruth.xml), [pinned 1 Samuel](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/1Sam.xml)
- **Daniel 3:18:** preserving the chosen edition layer matters independently of producing familiar English. Inkling and Ultra retained the supplied plural ketiv, “your gods”; Kimi substituted the separately recorded singular qere. This is an input-fidelity error, not a declaration that the ketiv is always the earliest reading. [Pinned Daniel with both readings](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Dan.xml)
- **Daniel 6:11, supplied MT numbering:** the question asks about kneeling, praying, giving thanks, and continuing an established practice. Inkling's response retained the main scene but misparsed forms; Ultra turned kneeling into blessing; Kimi supplied no final answer. None earns a clean result here. [Pinned Daniel](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Dan.xml)
- **Life application:** reasonable advice cannot be justified with invented textual support. Inkling's claim that Goshen demonstrated protective distance conflicts with Genesis 45:10's explicit proximity to Joseph. Kimi's appeal to Greek *dei* in Luke 17:3–4 cites a word absent from those verses. Both often gave useful reflections, but fluency did not establish their supporting evidence. [Pinned Genesis](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Gen.xml), [pinned Luke](https://raw.githubusercontent.com/Faithlife/SBLGNT/c4d241a9c1c479a55b989ba35a4976c1d0b8052c/data/sblgnt/text/Luke.txt)

Reviewers received final answers under P/Q/R labels, with model identities and prices withheld from their packets. The orchestrator knew the identities for sampling and final integration. One reviewer read project planning documents containing the earlier candidate names and summary findings, but did not see the new label mapping. Reviews were developed as answers arrived; the questions and criteria were already frozen. This is masked AI source checking, not a formally validated blind study or qualified scholarly adjudication. Debatable readings, minor terminology, verified factual errors, and missing answers were kept distinct. Full local review notes remain ignored; this document publishes the selected checked findings and limitations.

## Decision and next experiment

Proceed with Inkling's tokenizer preparation and a small billing/training calibration, followed by the planned original-language-only development pass if the calibration succeeds within its budget. Evaluate that adapter against the unchanged Inkling baseline on the frozen questions, checking regressions as well as improvements. Retain Kimi's results as a serious alternative rather than treating its slower Tinker run as proof of inferior ability or future serving performance. This comparison did not train any model or resolve public custom-adapter hosting.

The [same-16-question Inkling effort summary](../reports/inkling-effort-comparison-v1.json) reuses the earlier low-effort run and this run's medium-effort answers. Both completed all 16; estimated sampling cost rose from $0.036855 to $0.105047 for those questions. It adds no new calls. Reasoning setting and output allowance both changed, and no provider weight revision is exposed, so this is not an isolated causal test of reasoning effort. More reasoning did not establish uniformly reliable scholarship; select application settings through later evaluation rather than assuming the largest allowance is best.

The next useful evidence is whether adaptation improves the chosen base. Raw original-language exposure has not been shown to repair these English grammar explanations, historical attributions, or citation errors. The separate checked instruction-training arm remains part of the project plan; the central raw-text experiment is preserved.

## Frozen design

Compare full Inkling, NVIDIA Nemotron Ultra 550B, and Kimi K2.6 on the same 24 development questions: the 16 unchanged earlier comparison cases plus eight fresh language cases (three Hebrew, three Aramaic, two Greek). New source excerpts and review criteria are prepared before any answers are generated. This broadens the diagnostic evidence; the new questions remain deliberately constructed development cases, not an unbiased benchmark or a final holdout. The earlier model's observed failures informed the subject areas.

All three models receive identical application instructions, English questions, and source excerpts where available. Review criteria and expected findings are never sent as model input. All three are sampled again, including Inkling, to use the expanded question set and larger output allowance. Keep historical runs unchanged; differences from those runs cannot isolate model size or reasoning effort.

Use temperature 0, seed 20260905, a 6,000-token input ceiling, an 8,192-token total generation ceiling, and a 240-second request deadline. Inkling uses medium reasoning; NVIDIA and Kimi use their supported thinking mode. Model-specific reasoning controls are not equivalent computation budgets. Tokenizers differ, and no model is promised sufficient space to complete every answer. Incomplete answers are recorded without selectively increasing a candidate's limit.

Application budgets are $1.70 for NVIDIA, $1.50 for Kimi, and $1.30 for Inkling: **$4.50 combined**. At the verified rates, reserving every request's full configured input/output ceiling totals approximately $4.17. These are local application limits and token estimates, not a guaranteed invoice cap: the SDK can retry internally and a remotely accepted request can finish after a local timeout. The runner stops on uncertain accounting without automatically repeating the request.

Review final answers under masked candidate labels, withholding model names and prices from review packets. Separate the nine earlier language cases, eight new language cases, and seven application/general cases so readers can assess whether a recommendation depends on known failures. Assess faithful translation, grammar, exact quotation, unsupported claims, useful English, calibrated uncertainty, and the project's accepted reflection behavior. Source-checked AI review remains preliminary and is not qualified scholarly adjudication. Do not report completion as accuracy or invent a biblical-accuracy percentage.

## Provenance and operating limits

Pin public tokenizer assets and official rendering formats, check prompt tokenization, and count the whole sampled sequence, including reasoning and protocol. Preserve source editions and training artifacts unchanged. Provider weight revisions are not exposed and remain unpinned. Temperature and seed do not establish exact reproducibility.

Raw answers, operational journals, and credentials remain ignored locally. Publish source references, settings, hashes, aggregate costs and counts, and reviewed findings. Eventual public custom-adapter hosting remains a separate unverified requirement, regardless of which base wins this comparison.

Current official references: [Tinker catalog and pricing](https://tinker-docs.thinkingmachines.ai/tinker/models.json), [Inkling](https://huggingface.co/thinkingmachines/Inkling), [NVIDIA Nemotron Ultra](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16), [Kimi K2.6](https://huggingface.co/moonshotai/Kimi-K2.6).

## Reproduction and local validation

The [experiment settings](../manifests/comparison-large-experiment-v1.json), [dataset manifest](../evals/comparison-large-v1-manifest.json), [prospective review notes](../evals/comparison-large-v1-review-notes.md), [model assets](../manifests/comparison-large-models-v1.json), [pricing snapshot](../manifests/comparison-large-pricing-v1.json), and [pre-launch software hashes](../manifests/comparison-large-software-v1.json) were recorded before sampling. An ignored local copy retains the exact pre-launch source bytes. Earlier experiment files and manifests remain unchanged.

**137 local tests passed** before launch. Additional offline checks rendered all 24 prompts for each model, verified source text preservation and the official message formats, and exercised malformed/truncated response handling. These are implementation checks, not assessments of biblical accuracy.

NVIDIA's pinned tokenizer is checked against the SDK accessor. Inkling uses the official native TML renderer at effort 0.7 and compares it with pinned Hugging Face assets. Kimi uses the official SDK/cookbook-referenced tokenizer revision and its two reviewed, hash-pinned local Python modules. Its vocabulary is read from checked local bytes, bypassing the Tiktoken cache. Checks compare Kimi's local tokenizer interface with its underlying native encoding; they are not an independent tokenizer or live server comparison. Model-visible text and full prompt token counts are checked before sampling; only final text is retained as an answer.

Source and model licenses remain separate from the project's Apache-2.0 code license. Inkling is Apache-2.0, NVIDIA Ultra is OpenMDW-1.1, and Kimi uses a Modified MIT license with an additional attribution condition at its stated large commercial thresholds. The pinned model manifest records the license sources; redistribution requires checking the exact license.

Install the pinned comparison dependencies and fetch the small public tokenizer assets:

```sh
.venv/bin/python -m pip install -r requirements-comparison-large.txt
.venv/bin/python -m bibleprep.fetch_comparison \
  --manifest manifests/comparison-large-models-v1.json
```

The exact installed dependency versions are in [requirements-comparison-large.lock.txt](../requirements-comparison-large.lock.txt). Credentials belong only in the ignored root `.env` or the environment. The commands below prepare dry runs without reading credentials. Add `--execute --resume` to the identical command to perform sampling within its application budget.

```sh
.venv/bin/python -m bibleprep.tinker_compare \
  --model thinkingmachines/Inkling \
  --comparison-manifest manifests/comparison-large-models-v1.json \
  --dataset evals/comparison-large-v1.jsonl \
  --evidence-mode provided \
  --max-cases 24 \
  --max-input-tokens 6000 \
  --max-output-tokens 8192 \
  --timeout-seconds 240 \
  --temperature 0.0 \
  --seed 20260905 \
  --run-dir runs/comparison-large-inkling-v1 \
  --reasoning-effort medium \
  --input-price-per-million 1.87 \
  --output-price-per-million 4.68 \
  --budget-usd 1.3
```

```sh
.venv/bin/python -m bibleprep.tinker_compare \
  --model nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16 \
  --comparison-manifest manifests/comparison-large-models-v1.json \
  --dataset evals/comparison-large-v1.jsonl \
  --evidence-mode provided \
  --max-cases 24 \
  --max-input-tokens 6000 \
  --max-output-tokens 8192 \
  --timeout-seconds 240 \
  --temperature 0.0 \
  --seed 20260905 \
  --run-dir runs/comparison-large-nemotron-ultra-v1 \
  --reasoning-effort on \
  --input-price-per-million 2.49 \
  --output-price-per-million 6.225 \
  --budget-usd 1.7
```

```sh
.venv/bin/python -m bibleprep.tinker_compare \
  --model moonshotai/Kimi-K2.6 \
  --comparison-manifest manifests/comparison-large-models-v1.json \
  --dataset evals/comparison-large-v1.jsonl \
  --evidence-mode provided \
  --max-cases 24 \
  --max-input-tokens 6000 \
  --max-output-tokens 8192 \
  --timeout-seconds 240 \
  --temperature 0.0 \
  --seed 20260905 \
  --run-dir runs/comparison-large-kimi-k26-v1 \
  --reasoning-effort on \
  --input-price-per-million 2.205 \
  --output-price-per-million 5.49 \
  --budget-usd 1.5
```

Summarize the three unchanged journals with the matching 24-case dataset:

```sh
.venv/bin/python -m bibleprep.summarize_evaluation \
  runs/comparison-large-inkling-v1 \
  runs/comparison-large-nemotron-ultra-v1 \
  runs/comparison-large-kimi-k26-v1 \
  --dataset evals/comparison-large-v1.jsonl \
  --output reports/model-comparison-large-v1.json
```
