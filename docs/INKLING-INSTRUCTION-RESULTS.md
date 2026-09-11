# English instruction fine-tuning: results

September 6, 2026. **The original-text-only adapter remains the leading experimental checkpoint.** It was preferred over unchanged Inkling on 11 questions, less preferred on four, and tied on nine in this new 24-question review. English instruction training alone showed no clear advantage, and adding it after original-text training reduced completion and requested coverage. These are small, source-checked observations, not a demonstrated whole-Bible accuracy gain.

Both new fine-tunes completed seven updates on the same 104 reviewed English examples, with 16 examples reserved for validation. All 96 evaluation requests returned; 93 produced complete extracted answers. All answers were reviewed, including the three output-limit failures. There were no selective retries.

The [methods report](INKLING-INSTRUCTION-EXPERIMENT.md) documents the frozen data, native formatting, matched recipes, costs, and reproduction limits. The [operational aggregate](../reports/inkling-instruction-v1.json) and [complete source-review record](../reports/inkling-instruction-answer-review-v1.json) preserve measurements, every case's preference, corrections, and provenance hashes.

## Four approaches compared

| Arm | Treatment | Complete extracted answers |
|---|---|---:|
| A | Unchanged Inkling | 24/24 |
| B | Original-language text training only | 24/24 |
| C | English instruction training only | 24/24 |
| D | Original-language text, then the same English instruction training | 21/24 |

Reviewers ranked source fidelity and requested coverage first, then useful scope and clarity. Ties were allowed. A preference can reflect an omitted translation or unnecessary commentary; it is not necessarily a difference in factual correctness.

| Comparison | First arm preferred | Second arm preferred | Tied |
|---|---:|---:|---:|
| B versus A | 11 | 4 | 9 |
| C versus A | 8 | 7 | 9 |
| D versus A | 7 | 12 | 5 |
| B versus C | 12 | 4 | 8 |
| B versus D | 12 | 3 | 9 |
| C versus D | 10 | 9 | 5 |

Every row includes all 24 questions. B leads its comparisons with A, C, and D in this sample. C's near-even comparison with A does not justify replacing the original-text checkpoint. D has useful individual answers but is unsuitable for promotion with this recipe.

As a descriptive check, excluding D's three output-limit cases still leaves B preferred on nine questions, D on three, and nine ties among the remaining 21. The full 24-question result remains primary. B's Aramaic comparison with A is mostly ties (one preference for B, none for A, six ties), so its overall lead must not be described as broad Aramaic improvement.

## What changed in the answers

**B often preserved the requested source details and stayed focused.** Its Deuteronomy 24 answer retained both worker groups and the payment rule. C's quoted translation confused the relationship between withholding wages, the worker's appeal, and guilt; its later explanation corrected the sense but left an internal contradiction. D omitted important parts of the requested verse. B also led the Jonah 4 comparison, where C incorrectly attributed God's concern about Nineveh to Jonah's perspective. These are observed differences in these outputs, not proof of permanent training effects. See IH03 and IH07 in the [case review](../reports/inkling-instruction-answer-review-v1.json), with [pinned Deuteronomy](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Deut.xml) and [Jonah](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Jonah.xml).

**B still makes concrete errors.** In Isaiah 6:8 it inferred multiple actors from the plural “for us,” which does not itself establish multiple agents in the sending action. In 1 Corinthians 13 it substituted a different Greek conjunction while explaining the supplied wording. In James 2 it grouped a participle with subjunctive verbs. Relative preference is compatible with these mistakes; B is a candidate to improve, not an authoritative interpreter. See IH05, IG05, and IG06 in the [review record](../reports/inkling-instruction-answer-review-v1.json).

**Aramaic needs targeted attention across the models.** All three retained Daniel 5:5 answers mislabeled the qere as singular; the pinned annotation identifies a feminine plural form. D did not finish an extracted answer for that question. Correctly narrating the scene did not establish correct analysis of its written/read forms. The review also allowed defensible stem terminology and did not treat a known annotation inconsistency elsewhere in Daniel as unquestionable ground truth. See IA01 and the reviewer caveats in the [case record](../reports/inkling-instruction-answer-review-v1.json), [pinned Daniel](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Dan.xml).

**English training had some useful individual outcomes.** C led the Matthew 5 reconciliation and James 2 translation questions. D gave a direct, gentle Psalm 42 reflection and tied for first on the Micah 6 application question. Its concise style can fit a personal reflection while omitting necessary content in a translation task. Four application cases are too few to establish a reliable general preference.

**D's six incomplete assessments describe two different problems.** Three generations hit the 8,192-token limit: IH07, IA01, and IA04. Another three finished normally but omitted a requested translation or explanation: IG01, IG02, and IG06. The first is a generation-completion problem; the second is missing task coverage. Other localized omissions remain in the detailed notes, so this is not a comprehensive count of every coverage defect.

The three output-limit records contain no retained final text. The native extractor retains completed messages, and generated token IDs were hashed rather than saved. A local synthetic parser check shows that unfinished final text and unfinished thinking can both produce an empty retained string. We cannot reconstruct the actual unfinished content or conclude that it was repetition, reasoning alone, or no English generation. The observed failure to finish within the fixed limit remains part of the result.

## Why lower loss did not select the winner

| Fine-tune | Validation loss before | After | Relative reduction |
|---|---:|---:|---:|
| C | 2.51530 | 1.93125 | 23.2% |
| D | 2.19882 | 1.45623 | 33.8% |

Both improved prediction of the same 16 reviewed English targets, including assistant framing. D had the lower loss but worse completion and missing requested material. This is a direct reason to select checkpoints using English answers as well as prediction loss. These percentages are not translation-accuracy gains and cannot be compared directly with the earlier ancient-text loss reduction.

The dataset is small, and the learning rate and training duration were a first generic recipe. Final-only supervision used native formatting without fabricated reasoning traces. Its possible effects on output or reasoning behavior, the strength of the updates, and example composition are hypotheses for further testing. This experiment does not identify which caused D's problems or establish that instruction training cannot help.

## Review limits and cost

The evaluation contains seven Hebrew, seven Aramaic, six Greek, and four application questions. Twenty supply original-language excerpts; four application questions do not. It does not establish factual recall without evidence across the corpus. Its English supervision was held out, but the base models may already know the passages, and B/D may have seen them during the earlier original-text stage.

Three AI reviewers checked separate language packets with candidate labels concealed and varied by case; the key was opened after their review receipts were frozen. This was not a formal blind study or human specialist certification. The Aramaic judge authored the evaluation, and the other judges had worked on training-example authorship or review. They did not independently duplicate one another's ratings. Assessment-label thresholds can differ by reviewer, so no aggregate biblical-accuracy percentage is assigned.

The provider's base-weight revision is unpinned. Earlier repeated controls changed despite matching requested settings. This comparison uses contemporary A/B controls and identical prompt-token hashes across all four arms, but a single sampled answer per condition cannot establish a replicated causal effect. The prior raw-text experiment's mixed result remains preserved rather than replaced by this more favorable B-versus-A sample.

New C/D training and four-arm evaluation estimate **$1.69 in compute and sampling**, plus **$6 checkpoint/storage contingency**, for **$7.69 reserved/estimated**. Earlier training and model comparisons are excluded. These are token-price estimates, not reconciled invoice amounts or public hosting costs. The new code passed 54 focused tests, and all 120 source-review approvals and the 104/16 split passed a separate metadata audit.

## Decision and next experiment

Retain B as the leading experimental checkpoint and preserve A/C/D results. Do not select D on loss or median response time, and do not repeat the current English recipe unchanged in expectation of a different result.

Before another paid run:

1. Preserve partial native messages and completion state in a new, versioned evaluator so future output-limit failures are diagnosable. Keep existing results unchanged.
2. Freeze a new evaluation before further training or prompt changes. Treat the now-reviewed questions as development evidence. Include requested translation coverage, Aramaic form distinctions, application fit, and a small general English retention check.
3. Test a smaller English-training update while holding the dataset and other settings fixed. Use a bounded calibration and compare with B; choose later data or formatting changes separately. The exact recipe and spending cap should be recorded before execution.

This stays within fine-tuning work. No application harness, public serving, remote repository, or additional training run was started during the results review. Existing checkpoints have 30-day retention; export/load compatibility and affordable public adapter hosting remain unverified. Prepared examples and private run records are excluded from publication pending release review.
