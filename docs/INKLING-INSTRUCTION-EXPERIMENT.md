# Inkling English instruction experiment

September 6, 2026. Status: both seven-update fine-tunes and the 96-candidate source review are complete. A/B/C each produced 24 complete extracted answers; D produced 21 complete answers and three output-limit answers. The [results and decision](INKLING-INSTRUCTION-RESULTS.md) retain B as the leading experimental checkpoint; the English-training additions did not justify replacing it. The completed code suite has 54 passing focused tests. No selective retries were made.

The first original-text pass improved prediction of the selected ancient texts, while its English answers remained mixed. This experiment tests whether a small set of checked English explanations improves that bridge, and whether the earlier original-text stage contributes after the same English training.

| Arm | Starting point and treatment |
|---|---|
| A | Unchanged Inkling |
| B | Completed original-text adapter |
| C | Fresh Inkling adapter, trained on reviewed English examples |
| D | B's weights, followed by the same English examples as C |

The [frozen protocol](../manifests/instruction-experiment-v1.json) preserves the existing original-text checkpoint as B. D loads its weights into a compatible fresh client with a new optimizer. C and D use identical examples, order, training settings, and evaluation settings. The [original experiment](INKLING-ADAPTATION-RESULTS.md) remains a separate, preserved result.

## Examples and source review

The approved collection contains 120 constructed questions and English answers: 40 Hebrew textual examples, 40 Greek textual examples, 24 Aramaic textual examples, and 16 life-reflection examples. Reflections use relevant Hebrew or Greek passages, so those categories are different from language totals. No user conversations are included.

The [preparation manifest](../manifests/preparation-instruction-v1.json) fixes **104 training examples and 16 validation examples**. Training includes 42 Hebrew, 19 Aramaic, and 43 Greek examples; validation includes five Hebrew, five Aramaic, and six Greek examples. The split uses 89 training and 13 validation chapter families, with known direct quotation/parallel groups kept together. Training processes **64,154 input positions**, scoring **15,554 assistant positions**. Validation has 10,837 input positions and 2,344 scored assistant positions.

Every example has an author and a separate AI source reviewer. Review checks the exact pinned edition, parsing, subject and object, translation scope, historical assertions, and whether application introduces biblical details absent from its sources. A hash binds approval to the actual content; editing it requires review again. This is AI source checking, not human specialist certification.

The textual examples provide exact OSHB/WLC or SBLGNT excerpts. The reflection examples provide no excerpt to the model, but retain source references for review. Targets are newly authored English explanations. Source notes, review metadata, and evaluation criteria are excluded from model inputs and targets.

OSHB and SBLGNT identities remain pinned in their existing manifests. MorphGNT was used privately as a Greek morphology review aid, at revision `aaed91e57c8e4a8dc9a2383e129ca5e75fe6393d`; its annotations retain CC BY-SA 3.0 attribution and obligations. Source texts, annotations, reference works, and model weights are not relabeled with the project's code license. Reviewed/prepared datasets remain private pending a separate release review.

## Separation from evaluation

The fresh evaluation contains 24 questions: seven Hebrew, seven Aramaic, six Greek, and four application cases. Twenty provide excerpts. The questions and criteria were frozen before candidate sampling. The evaluation author did not author the English training targets; training authors received only a minimal chapter-exclusion inventory.

Nineteen chapter families are excluded from both English training and English validation. Source review also checks direct quotations and obvious parallel passages: a draft's Mark 12:31 quotation was removed because it repeated a command in excluded Leviticus 19. Identified direct quotation/parallel groups in the remaining examples are kept on the same training/validation side. Shared themes and unidentified parallels remain possible.

This holds out English supervision. B may have encountered these ancient passages in original-text training, and all arms have unknown pretraining exposure. The small evaluation does not establish performance across the whole Bible or reconstruct unattested originals.

## Training and sampling

C and D use one epoch, rank 8, attention/MLP/unembedding adapters, batch size 16, shuffle seed 20260906, and Adam with learning rate 0.0001, beta1 0.9, beta2 0.95, epsilon 1e-8, no weight decay, and no clipping. This is an experimental generic recipe, not a tuned Inkling optimum. Training scores the assistant response and native turn boundaries while masking the prompt; sequences are shifted once and never truncated.

Native TML rendering and sampling both request thinking effort 0.7. The supervised examples contain final English answers without fabricated reasoning traces. Native rendering canonicalizes that final-only response to the main channel. Its possible effect on analysis emission is an untested hypothesis, not an established cause of D's completion failures. General reasoning retention is not established by this Bible evaluation. [Native renderers](https://tinker-docs.thinkingmachines.ai/cookbook/inkling/tml-renderers/), [thinking effort](https://tinker-docs.thinkingmachines.ai/cookbook/inkling/thinking-effort/), [weights-only loading](https://tinker-docs.thinkingmachines.ai/tinker/api-reference/trainingclient/#load_state).

All four arms use the frozen system prompt, temperature 0, seed 20260905, an 8,192-token output ceiling, a 6,000-token input ceiling, and a 300-second request deadline. Adapter sampling explicitly uses the corresponding checkpoint. Receipts and hashes prevent silently substituting a base model or another adapter. Earlier repeats differed despite matching requested settings; provider base weights are unpinned and the run is not guaranteed deterministic.

The two new training runs estimate **$0.96299016 in compute plus $6 in checkpoint/storage contingency**, for a **$6.96299016 combined reservation**. They have a $15 combined estimate cap within the existing $50 shared training reservation. Each includes $3 of checkpoint/storage contingency. Sampling has an explicit $1.19 per-arm cap at the recorded rates. These are local conservative budget controls, not a reconciled invoice or a guaranteed provider spending limit. Checkpoints have 30-day retention.

## Reproduction

The native runtime is pinned in `requirements-training.txt`. Source acquisition remains documented in [preparation readiness](PRETRAINING-READINESS.md). The reviewed English dataset is not yet a public distribution artifact; hashes and procedures alone do not make this experiment fully reproducible from a public checkout.

`bibleprep.prepare_instruction` verifies sources, separate reviews, evaluation exclusions, chapter splits, native rendering, masking, and counts locally. Its frozen manifest is required by `bibleprep.train_instruction`. Planning C or D loads no credentials and submits no API operations:

```sh
python -m bibleprep.train_instruction --arm C
python -m bibleprep.train_instruction --arm D
```

Paid training requires `--execute` and a fresh private run directory. `bibleprep.evaluate_instruction` similarly requires the frozen dataset, an explicit arm, a matching checkpoint for B/C/D, prices, budget, and `--execute` for live sampling. Runners stop after uncertain operations and do not retry automatically.

The source/preparation/training/evaluation code passed 43 focused tests before C/D execution, and a separate metadata audit confirmed all 120 review hashes and the 104/16 split. No source or token truncation was permitted.

## Measured training and sampling

| Fine-tune | Validation NLL before | Validation NLL after | Relative reduction |
|---|---:|---:|---:|
| C: English instructions | 2.51530 | 1.93125 | 23.2% |
| D: original text, then English instructions | 2.19882 | 1.45623 | 33.8% |

Both use the identical 16-example validation set and 2,344 scored assistant positions. Loss fell in all three language groups. These figures measure prediction of the reviewed English targets, including native assistant framing. They cannot be compared directly with the earlier ancient-text loss, and they are not translation-accuracy percentages.

| Evaluation arm | Complete answers | Output-limit answers | Generated tokens | Median request time | Estimated sampling cost |
|---|---:|---:|---:|---:|---:|
| A | 24/24 | 0 | 41,056 | 34.0s | $0.21077 |
| B | 24/24 | 0 | 26,463 | 29.5s | $0.14248 |
| C | 24/24 | 0 | 44,268 | 46.6s | $0.22581 |
| D | 21/24 | 3 | 27,952 | 6.0s | $0.14945 |

All 96 requests returned with usage records; there were no transport errors or uncertain requests. D's incomplete answers include one Hebrew and two Aramaic cases. Every returned prompt hash matches its counterparts across arms. Incomplete answers remain in the comparison, with their available extracted text and finish status. The three output-limit cases have no retained final text. The current extractor returns completed native messages and the raw generated token IDs were hashed rather than saved. A synthetic official-parser check confirms that unfinished final text or unfinished thinking can both yield an empty retained final string. Actual repetition, reasoning-only generation, and the contents of any unfinished answer cannot be reconstructed. This limits diagnosis; it does not erase the observed failure to finish within 8,192 tokens.

Generated-token totals include native framing and any reasoning. The current native transport does not supply a reliable analysis/final token split; unavailable values are recorded as null. D's shorter median and incomplete outputs require answer-level inspection and do not establish a serving speed advantage or improved reasoning.

The incremental estimate is **$1.69149192 in compute and sampling**, plus **$6 checkpoint/storage contingency**, totaling **$7.69149192**. This covers C/D training and all four contemporary evaluations; it excludes previously incurred original-text training and earlier model comparisons. It is not an invoice.

The [machine-readable aggregate](../reports/inkling-instruction-v1.json) verifies dataset, prompts, checkpoints, and matched C/D recipes. The [completed answer review](../reports/inkling-instruction-answer-review-v1.json) records all 24 four-arm rankings and source corrections. B was preferred over A on 11 questions, A over B on four, with nine ties. C versus A was nearly even (8/7/9). D's lower loss did not translate into a preferred checkpoint. Read the [results report](INKLING-INSTRUCTION-RESULTS.md) for review limitations, the distinction between native noncompletion and missing requested content, and the next proposed experiment.
