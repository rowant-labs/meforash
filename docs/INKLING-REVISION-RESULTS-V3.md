# Revised English targets: controlled comparison v3

**September 6, 2026: comparison and source review complete. Retain original-text-only B provisionally; preserve F.** The revised English fine-tune did not clearly improve on B: on 24 Bible questions, F was preferred on five, less preferred on six, and tied on thirteen. F omitted requested content in three answers, compared with one in B. The [case-level review](../reports/inkling-instruction-target-revision-available-answer-review-v3.json) covers all 94 returned answers. E stopped after four answers, so this round cannot support a full comparison of the old and revised English datasets.

This experiment tests the separately reviewed [v3 English-target revision](INKLING-TARGET-REVISION-V3.md). All earlier checkpoints and evidence remain preserved. These are small-sample AI judgments, not an expert accuracy score or proof of broad historical understanding.

## Fixed comparison

| Arm | Treatment |
|---|---|
| A | Contemporary unchanged full Inkling |
| B | Retained original-language-only adapter |
| E | Retained B plus the original 104 English examples at learning rate 2e-5 |
| F | New B plus the revised 104 English examples at learning rate 2e-5 |

F starts from B's weights with a fresh optimizer. It retains rank 8, all three trained component groups, batch size 16, one epoch of seven updates, native final-only supervision, effort 0.7 and the original example order. Fourteen prompts and targets change; the other 90 training examples, all 16 validation examples, exact ancient source excerpts, IDs and source families remain unchanged. The revised training sequences contain 65,573 input positions and 16,598 supervised positions. The two validation forwards each use 10,837 input positions and 2,344 supervised positions. The [training manifest](../manifests/instruction-target-revision-training-v3.json) and [execution protocol](../manifests/instruction-target-revision-experiment-v3.json) were frozen before submission.

The change bundles task scope, target wording and length, and supervised-token volume. It is not a length-controlled causal test. The previous audit found no clear material errors in the narrow original targets; the new tasks broaden translation coverage rather than correct demonstrated old factual errors.

## Evaluation and review

Each arm was assigned the same 30 frozen questions once: seven Hebrew, seven Aramaic, six Greek, four life-application and six constructed general-English cases. Native output limits are 8,192 generated tokens, including thinking and final text; the input ceiling is 6,000. All arms use temperature zero, effort 0.7, 300-second request deadlines, and the same native renderer and prompt tokens. Applications receive the accepted Bible-based, non-denominational reflection behavior.

The sampling seed is **20260905**, preserving the previous evaluation setting. The training shuffle seed remains **20260906**. The earlier proposal listed the training seed in its suggested sampling settings; this explicit pre-execution choice resolves that planning inconsistency. No model answers were consulted in choosing either seed.

All questions, criteria and the separate pre-output scoring supplement are frozen. The revised dataset was fixed before its authors opened the new questions. Scoring allows defensible alternative translations and accurate plain-English grammar explanations. Keep source accuracy, requested-content coverage, native completion and task focus separate. Preserve available partial final outputs and every failure; no selective retries. SDK-internal submission retries may occur and are not exposed by the provider.

Private review packets conceal arm labels separately for each case and contain final or structurally available partial answers, never hidden thinking. The plan called for reviewing all 120 returned candidates before labels were integrated. Reviewers are AI agents with prior project roles, not an independent human expert panel or a formal blinded study. General-fixture semantics and requested JSON formatting are separate from biblical judgments and from each other.

All 19 supporting chapter families were present in B's original-text training, and base-model exposure is unknown. The fresh questions avoid every English SFT chapter and all prior explicitly evaluated verses/prompts, but seven Aramaic cases share two chapter families used in earlier evaluations. This is a small development comparison, not an unseen-text or whole-Bible accuracy benchmark. Repeated development cycles further limit broad claims.

Three principal AI reviewers checked disjoint packets containing 43 Hebrew/general, 21 Aramaic, and 30 Greek/application answers. A fourth agent supplied a narrow source advisory on two masked Hebrew candidates. Before the reviews were frozen or labels revealed, that advisory led the principal reviewer to treat one internally awkward subject explanation as a limited ambiguity rather than a material reversal of agency; a separate prediction-versus-prohibition explanation retained its qualified error finding. The advisory and revision history are preserved. All three final reviews were frozen before label integration. The integration verified 94 exact answer-to-native-receipt bindings and all 120 availability slots; absent answers were never assigned semantic grades.

## Answer findings and decision

Preferences consider source fidelity, coverage and task focus; a less-preferred answer is not necessarily factually wrong. The first named model is the subject of each comparison below.

| Comparison | Preferred | Less preferred | Tied | Jointly reviewed Bible questions |
|---|---:|---:|---:|---:|
| B versus A | 12 | 3 | 9 | 24 |
| F versus A | 11 | 5 | 8 | 24 |
| F versus B | 5 | 6 | 13 | 24 |

E's four returned Hebrew answers were preferred to B on two questions and tied on two; against F, E was preferred once and tied three times. This small, contiguous subset excludes all Aramaic, Greek, application and general questions. It cannot select E or establish the effect of revising E's dataset. The earlier complete v2 comparison remains separate evidence on different questions.

All A/B/F answers completed natively, and each arm passed all six simple general-English fixtures for both meaning and requested format. E returned no general fixtures in this round. Those six checks provide limited retention evidence, not a broad reasoning or English benchmark.

F's three requested-content omissions were distinct:

- **IA303, Daniel 5:20–21:** F summarized the event instead of supplying the full requested translation. B supplied the requested content.
- **IG302, Mark 5:25–29:** both B and F translated the passage but omitted the requested explanation of the opening condition/medical-history participles in relation to the main action. B also incorrectly called the perfect healing form present tense; F avoided that extra error.
- **IM304, Philippians 1:3–6:** F's reflection omitted the gospel-partnership context required by the frozen criteria. A and B retained that context but misattributed their quoted English wording to NRSVUE, a separate quotation-edition problem.

F also avoided some errors found in B, including a Hebrew article misparse and an unsupported claim that Barnabas verified Saul's account. Other F answers introduced or retained problems, including an inaccurate Aramaic stem label and a substituted Hebrew lexical term. The case-level report preserves these distinctions and acceptable alternative readings; the result is not simply a preference for longer answers.

**Keep B as the main development checkpoint and preserve E/F for comparison.** The broader targets did not establish a gain over B or eliminate requested-content omissions. Do not add epochs or choose F because its validation loss is lower or its responses are faster. This round is now development evidence. Before another training change, specify a distinct hypothesis for the remaining clause, grammar-explanation and contextual-coverage failures, and freeze a separate evaluation; broader scholarly review is needed before public accuracy claims. No further paid run is part of this result.

## Execution contingency

E returned its first four Hebrew answers, then its IH305 request failed after 300.0384 seconds. The recorded privacy-safe kind is `network_error`, consistent with the local 300-second deadline; the provider-side cause remains unknown. The runner retained the $0.04955856 worst-case request reservation because billing is uncertain and stopped, leaving 25 questions unsubmitted. No selective retry was made. A, B and F each finished all 30 questions under the unchanged protocol. The unavailable E answer receives no semantic grade.

The original review tooling required 120 returned answers. A separately versioned [reporting contingency](../manifests/instruction-target-revision-review-contingency-v3.json) retains all 120 intended slots and prepares all 94 actual answers for review. Pairwise judgments use only questions with both candidates available and disclose that denominator. This operational contingency was chosen from completion counts before reviewers opened any candidate text; original data, scoring criteria, generation settings and frozen tools remain preserved. The complete A/B/F Bible comparison covers 24 questions, while every comparison involving E is restricted to its four returned Hebrew questions.

After candidate review began, an integration validation check incorrectly expected the legacy `missing_results` counter to be zero. That counter includes the 25 unsubmitted E questions. A separately frozen [integration repair](../manifests/instruction-target-revision-integration-repair-v3.json) instead requires it to equal `not_started`, while still requiring zero unresolved requests and missing usage. It preserves the original tooling, packets and judgments; it changes no scoring criteria or model calls. Eighteen tests and an independent code review passed before review integration or label-key access.

## Completed execution

All 94 returned answers completed natively, with no output-limit or parsing failures. There were 95 submitted requests, one terminal error and 25 unsubmitted slots. All 94 private diagnostic receipts were verified. A/B/F each used 12,238 input tokens across the 30 questions; E's four returned answers used 2,112. All available native prompt hashes match the frozen local rendering. The [operational aggregate](../reports/inkling-instruction-target-revision-partial-v3.json) preserves the incomplete four-arm comparison and exact provenance.

| Arm | Returned and natively complete | Request errors | Not submitted | Known generated tokens | Median returned-response time |
|---|---:|---:|---:|---:|---:|
| A | 30/30 | 0 | 0 | 42,604 | 33.21 s |
| B | 30/30 | 0 | 0 | 25,850 | 61.35 s |
| E | 4/30 | 1 | 25 | 1,282 | 29.46 s |
| F | 30/30 | 0 | 0 | 15,701 | 28.99 s |

Generated-token counts include the model's generation process, not just visible answers. Response times are measured in this run and include provider/transport conditions; E's median covers only four returned Hebrew answers and excludes its 300-second failure. These figures do not establish production latency or answer quality.

F completed all seven updates, two validation forwards and two checkpoint saves with no uncertain training operations. The preserved validation set's weighted NLL fell from **2.19882247 to 1.79157511**, an **18.52% decrease**. E's prior final NLL was 1.79180849 on the same validation bytes. These nearly equal losses measure target prediction, not translation accuracy or a meaningful quality advantage.

## Budget and readiness

The official provider prices were rechecked before execution: $1.87/M input tokens, $4.68/M output tokens and $5.61/M training tokens, including the temporary discount. Read-only provider checks found both B/E checkpoint types present, private and unexpired, and confirmed B's base model, rank and trained components. [Preflight record](../manifests/instruction-target-revision-preflight-v3.json), [official prices](https://tinker-docs.thinkingmachines.ai/tinker/models/).

F reserved **$0.48945567** for one epoch and two validation forwards, conservatively pricing the forwards at the training rate, plus **$3 checkpoint/storage contingency**. Sampling is capped at **$1.50 per arm**, **$6 total**. Combined reservations remain within the **$10 incremental cap**. The shared training ledger rose from $35.43523284 to $38.92468851 against its $50 cap. These are local submission guards and estimates, not provider-enforced limits or reconciled invoice amounts.

Training and sampling records, checkpoints, private receipts and credentials remain excluded from publication. Public custom-adapter hosting and export/load compatibility are still unverified. This experiment does not introduce a harness, deploy an app, or publish the repository.

The completed round accounts for **$0.48945567** in estimated training/validation compute and **$0.52200834** in sampling estimates/reservations. Sampling includes **$0.47244978** for returned usage and the **$0.04955856** uncertain E request reservation. This totals **$1.01146401**, plus the **$3 checkpoint/storage allowance**, or **$4.01146401** estimated/reserved under the $10 cap. The allowance is not a confirmed storage charge, and the provider invoice remains unreconciled.
