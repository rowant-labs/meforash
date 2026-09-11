# Model comparison before adaptation

A later [24-question large-model comparison](LARGE-MODEL-COMPARISON.md) retains Inkling as the first adaptation candidate and identifies Kimi K2.6 as the closest challenger. The earlier experiment below is preserved with its original results and settings.

Experiment date: September 5, 2026 (local date; journals use UTC). The purpose is to choose a credible starting model for the whole-corpus training experiment by comparing actual English answers about Hebrew, Aramaic, Greek, and life application. No model is trained during this comparison.

**Provisional recommendation: use full Inkling for the first controlled original-language adaptation experiment, with Inkling-Small as the cheaper and faster comparison.** Full Inkling gave the strongest basic-language answers in this small diagnostic sample and materially improved the difficult Daniel 3:18 translation. Its application answers were useful and generally restrained. Inkling-Small was close overall and sometimes preferable for practical reflection.

This is an experimental model choice. All five tested models still failed the central finite-verb analysis in Daniel 2:20. Full Inkling also misattributed English translation wording and silently substituted a different Hebrew/Aramaic reading in another answer. These observations establish neither scholarly competence nor improvement from training.

| Model | Complete final answers | Incomplete | Estimated token cost | Median request time |
|---|---:|---:|---:|---:|
| Full Inkling | 16/16 | 0 | $0.036855 | 8.0 seconds |
| Inkling-Small | 16/16 | 0 | $0.011226 | 4.9 seconds |
| Qwen3.8-27B | 16/16 | 0 | $0.148572 | 22.9 seconds |
| Nemotron Lightning | 14/16 | 2 | $0.020473 | 73.3 seconds |
| gpt-oss-120b (reused) | 16/16 | 0 | $0.016118 | 18.3 seconds |

The **64 new requests cost an estimated $0.21712640**, approximately 22 cents. The reused 16-question baseline adds no new charge; including its historical token estimate gives $0.23324483 for the 80 compared observations. No new request timed out or had uncertain accounting. NVIDIA A02 and A05 hit their generation limits; A05 returned no final answer. All local processes have stopped. These are token-price estimates, not reconciled provider invoices.

The [machine-readable results](../reports/model-comparison-v1.json) retain source hashes, counts, settings, tokens, and cost estimates. Completion means a final answer was delivered, not that it was correct. Request times include local setup, tokenization, queueing, and generation; differing reasoning modes, answer lengths, and service conditions prevent treating them as controlled model-speed benchmarks.

## Findings that drive the choice

Reviewers received constructed case IDs, source excerpts, and final answers under masked candidate labels. Model names and costs were withheld from their answer packets. These were source-checked AI reviews, not qualified scholarly adjudication or a formally validated blind study. Each of the nine language cases and seven application/general cases was examined. Incomplete answers remain incomplete rather than receiving credit for an inferred continuation.

| Model | Findings in this diagnostic sample | Implication |
|---|---|---|
| **Full Inkling** | Sound basic Hebrew/Greek answers; correctly rendered Daniel 3:18's “But if not, let it be known,” where the other complete alternatives mishandled the conditional. Useful, restrained application. Still misparsed Daniel 2:20, misquoted translation versions, and silently substituted singular qere for the supplied plural ketiv in Daniel 3:18. | Best provisional language candidate; first adaptation experiment, with explicit remaining failure cases. |
| **Inkling-Small** | Focused basic Hebrew/Greek explanations and often the strongest everyday reflection. Preserved agency and distinguished forgiveness from restored trust. Aramaic remained weak, including the Daniel 3:18 conditional; its manuscript definition also confused manuscripts with authors' originals. | Strong cost/speed comparison and a useful alternative if further evaluation narrows the quality difference. |
| **Qwen3.8-27B** | Improved over the original baseline, with a sound manuscript definition and some useful nuance. Added false LXX wording, misidentified Greek case, and made unsupported claims about translation and suffering/forgiveness passages. | Its smaller total-weight footprint is appealing, but source reliability did not win this comparison. |
| **Nemotron Lightning** | Some sound translations and basic parsing, but verbose answers introduced false textual variants and grammatical claims. Two language answers hit the output limit, one without a final answer. | The inexpensive rate and smaller model do not compensate for the observed reliability and completion problems at these settings. |
| **gpt-oss-120b** | Reused baseline answers showed extensive invented wording, false grammatical explanations, and unsupported citations despite fluent English. | Retain as the original baseline; it is not the selected next training candidate. |

Three concrete source checks are especially relevant to the experiment:

- **Daniel 2:20:** the pinned annotation for **לֶהֱוֵא** is `AVqi3ms`, an Aramaic Peal imperfect, third-person masculine singular. Its benedictory context supports jussive force. None of the five candidates supplied that central finite-verb analysis correctly; identifying the blessing's general meaning does not repair an invented infinitive or particle analysis. [Pinned Daniel](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Dan.xml), [OSHB morphology](https://hb.openscriptures.org/parsing/HebrewMorphologyCodes.html)
- **Daniel 3:18:** full Inkling correctly preserved the countercondition followed by the declaration. It still rendered “your god” without acknowledging that the supplied **ketiv** is plural, while the separately preserved **qere** is singular. This is fidelity to a chosen source layer, not a claim that one reading is universally correct. [Pinned Daniel with both readings](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Dan.xml)
- **Daniel 3:17:** full Inkling recognized the actual Aramaic condition, but its English-version comparison was wrong. ESV begins “If this be so”; NIV retains an explicit condition about being thrown into the furnace. Claims that NIV drops the condition and the attributed ESV wording were unsupported. [ESV](https://www.esv.org/Daniel+3:17/), [NIV](https://www.biblegateway.com/passage/?search=Daniel+3:17&version=NIV)

For everyday questions, both Inkling models were more restrained than the original baseline. Full Inkling offered especially useful job-change reflection; Inkling-Small more clearly separated forgiveness from restored trust and reconciliation. Both still need better source definitions and careful handling of the full range of biblical explanations of suffering. Reassuring language must not erase difficult wording: for example, Matthew 18:34–35 contains punishment and a warning, whatever interpretation is adopted. [Pinned Matthew](https://raw.githubusercontent.com/Faithlife/SBLGNT/c4d241a9c1c479a55b989ba35a4976c1d0b8052c/data/sblgnt/text/Matthew.txt)

## Next experimental step and hosting limit

Retokenize the unchanged full source corpus for the selected Inkling tokenizer, validate the prepared sequences, and measure a small billing/training calibration before one development-corpus pass. Repeat the frozen English questions afterward and check for regressions as well as improvements. Raw-text exposure remains the first adaptation arm; it has not yet been shown to fix grammar explanations or citation fabrication. Later checked translation/instruction training remains a separate comparison.

Full Inkling's observed quality advantage warrants a research experiment within the initial compute budget. Its 975B total parameters make independent hosting a poor fit for this project's small recurring budget; even Inkling-Small has 276B total parameters. Tinker checkpoint inference remains the private experimental path. Affordable, stable public service for the exact custom adapter is still unproven and must be tested before committing to a public deployment architecture. [Tinker checkpoint inference](https://tinker-docs.thinkingmachines.ai/tinker/compatible-apis/openai/)

## Models and selection

| Candidate | Reason to include | Native sampling input/output per million tokens |
|---|---|---:|
| NVIDIA Nemotron 3.5 Lightning 30B-A3B | Inexpensive U.S. candidate with a smaller total-weight footprint | $0.195 / $0.495 |
| Thinking Machines Inkling-Small | U.S. generalist from the training provider; 276B total parameters make independent hosting harder than its name suggests | $0.58 / $1.44 |
| Qwen3.8-27B | A current alternative to test the task-performance tradeoff of the U.S. preference; 27B dense model | $1.86 / $5.595 |
| Thinking Machines Inkling | Larger U.S. reference added after the first alternatives retained Aramaic errors; 975B total parameters make independent hosting impractical for the initial budget | $1.87 / $4.68 |
| OpenAI gpt-oss-120b | Reused unchanged baseline responses, with no new inference for these cases | $0.33 / $0.84 at the original run's rates |

The [pricing snapshot](../manifests/comparison-pricing.json) records exact Tinker IDs and source hash. NVIDIA and Inkling prices include temporary discounts. These are training-pool sampling rates, not public custom-adapter hosting quotes. [Tinker catalog](https://tinker-docs.thinkingmachines.ai/tinker/models.json)

The NVIDIA model uses OpenMDW-1.1; Qwen and Inkling use Apache-2.0. Model/source rights remain separate from the project code. Publisher model cards describe architectures and intended usage; they do not establish ancient-language accuracy. [NVIDIA](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16), [Inkling](https://huggingface.co/thinkingmachines/Inkling-Small), [Qwen](https://huggingface.co/Qwen/Qwen3.8-27B), [full Inkling](https://huggingface.co/thinkingmachines/Inkling)

## Comparison design

[`evals/comparison-v1.jsonl`](../evals/comparison-v1.jsonl) contains 16 unchanged rows of the original pilot, four per language group: six focused grammar questions, three translations, four life reflections, one passage comparison, one ordinary English instruction question, and one source-boundary question. The [selection manifest](../evals/comparison-v1-manifest.json) records hashes and case IDs.

Selection occurred after seeing the original model's failures. Full Inkling was added as a fourth new candidate after preliminary review found shared Aramaic weaknesses in the initial alternatives; all 16 questions and the low-effort TML settings stayed fixed. This is a diagnostic development comparison, not an unbiased benchmark or final holdout. It deliberately revisits known errors, includes direct translation tasks, and tests broader English usefulness. Answers and evaluation criteria remain excluded from training data.

All models receive the same application instructions and user-question text. The provided-evidence condition adds the same excerpts to nine grammar/translation cases; the remaining seven questions receive no additional excerpt. The original gpt-oss results come from the completed 40-question provided-condition run. A verified subset summary checks that the selected rows are unchanged and reads those original journal events without rewriting them or pretending they are new calls.

All new runs use temperature 0, seed 20260905, a 6,000-token input ceiling, a 4,096-token total generation ceiling, and a 180-second deadline. The old baseline used 120 seconds. Reasoning controls differ by model: Lightning thinking on, Qwen low, Inkling low, and the original gpt-oss low. These are model-specific operating settings, not equivalent reasoning budgets. Tokenizers differ, so equal token ceilings do not equalize language content or computation. Record incomplete answers rather than silently extending only one candidate's limit.

Each model has its own official rendering and parsing path. No analysis text is promoted to an answer. Token accounting includes the entire generated sequence, including reasoning and protocol. The generation profiles follow the pinned [Tinker cookbook metadata](https://github.com/thinking-machines-lab/tinker-cookbook/blob/1f962eda3a2cec8de284725f2adc9978e93dfcd3/tinker_cookbook/model_info.py): `nemotron3_ultra`, `qwen3_8`, and `tml_v0`. Older similarly named renderers are not assumed interchangeable.

NVIDIA and Qwen use pinned official tokenizer/template assets, checked against the SDK's tokenizer and each submitted prompt. Inkling uses the official `tml-renderers==0.1.0` native renderer. Tinker SDK 0.27.1's Inkling tokenizer accessor refers to an unavailable `tml_tokenizers` package, so it is bypassed. The official native Inkling tokenizer was checked against the pinned Hugging Face rank file: all 199,998 ordinary tokens and 60 special tokens match. Native and pinned tokenization are compared for rendered prompts. This is **not a live server tokenizer or weight-revision verification**. See the [asset manifest](../manifests/comparison-models.json) and [official TML documentation](https://tinker-docs.thinkingmachines.ai/cookbook/inkling/tml-renderers/).

The [software snapshot](../manifests/comparison-software.json) records current code and dependency hashes. It is a reproducibility reference, not a claim of an immutable code revision at every launch; the original three-model asset manifest is [preserved separately](../manifests/comparison-models-initial-v1.json). Provider weight revisions remain unpinned for all candidates. Seed and temperature do not guarantee identical service outputs. Answers have no browsing tools or manuscript database in this experiment; exact-citation claims are assessed against that limitation.

## Budget and review

The application budgets are $0.10 for NVIDIA, $0.20 for Inkling-Small, $0.70 for Qwen, and $0.60 for full Inkling: $1.60 total. Reserving the full configured input/output ceiling for every one of the 64 planned new requests totals approximately $1.23 at the recorded rates. Successful exact token counts replace unused reservations. Provider invoices remain unverified; SDK submission retries and remotely accepted work after a local timeout prevent a guaranteed invoice ceiling.

The runner stops on uncertain accounting without automatic retries. Previous gpt-oss comparison timeouts are not retried here. Run artifacts, credentials, and raw answers remain ignored locally; shareable reports contain reviewed observations, hashes, safe settings, and aggregate accounting.

Review compares source fidelity, linguistic claims, English usefulness, uncertainty, quotation/citation support, and the accepted intent-based reflection contract. Preliminary AI source checking is not a qualified scholarly review. No numerical biblical accuracy claim follows from completed responses or software tests. A practical candidate recommendation must preserve uncertainty and consider training and eventual adapter serving separately.

## Reproduce

Use Python 3.11 or later (locally tested with 3.13), with credentials only in the ignored root `.env` or exported environment. Fetching public tokenizer assets and dry runs need no API key.

```sh
.venv/bin/python -m pip install -r requirements-comparison.txt
.venv/bin/python -m bibleprep.fetch_comparison
```

Each command below prepares a dry run. After verifying it locally, add `--execute --resume` to the identical command to dispatch its bounded requests. Run directories are kept separate by model.

```sh
.venv/bin/python -m bibleprep.tinker_compare \
  --model nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16 \
  --dataset evals/comparison-v1.jsonl \
  --input-price-per-million 0.195 --output-price-per-million 0.495 \
  --budget-usd 0.10 --run-dir runs/comparison-nemotron-lightning-v1

.venv/bin/python -m bibleprep.tinker_compare \
  --model thinkingmachines/Inkling-Small \
  --dataset evals/comparison-v1.jsonl \
  --input-price-per-million 0.58 --output-price-per-million 1.44 \
  --budget-usd 0.20 --run-dir runs/comparison-inkling-small-v1

.venv/bin/python -m bibleprep.tinker_compare \
  --model Qwen/Qwen3.8-27B \
  --dataset evals/comparison-v1.jsonl \
  --input-price-per-million 1.86 --output-price-per-million 5.595 \
  --budget-usd 0.70 --run-dir runs/comparison-qwen38-27b-v1

.venv/bin/python -m bibleprep.tinker_compare \
  --model thinkingmachines/Inkling \
  --dataset evals/comparison-v1.jsonl \
  --input-price-per-million 1.87 --output-price-per-million 4.68 \
  --budget-usd 0.60 --run-dir runs/comparison-inkling-v1
```

The exact installed comparison dependencies are recorded in [requirements-comparison.lock.txt](../requirements-comparison.lock.txt). To compare the same 16 observations without rewriting the older baseline:

```sh
.venv/bin/python -m bibleprep.summarize_evaluation \
  runs/tinker-baseline-120b-provided-v1 \
  runs/comparison-nemotron-lightning-v1 \
  runs/comparison-inkling-small-v1 \
  runs/comparison-qwen38-27b-v1 \
  runs/comparison-inkling-v1 \
  --subset-dataset evals/comparison-v1.jsonl \
  --output reports/model-comparison-v1.json
```

The aggregate distinguishes the original selected-case count from the filtered comparison count and hashes the untouched source journals.

All source editions and original prepared training files remain unchanged. Changing the base model will require retokenizing the full original-language corpus with that model's tokenizer before training; the existing gpt-oss token counts cannot be reused as exact forecasts.
