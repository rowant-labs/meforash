# First Inkling original-text adaptation: results

September 6, 2026. The first actual original-language fine-tune completed successfully. It improved prediction of the selected biblical editions on a fixed Hebrew/Greek sample. **The English comparison is mixed and does not establish a general accuracy gain.** Some explanations are better, some are worse, and several important mistakes persist. This is useful experimental evidence, not a model ready to launch as a reliable biblical authority.

The complete recipe, source layers, provider documentation, checkpoints, and reproduction commands are in [the training report](INKLING-TRAINING.md). The [aggregate measurements](../reports/inkling-adaptation-v1.json) and [unchanged-model repeat control](../reports/inkling-repeat-control-v1.json) contain no answer text or private checkpoint references.

## What was trained and measured

Full `thinkingmachines/Inkling` received a fresh rank-8 LoRA adapter, trained for one development-corpus pass: **136 updates and 3,280,433 input tokens**. Training targets were the unchanged Hebrew/Aramaic OSHB/WLC and Greek SBLGNT text plus document endings. Metadata was masked. There were no English-answer targets, commentaries, reasoning traces, or user conversations. The separate one-update calibration adapter was not continued into this run.

The fixed validation sample's average negative log likelihood fell from **0.050675 to 0.011513**, about **77.3% lower next-token loss**. Both measurements used the same 20,419 scored tokens from 12 held-out windows, six Hebrew and six Greek. Lower loss means better prediction of this text; it is not a percentage of questions answered correctly. There is no Aramaic in this loss-monitoring sample, and prior exposure during base-model pretraining is unknown.

The 24-question English evaluation completed without errors, truncation, or missing responses. Every adapter prompt-token hash matched its original baseline counterpart. All three conditions used the same source evidence, native rendering, medium reasoning effort, temperature, seed, and output ceiling. The adapter request deadline was extended from 240 to 300 seconds after slower calibration sampling; all answers completed within it.

| Measurement | Original unchanged model | Contemporary unchanged repeat | Original-text adapter |
|---|---:|---:|---:|
| Complete English answers | 24 / 24 | 24 / 24 | 24 / 24 |
| Median request time | 21.8 seconds | 36.0 seconds | 59.2 seconds |
| Estimated sampling cost | $0.180, already incurred | $0.168 | $0.127 |

These request times include service overhead and differ in service conditions and concurrency. They are observations from this experiment, not a controlled inference-speed benchmark or a public hosting estimate.

## How the answers were reviewed

All **72 final answers across 24 questions** were reviewed in three groups. Each question's three final answers received case-specific X/Y/Z labels, with order selected deterministically among six permutations. Reviewers checked the supplied edition, relevant annotations, named translations, and selected primary or scholarly references. They ranked answers with ties, distinguishing factual errors from interpretation and style. The integrating reviewer then mapped those judgments to the original baseline, contemporary repeat, and adapted model and checked consequential source claims.

This is **AI source review with labels concealed**, not a formal blind study, an independent gold-standard evaluation, or specialist certification. Reviewers shared prior project context. One had helped implement the labeling software and knew its method; another had earlier fresh-case findings in context. They reported not consulting the label key or inferring condition identities during review. The integrating reviewer knew the mapping. These limitations prevent treating reviewer preferences as an unbiased accuracy score.

The contemporary unchanged-model control matters: all 24 exact final answers and generated-token hashes differed from the original baseline despite matching requested settings and prompt tokens. We cannot assign the cause to sampling alone, since the provider exposes no pinned base-weight revision. An error absent from the first baseline but present in both the repeat and adapter is weak evidence for a training-caused regression. Conversely, an adapter answer better than both controls is a useful candidate gain, not a replicated causal result.

The questions are a development diagnostic, including known difficult cases. Seventeen include an original-language excerpt; seven do not. This is not a complete paired evaluation of excerpt and no-excerpt performance, a test of every biblical book, or an assessment of general reasoning preservation. No numerical biblical-accuracy score is assigned.

## What the comparison shows

**Some concrete improvements are visible.** On Exodus 3:14, the adapter gives a focused explanation without the original baseline's invented syntactic alternative and inaccurate main-text attribution to NJPS. On Proverbs 26:4–5, it correctly identifies the English quotation as NIV instead of attributing one wording to multiple translations. These are specific source-fidelity improvements in the sampled answers. The Exodus annotation identifies the relative particle and the finite verbs; JPS distinguishes its untranslated main designation from translation possibilities in a note. [Pinned Exodus](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Exod.xml), [JPS at Sefaria](https://www.sefaria.org/Exodus.3.14?with=Translations), [Proverbs translation comparison](https://www.biblegateway.com/passage/?search=Proverbs+26%3A4-5&version=NRSVUE%3BNIV).

**Aramaic remains uneven.** In Daniel 2:20, the adapter still incorrectly teaches that לֶהֱוֵא is a preposition plus infinitive. The annotation is a finite Peal imperfect, third masculine singular, with optative force in this blessing. The original baseline offered the correct parse alongside a false alternative; the repeated baseline and adapter both assert the false infinitive parse. In Daniel 3:18, the adapter and original baseline correctly preserve the supplied plural ketiv, “your gods,” while the repeated baseline silently substitutes singular wording. That is preserved competence against the original baseline, not a new training gain. [Pinned Daniel, including separate ketiv/qere records](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Dan.xml), [annotation key](https://github.com/openscriptures/morphhb/blob/3d15126fb1ef74867fc1434be1942e837932691f/parsing/HebrewMorphologyCodes.html).

The two clearest contrasting morphology results are Ezra 4:21 and Daniel 6:11, using the supplied source numbering. In Ezra, the adapter mislabels the Pael infinitive as Peal and a Hithpeel finite form as Itpael; the original baseline gets both right, and the repeat makes only the first error. In Daniel, the adapter correctly identifies all four requested forms, including the kneeling participle that both controls misparse as a perfect. Yet it adds a false literal gloss about blessing: the contextual Peal sense is kneeling. These examples show both a candidate regression and a candidate gain, with even the better answer requiring correction. [Pinned Ezra](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Ezra.xml), [Aramaic paradigms](https://hebrewsyntax.org/other_languages/biblical_aramaic_paradigms.pdf), [Comprehensive Aramaic Lexicon, brk](https://cal.huc.edu/oneentry.php?lemma=brk%20V&cits=all).

**Reasonable reflection can still rest on invented evidence.** All three forgiveness answers need correction. The adapter says Joseph tested his brothers after reconciliation; Genesis places the tests in chapters 42–44 before disclosure in chapter 45. The original baseline invents protective distance as the reason for Goshen, although Genesis 45:10 says the family would be near Joseph. The repeated baseline adds mistakes about manuscript hands in Luke 23:34a and substitutes a psychological reading for Matthew 18's stated judgment. Being reassuring or relatively preferred does not make an answer a checked training target. [Pinned Genesis](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Gen.xml), [Luke 23:34a apparatus discussion](https://tyndalehouse.com/2018/11/15/father-forgive-them-the-variant-in-luke-2334a/), [pinned Matthew](https://raw.githubusercontent.com/Faithlife/SBLGNT/c4d241a9c1c479a55b989ba35a4976c1d0b8052c/data/sblgnt/text/Matt.txt).

**Some apparent gains mainly concern presentation.** The adapter's Jeremiah 29:11 career response is more concise and fits the personal question better, but all three already reject a direct mandate to resign and preserve the user's decision. Several basic grammar and translation cases also tie. A shorter answer should not be counted as increased historical accuracy.

## Case-level review

Here **O** means the original unchanged baseline, **R** its contemporary repeat, and **A** the original-text adapter. `>` records a review preference, not a numeric accuracy margin; `=` records a tie on the requested task. Shared errors can remain in tied or first-place answers. The case IDs refer to [the frozen evaluation questions](../evals/comparison-large-v1.jsonl).

| Case | Preference | Interpretation of the adapter result |
|---|---|---|
| H01 · Genesis 1:1 | O = A > R, small | Correct core verb analysis retained; R adds an unqualified disputed noun-state analysis. |
| A01 · Daniel 2:20 | O > R = A, all flawed | False infinitive analysis persists; categorical error also appears in the repeat. |
| G01 · Mark 1:4 | O = R = A | Correct participle and agreement retained. |
| H02 · Exodus 3:14 | A > R > O | Fewer grammar/version errors and better focus in A. |
| A02 · Daniel 3:17 | O > R > A, qualified | A most overstates a disputed conditional scope; no answer settles the ambiguity. |
| G02 · John 1:1 | A > R = O, small | A better separates visible syntax from interpretation; unsolicited reflection remains. |
| H05 · Exodus 20:13 | O = R = A on translation | Prohibition preserved; shared lexical explanations need qualification. |
| A05 · Daniel 3:18 | O = A > R | A retains the original baseline's fidelity to the supplied plural ketiv. |
| G05 · Mark 10:45 | O = R = A | Core translation and passive/active relationships retained. |
| M01 · Proverbs 26:4–5 | A > R > O | A improves named-translation fidelity; broad reception claims remain unverified. |
| M02 · Suffering | O = R = A | Competing strengths and errors; A retains Luke 13's warning but adds citation and psalm-description problems. |
| M03 · Manuscript versus edition | A > O > R | A better describes editorial use of witnesses, but its word “original” still risks suggesting an autograph. |
| M04 · Synthetic instruction in a source | O = R = A | All reject this particular embedded directive; broader robustness untested. |
| A09 · Daniel 3 and conformity | R = O > A, modest | Useful reflection retained; A adds an unsupported claim about actual exilic readers. |
| G09 · Forgiveness | A > O > R, all need correction | Relative preference only; A reverses Joseph's testing/reconciliation chronology. |
| H10 · Jeremiah 29:11 and work | A > O = R, mainly style | Better economy and intent fit; no clear gain in core textual accuracy. |
| H13 · Ruth 2:8 | O = R = A | Prohibition, infinitive, addressee, and instructions are substantively correct. |
| H14 · 2 Kings 6:22 | A > R = O, limited | Roles preserved; all blur the rhetorical comparison with actual capture by sword/bow. |
| H15 · 1 Samuel 1:12–15 | O = R = A | Passive meaning and narrator/Eli/Hannah perspectives preserved; A is focused but less explicit on form. |
| A13 · Ezra 4:21 | O > R > A | A introduces two stem errors; R has one; all preserve the command's practical meaning. |
| A14 · Ezra 6:7–8 | O = R = A | Builders, royal funding source, and prevention of stoppage preserved. |
| A15 · Daniel 6:11 | A > R > O | A correctly identifies all four requested forms but adds a false literal gloss. |
| G13 · 2 Thessalonians 3:10–12 | A > O > R overall; core grammar tied | A stays focused on unwillingness; preference concerns restraint and scope. |
| G14 · Philemon 13–14 | A > R > O | A is more faithful and focused; O adds verse-12 wording inside its verse-13 translation. |

The [machine-readable review record](../reports/inkling-answer-review-v1.json) retains these preferences and the review-artifact hashes. The case review is a record of this experiment's observations. It is not an endorsement of any answer as an authoritative explanation or a ready-made supervised training target.

## Cost and next experiment

The [incremental cost record](../reports/inkling-experiment-cost-v1.json) totals **$25.31 estimated or reserved**, including **$6 of checkpoint/storage contingency**. Estimated compute and sampling are **$19.31**. This covers calibration, the development training pass and validation, four calibration answers, the 24-question unchanged repeat, and 24 final adapter answers. It excludes the previously incurred baseline and model comparisons. Provider billing has not been reconciled; these are not settled charges.

Keep this original-text adapter as arm B of the [training plan](training-plan.md), alongside the unchanged baseline. The next proposed training experiment is a small set of approximately **100–300 checked English translation and explanation examples**, using different passages from a newly frozen evaluation. Train the same examples on the unchanged model (arm C) and after original-text adaptation (arm D), so we can test whether source exposure adds value once English explanations are supervised. That comparison has not been run.

Each target should cite the exact edition and include source support for morphology, reading choices, and historical claims. Ambiguity should be stated rather than hidden in a confident target. Include Aramaic deliberately and examples where a sound reflection must not invent narrative details. Drafting by an LLM is not validation; record review status and obtain specialist checks before making scholarly accuracy claims. Freeze fresh evaluation questions and criteria before developing these examples, and keep their answers out of training.

Another raw-text pass is not yet justified by this mixed English result. This experiment does not require building a harness first; source lookup and citation checks remain a separate future option. The fine-tune's training and sampling checkpoints are private, initially retained for **30 days**. Review export and retention before expiry. Public custom-adapter serving, export/load compatibility, and a monthly hosting cost remain unverified. No model artifact, user data, or repository has been published.
