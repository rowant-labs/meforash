# Smaller English-training update: calibration v2

**Completed September 6, 2026. Retain original-text-only B as the leading development checkpoint; preserve gentler English checkpoint E as a promising follow-up.** E completed all 30 answers and improved on the earlier combined checkpoint D, but did not clearly improve on B and omitted requested content in three answers. All 120 candidates were reviewed against the frozen sources and criteria.

The [first English instruction experiment](INKLING-INSTRUCTION-RESULTS.md) favored the original-text-only checkpoint B on its small review. The combined checkpoint D predicted the English validation targets better but failed to finish three answers and omitted requested content in others. This follow-up tests a smaller update while preserving that evidence.

## Fixed comparison

| Arm | Treatment |
|---|---|
| A | Contemporary unchanged Inkling control |
| B | Preserved original-text-only checkpoint |
| D | Preserved original-text-plus-English checkpoint, learning rate 0.0001 |
| E | New adapter starting from B's weights, same English training at learning rate 0.00002 |

Only E requires new training. It uses the unchanged 104 training examples and 16 validation examples, identical shuffled order, rank 8, component selection, batch size 16, one epoch/seven updates, and a fresh optimizer. The learning rate is five times lower. E starts from B, not D. The rate is an experimental choice, not a provider-optimized recipe. The [training manifest](../manifests/instruction-calibration-training-v2.json) fixes its source, data, recipe, code identities, and estimated cost.

The target answers and native final-only formatting are unchanged. This isolates one recipe change. A benefit or regression would not establish that this learning rate is optimal or identify the separate effects of target formatting and example composition.

## Fresh evaluation and diagnostics

The [30-question evaluation](../evals/instruction-calibration-v2.jsonl), [evaluation manifest](../manifests/instruction-calibration-evaluation-v2.json), and [execution protocol](../manifests/instruction-calibration-experiment-v2.json) were frozen before training or sampling. Bible coverage is seven Hebrew, seven Aramaic, six Greek, and four application cases, with six additional objective English retention checks. All 102 chapter families used in the existing English training/validation data are excluded. There are no identical prompts or explicitly referenced verses shared with the four earlier evaluation files. The seven Aramaic questions use new spans within previously evaluated Daniel 5 and Ezra 7; the small Aramaic corpus limits chapter-level novelty. Unknown base pretraining and B's earlier raw-text exposure remain limitations.

All four arms use the same question bytes and system prompt, medium thinking effort 0.7, temperature zero, seed 20260905, an 8,192-token output ceiling, a 6,000-token input ceiling, and 300-second sampling deadlines. Submit each of the 30 questions once per arm, with no selective retries. Preserve matched prompt-token hashes and verified checkpoint receipts.

The versioned evaluator retains raw generated token IDs and separately identified partial final text in private, restricted-permission diagnostic files. Completed text and unfinished text remain distinguishable. Thinking text is excluded from public reports and answer-review packets. This addresses the earlier inability to diagnose three empty extracted final answers; it does not change those historical records or turn partial answers into completed ones.

The six general checks use constructed fixtures with deterministic expected fields. Report their exact completion and pass counts separately from Bible source review. Literal field checks can reject equivalent wording; for example, the folder-location case can reasonably answer “shelf” or “on the shelf.” Review semantic correctness separately before interpreting a literal failure. These are a small instruction-following check, not a general reasoning benchmark or a guarantee of retention.

## Execution results

All four arms returned all 30 requests without request errors, timeouts, missing usage, unresolved requests, or selective retries. All 120 private diagnostic files verified, and every submitted prompt matched the frozen local rendering: 12,445 input tokens per arm.

| Arm | Native answers completed | Generated tokens | Median response time | Literal general checks | Semantically correct general checks |
|---|---:|---:|---:|---:|---:|
| A · unchanged | 30/30 | 37,951 | 28.44 s | 6/6 | 6/6 |
| B · original text | 30/30 | 24,615 | 22.54 s | 5/6 | 6/6 |
| D · English LR 1e-4 | 28/30 | 20,270 | 5.92 s | 6/6 | 6/6 |
| E · English LR 2e-5 | 30/30 | 16,281 | 10.95 s | 5/6 | 6/6 |

The two literal general-check failures concern equivalent prepositional wording for the folder locations, not incorrect locations or invented ownership. These six simple fixtures are too small to establish broad retention. Response time and generated-token counts include the model’s generation process; shorter outputs and faster replies do not themselves establish better answers. D’s two unfinished responses each reached 8,192 tokens. Their partial final content is retained separately; neither is a parser error. All 120 responses have zero parser errors or diagnostic warnings.

## Source review and decision

The unchanged English validation set contains 16 examples and 2,344 scored assistant tokens. E’s weighted negative log likelihood fell from **2.198822 to 1.791808**, an **18.5% decrease**, with decreases in Hebrew, Aramaic, and Greek groups. This is a prediction-loss result, not a measure of translation accuracy. It does not by itself establish that E answers better than B or D.

Use per-case concealed candidate labels and review all 120 returned candidates. Source fidelity and requested coverage matter before scope and clarity; allow ties and separate completion failures, omitted deliverables, parsing errors, and interpretive disagreements. Report partial final content as unfinished, without inferring an unwritten continuation. AI source checks do not constitute expert certification, and reviewer project-role overlap remains disclosed.

The predeclared decision rule required useful English-answer gains without concerning completion, coverage, or retention regressions before replacing B. **This comparison does not meet that bar.** E versus B is nearly balanced, with three requested-content omissions in E and none in B. Keep B as the main development checkpoint, retain E, and preserve all results.

The [operational measurements](../reports/inkling-instruction-calibration-v2.json) and [case-level source review](../reports/inkling-instruction-calibration-answer-review-v2.json) record the complete comparison. The following preferences use **only the 24 Bible questions**; the six general fixtures are excluded.

| Comparison | First preferred | Second preferred | Tied |
|---|---:|---:|---:|
| B versus A | 9 | 3 | 12 |
| E versus A | 12 | 7 | 5 |
| E versus B | 7 | 8 | 9 |
| E versus D | 12 | 3 | 9 |
| B versus D | 13 | 5 | 6 |
| D versus A | 10 | 10 | 4 |

E’s strengths were often focus and useful concision. In the Luke 17 question it distinguished the ten people’s cleansing from the returning Samaritan’s described salvation/healing without overextending the theology. In Romans 15 it translated the passage and correctly separated the prayer, two purpose clauses, and command to welcome. Its Ecclesiastes 4 reflection offered a concrete, optional way to seek support while respecting the source’s imagery.

The omissions matter for an English-speaking user relying on the model to render the source. E omitted the opening narrative of 1 Samuel 3:10 (IH204), lost reward details and the requested infinitive relationship in Daniel 5:7–8 (IA202), and omitted the royal self-identification and issuing clause from the requested Ezra 7 decree translation (IA207). These all had completed native turns. The reviewer assessed the first and third as incomplete and the second as mixed; semantic coverage and assessment labels are kept separate.

D had four natively completed answers with missing requested content, plus two native output-limit failures: IH201 and IA205. The new diagnostics show that IH201 repeatedly copied Hebrew source lines without giving the English translation. IA205 already covered the requested substance before repeating unrequested English sentences extensively. Neither failure was a parser error, and the second is not counted as absent English content. These observations concern this new run; the earlier v1 failures still lack raw-token records and cannot be reconstructed from it.

B also retains errors. Its Daniel 5:10–12 explanation drew an unsupported inference about the queen’s family relationship; its Daniel 5:18–19 response silently substituted a separately recorded qere form in a source-labelled transcription and overclaimed immediacy. E made other errors in the latter passage, including confusing a recipient with a direct object and participles with perfect verbs. A fluent or preferred answer is not automatically fully correct.

Three AI reviewers covered separate language/application partitions. The ratings and packet hashes were frozen before the integration opened the identity key, and all 120 completed/partial final outputs and native statuses matched their operational records exactly. Reviewers had prior project roles; the coordinating reviewer knew aggregate completion counts, which could indirectly identify an unusual unfinished candidate. There was no independently duplicated specialist review. Preferences include source fidelity, coverage, focus, and application usefulness, with subjective thresholds; they are not accuracy percentages or proof of broad biblical competence.

The next useful preparation task is to audit the fixed English targets for complete requested translations, precise occurrence-level grammar, and intent-appropriate focus, then design one separately versioned revision. Freeze another evaluation before that revision is trained. Keep B and E as controls; this run does not identify whether target composition or native target formatting contributes to omissions. No further dataset change or paid run was started here.

## Budget and boundaries

E training plus two validation passes estimates **$0.48149508 in compute**, with **$3 checkpoint/storage contingency**. The shared training reservation rose from $31.95373776 to $35.43523284, within the existing $50 cap. Each 30-question evaluation has a $1.50 ceiling; maximum input/output token reservations total about $1.487 per arm. The incremental experiment ceiling is **$10**, covering the $3.48149508 training reservation and up to $6 in sampling reservations. Actual token-price estimates may be lower. These are local guards, not a provider invoice or guaranteed provider-enforced cap.

The completed E run and four evaluations estimate **$1.03845124 in new compute and sampling**, plus **$3 checkpoint/storage contingency**, for **$4.03845124 estimated or reserved**. This is below the $10 experiment cap and excludes earlier training/evaluation rounds. The provider invoice remains unreconciled.

Only this E calibration and the matched A/B/D/E evaluation were executed. No further epochs, new training targets, application harness, deployment, or publication are included. Checkpoints retain a 30-day TTL; public serving cost and export/load compatibility remain unresolved. The earlier original-text and instruction experiments stay unchanged.

## Local inspection and reproduction limits

Verification included 60 focused tests for the new training, evaluation, diagnostics and aggregation code, plus 17 synthetic review-integration checks. The source criteria were checked before sampling; completed run verification also checked the frozen software/data identities, checkpoint lineage, all prompt hashes, all 120 private diagnostic artifacts, and exact native-to-review packet matches. These are software and provenance checks, not expert accuracy validation.

The trainer and evaluator default to a local plan, without model calls. From a prepared checkout, inspect E’s plan with `python -m bibleprep.train_instruction_calibration` and the unchanged-model evaluation plan with `python -m bibleprep.evaluate_instruction_calibration --arm A`. Paid execution requires the explicit `--execute` flag, a configured private key, and the frozen local receipts. The evaluator always uses all 30 questions; it does not support selectively repeating failed cases.

The [trainer](../bibleprep/train_instruction_calibration.py), [evaluator](../bibleprep/evaluate_instruction_calibration.py), [diagnostics](../bibleprep/native_diagnostics_v1.py), and [aggregator](../bibleprep/summarize_instruction_calibration.py) are inspectable. The execution protocol pins the training and sampling software, source checkpoints, question bytes, prices, and settings before execution. Local prompt rendering produced 12,445 input tokens per full arm, with at most 760 in any question; actual submissions are checked against these hashes.

These wrappers deliberately verify this experiment’s preserved checkpoint receipts. Repeating the study on another account requires a new versioned protocol around independently recreated parents, rather than bypassing the checks. The provider’s base weights remain unpinned. Prepared English examples, model artifacts, and private operational records are still excluded pending release review; the public scaffold therefore describes the method but is not yet a fully self-contained reproduction package.
