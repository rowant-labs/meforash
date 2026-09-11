# First live baseline: gpt-oss-120b

Experiment date: September 5, 2026 (local date; journals use UTC). **Tinker access and native sampling work. The unchanged model produces fluent English, but preliminary source checks found concrete linguistic mistakes and unsupported historical citations. No model has been trained.**

These are development observations, not a certified biblical accuracy score. The first four answers and a four-answer life-reflection sample received a source-checked AI review; a qualified scholarly review of the full pilot remains outstanding. Completion measures below describe delivery of a final answer, not correctness.

## Execution and cost

The machine-readable [aggregate report](../reports/baseline-2026-09-05.json) records journal and manifest hashes, counts, settings, tokens, and unreconciled cost estimates without publishing raw answers or account information. Raw journals remain in ignored local run directories.

| Run | Planned | Complete final answers | Incomplete | Errors | Unattempted | Returned-token estimate |
|---|---:|---:|---:|---:|---:|---:|
| Four-case smoke · low reasoning | 4 | 4 | 0 | 0 | 0 | $0.00424044 |
| Pilot · provided excerpts · low | 40 | 39 | 1 | 0 | 0 | $0.04613274 |
| Pilot · no excerpts · low | 40 | 5 | 0 | 1 | 34 | $0.00651486 |
| Four-case control · high reasoning | 4 | 2 | 1 | 1 | 0 | $0.01534950 |
| **Total across repeated questions** | **88** | **50** | **2** | **2** | **34** | **$0.07223754** |

All four local processes have stopped. The provided-excerpt pilot attempted all 40 questions; G07 hit its output limit. The no-excerpt pilot stopped on the A02 timeout. The high-reasoning control hit the output limit on H01 and timed out on M01. No timeout was automatically repeated. The aggregate is marked partial because 34 planned comparison requests were never started; it is not a background job that is still running.

The intended pilot is **40 unique questions in two evidence conditions**, not 80 unique questions. Only the 12 grammar and three direct translation prompts gain source excerpts in the provided condition; the other 25 prompts are unchanged. The four-case smoke and reasoning control repeat the first four pilot questions. The incomplete no-excerpt run cannot establish a full paired comparison.

Across 52 returned responses, exact submitted and generated token counts were 13,682 input and 80,622 output. At the recorded $0.33/million input and $0.84/million output rates, their compute estimate is **$0.07223754**. The two timeouts retain another **$0.01428192** in uncertain local reservations, giving **$0.08651946**, approximately nine cents, accounted or reserved locally. The provider invoice has not been reconciled; these amounts are not confirmed charges.

Both timeout cases stopped their respective runs with uncertain accounting, retaining a full local request reservation. They were not automatically retried. A local timeout cannot cancel a request already accepted remotely. Reconcile provider usage before making a fresh attempt at those cases. The SDK's internal submission retries and provider metering prevent these local estimates from being a guaranteed invoice ceiling.

## What the first four answers showed

The following are narrowly checkable observations from the initial low-reasoning smoke, not a substitute for full linguistic or historical review. Edition annotations are evidence with their own editorial limits.

| Case | Observation | Checkable source |
|---|---|---|
| H01 · Genesis 1:1 | Correctly identifies the verb as Qal perfect, third-person masculine singular, but misidentifies a vowel and claims the final aleph marks an infinitive absolute. Aleph belongs to the root; the pinned annotation is `HVqp3ms`. | [Pinned Genesis](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Gen.xml), [OSHB morphology codes](https://hb.openscriptures.org/parsing/HebrewMorphologyCodes.html) |
| A01 · Daniel 2:20 | Misidentifies **לֶהֱוֵא** as a preposition/pronoun meaning “to him.” The source marks an Aramaic Peal imperfect verb, third-person masculine singular (`AVqi3ms`), in the blessing “Blessed be the name of God.” | [Pinned Daniel](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Dan.xml), [OSHB codes](https://hb.openscriptures.org/parsing/HebrewMorphologyCodes.html), [Daniel 2](https://bible.usccb.org/bible/daniel/2) |
| G01 · Mark 1:4 | Gets the basic participle parsing right, but alters **κηρύσσων** to **κῆρύσσων**, supplies the wrong lemma, and calls **εἰς ἄφεσιν** an infinitive before also identifying it as a prepositional phrase. | [Pinned Mark](https://raw.githubusercontent.com/Faithlife/SBLGNT/c4d241a9c1c479a55b989ba35a4976c1d0b8052c/data/sblgnt/text/Mark.txt), [MorphGNT Mark, rows 020104](https://raw.githubusercontent.com/morphgnt/sblgnt/master/62-Mk-morphgnt.txt) |
| M01 · Proverbs 26:4–5 | Offers a plausible general reflection about discernment, but invents Hebrew wording and a quotation attributed to Sirach 27:1–2. Those Sirach verses concern profit and sin in trade. A discussion of the Proverbs pair is also misattributed to Berakhot 61a; the directly relevant discussion is Shabbat 30b:7. | [Pinned Proverbs](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Prov.xml), [Sirach 27](https://bible.usccb.org/bible/sirach/27), [Shabbat 30b:7](https://www.sefaria.org/Shabbat.30b.7?lang=bi) |

MorphGNT and English translations here are review references; this review does not add them to the approved original-text training corpus. MorphGNT links currently use a mutable branch and are not a frozen scholarly answer key. Broader syntax, dating, and interpretation claims require suitable scholarship and qualified review.

## Higher reasoning control

A four-question control changed reasoning from low to high and raised the generation ceiling from 4,096 to 8,192 tokens. This changes two settings and is unreplicated, so it is exploratory rather than a clean measurement of reasoning effort alone.

H01 exhausted its token ceiling without a final answer; M01 timed out. A01 correctly recognized a form of the Aramaic verb **הוה**, but retained an unsupported purpose-clause analysis and invented details about the word's formation. Contextual jussive force is a reasonable issue to discuss; calling the form a purpose/result particle is the specific error. G01 corrected its lemma to **κηρύσσω** and its treatment of the prepositional phrase, but kept the misspelled present participle and introduced the incorrect aorist participle **ἐκηρύξας**. Compare **κηρύξας** in [MorphGNT 1 Corinthians 9:27, row 070927](https://raw.githubusercontent.com/morphgnt/sblgnt/master/67-1Co-morphgnt.txt).

The control corrected selected details but retained or introduced concrete linguistic errors, while two cases produced no usable final answer. It does not establish that a reasoning setting solves the observed reliability problems.

## Life-application sample

Four completed answers from the larger provided-condition run were reviewed against the project's answer contract. None of these four questions actually received a source excerpt; their evidence fields are empty. Selection was qualitative and small, not a random estimate of overall performance.

| Case | Useful behavior | Source or application concern |
|---|---|---|
| H10 · Jeremiah 29:11 and changing jobs | Rejects treating the verse as a career directive and preserves personal agency. | Adds an unsupported petition behind Jeremiah's letter and understates the concrete communal restoration setting. [Pinned Jeremiah](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Jer.xml) |
| A09 · Daniel 3 and conformity | Discusses conscience and humility about outcomes without a named denominational frame. | Invents wording attributed to Daniel 3:30; that verse concerns the youths' advancement, while royal praise appears in 3:28. Calling the king's response a conversion goes beyond the passage. [Pinned Daniel](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Dan.xml) |
| G09 · forgiveness | Begins empathetically and acknowledges emotional difficulty. | Invents a Matthew 5:22 quotation and Greek insult. The verse has **Ῥακά** and **Μωρέ**, not the supplied **ἀσώματος**. It also risks imposing an apology without knowing who did what. [Pinned Matthew](https://raw.githubusercontent.com/Faithlife/SBLGNT/c4d241a9c1c479a55b989ba35a4976c1d0b8052c/data/sblgnt/text/Matthew.txt), [Matthew 5:22](https://bible.usccb.org/bible/matthew/5) |
| M02 · suffering and punishment | Allows multiple biblical perspectives and does not diagnose suffering as divine punishment. | Labels wording from Job 42:5 as 42:3 and oversimplifies differences between biblical collections. Suggestions about what God is shaping should remain optional reflections. [Pinned Job](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Job.xml) |

These answers generally recognize reflection intent and avoid promoting a named denomination. Long introductory structures sometimes delay practical help. The main observed weakness is plausible reflection supported by inaccurate quotations and references. Source grounding and personal agency therefore need review alongside linguistic accuracy in the before/after experiment.

## Reproducibility and limits

Runs use native Tinker sampling on `openai/gpt-oss-120b`, temperature 0, seed 20260905, prompt date 2026-09-05, a 6,000-token input ceiling, and a 120-second complete-operation deadline. The default low-reasoning runs cap generation at 4,096 tokens. Output counts include reasoning and protocol tokens; analysis text is not retained. No training client or adapter was created.

The pinned official chat template and tokenizer matched the live provider's full vocabulary and Unicode probes. Every submitted prompt was checked for exact token-ID equality. This validates input representation, not a pinned provider weight revision; Tinker did not expose one. Sampling repeatability is not guaranteed by a shared model name, seed, or temperature.

The aggregate separates complete answers, incomplete responses, errors, and unattempted cases. Three dataset fixtures test constructed metadata handling; any format-check passes establish only that narrow behavior. They are not biblical accuracy scores. All substantive evaluation criteria remain draft and all answers await qualified review. See [native runner details](TINKER-BASELINE.md) and the [evaluation method](BASELINE-EVALUATION.md).

## Decision for the training experiment

Keep gpt-oss-120b as an experimental candidate; do not treat fluent English or a cheaper compute estimate as evidence that it is already a reliable biblical language expert. The observed errors give the original-text-only adaptation experiment specific weaknesses to test. They do not show that raw-text exposure will repair grammar explanations or invented citations.

Before the first adapter run, review a balanced subset of completed answers against sources, resolve the timeout/accounting records before any rerun, and finalize a bounded training calibration with documented LoRA settings. Preserve this baseline, the unchanged evaluation questions, and a separate final evaluation before tuning extensively. If task-specific language review shows an inadequate starting point, run a small matched comparison with another viable base before spending on a full adaptation pass. Public custom-adapter serving remains a separate unverified requirement.

The whole Hebrew/Aramaic and Greek raw-text experiment remains central. The next training objective is still one development-corpus adaptation pass followed by the same English questions, measuring improvements and regressions rather than assuming either outcome.
