# Evaluation runbook

Current execution status (September 10, 2026): the bounded [Candidate G comparison is complete](CANDIDATE-G-RESULTS.md). All 60 native answers, 60 individual judgments and 30 paired judgments were verified and frozen before label integration. Across 24 Bible pairs, G was preferred on 3, B on 10, with 11 ties. Retention diagnostics passed, but the frozen preference gate independently failed, so retain B. Aggregate finding counts are AI-review flags rather than factual-accuracy scores; root review disputes the James material-error flag applied to both arms and treats some omissions as rubric/notice-level, without changing the failed preference result. Estimated execution cost is $1.58403889; with the $3 storage contingency it is $4.58403889, below the $7.66376908 reservation. No further training, recollection or promotion follows. Next audit evaluation severity and advance B beta hosting/recovery readiness. See the [frozen method](CANDIDATE-G-EXPERIMENT.md) and [living state](../manifests/execution-state.json).

Updated September 10, 2026 UTC. Use with the [execution plan](EXECUTION-PLAN.md). This file maps completed evaluations, the current Candidate G comparison and a separate proposed historical-evidence follow-up. The known-topic pilot is complete; the sixteen-answer guidance comparison is complete and its adoption gate failed. The [offline planner](EVIDENCE-EVALUATION-TOOLING.md), [collection auditor](EVIDENCE-COLLECTION-ACCOUNTING.md), [native handling](EVIDENCE-NATIVE-BRIDGE.md), [request preparation](EVIDENCE-REQUEST-PREPARATION.md), and [paired review tools](EVIDENCE-PAIRWISE-REVIEW.md) preserve their constructed engineering checks. The [single-run pilot runner](EVIDENCE-PILOT-RUNNER.md) supplies the separately verified actual provider boundary. All previously reviewed questions, including this pilot, are development material. The [entry contract](EVIDENCE-EVAL-ENTRY-CONTRACT.md) remains a reference for future source bindings and completeness requirements.

## Where evaluation happens

| Layer | Location | What it establishes |
|---|---|---|
| Offline engineering checks | Local Python tests in [`tests/`](../tests/); mock transports and constructed fixtures | Correct source handling, formatting, budgets, errors and boundaries; no model-quality score |
| Evidence validation | [`bibleprep/evidence.py`](../bibleprep/evidence.py); private drafts in `data/evidence/drafts/v1/` | Valid draft structure, references and source-byte binding; not factual accuracy or approval |
| Model generation | Local versioned runner submits native inference requests to **Tinker** | Actual answers from identified base/adapter under recorded settings |
| Private generation/review records | Ignored `runs/` directories | Request slots, native completion diagnostics, cost reservations, blinded answers and review bindings; not public chat logs |
| Semantic/source review | Local review packets, then case-level public summaries in [`reports/`](../reports/) | Comparison against source-based criteria; AI judgments are labeled, specialist review is separate |
| Product checks | Local browser preview and source drawer | Chat/follow-up behavior and visible evidence; engineering smoke checks are not a benchmark |
| Public reporting | [`docs/`](./), [`evals/`](../evals/), [`manifests/`](../manifests/), [`reports/`](../reports/) after disclosure/rights review | Inspectable methods/results, including uncertainty and negative results |

There is no external evaluation dashboard or hosted judging service configured. Generation is remote; preparation, scoring integration and reports are local. A public repository does not imply public credentials, checkpoint receipts, draft sources or user conversations.

## Existing evaluations: read them, do not rerun them

Counts below are dataset rows, not necessarily the number of paid requests in every historical run. Settings and collection completeness belong to each protocol/report.

| Dataset | Rows | Protocol / results | Runner reference |
|---|---:|---|---|
| [`pilot-v1.jsonl`](../evals/pilot-v1.jsonl) | 40 | [Baseline guide](BASELINE-EVALUATION.md), [native Tinker baseline](TINKER-BASELINE.md), [baseline findings](BASELINE-RESULTS-2026-09-05.md) | `bibleprep/tinker_evaluate.py`; generic `evaluate.py` has older non-Tinker defaults |
| [`comparison-v1.jsonl`](../evals/comparison-v1.jsonl) | 16 | [Earlier model comparison](MODEL-COMPARISON.md), [`model-comparison-v1.json`](../reports/model-comparison-v1.json) | `bibleprep/tinker_compare.py` |
| [`comparison-large-v1.jsonl`](../evals/comparison-large-v1.jsonl) | 24 | [Large-model comparison](LARGE-MODEL-COMPARISON.md); later [B adaptation review](INKLING-ADAPTATION-RESULTS.md) and [repeat control](../reports/inkling-repeat-control-v1.json) | `tinker_compare.py`, `evaluate_adapter.py` |
| [`instruction-comparison-v1.jsonl`](../evals/instruction-comparison-v1.jsonl) | 24 | [`instruction-evaluation-v1.json`](../manifests/instruction-evaluation-v1.json), [A/B/C/D results](INKLING-INSTRUCTION-RESULTS.md), [answer review](../reports/inkling-instruction-answer-review-v1.json) | `bibleprep/evaluate_instruction.py` |
| [`instruction-calibration-v2.jsonl`](../evals/instruction-calibration-v2.jsonl) | 30 | [`instruction-calibration-evaluation-v2.json`](../manifests/instruction-calibration-evaluation-v2.json), [A/B/D/E results](INKLING-CALIBRATION-V2.md), [answer review](../reports/inkling-instruction-calibration-answer-review-v2.json) | `bibleprep/evaluate_instruction_calibration.py` |
| [`instruction-target-revision-v3.jsonl`](../evals/instruction-target-revision-v3.jsonl) | 30 | [`instruction-target-revision-evaluation-v3.json`](../manifests/instruction-target-revision-evaluation-v3.json), [A/B/E/F results](INKLING-REVISION-RESULTS-V3.md), [available-answer review](../reports/inkling-instruction-target-revision-available-answer-review-v3.json) | `bibleprep/evaluate_instruction_revision.py` |

V1 instruction evaluation has 24 Bible questions. V2 and v3 each have 24 Bible questions plus six simple general-English fixtures. V3 A/B/F completed 30 each. E returned four answers, then one request failure and 25 unsubmitted slots; all 94 returned answers were reviewed. Do not treat missing E answers as semantic failures or extrapolate its four-case comparison to thirty.

The v3 private collection/integration work is indexed by `runs/instruction-v3-execution/`. Its preserved `integrate_available_reviews_v3_fix1.py` corrected integration accounting; the original script and separate repair protocol remain. These are audit references, not a general evaluation command. Follow the public report's receipt bindings when investigating a particular result; do not dump private native output or reasoning into the conversation.

Original-language held-out loss is recorded in [the training report](INKLING-TRAINING.md) and [adaptation report](../reports/inkling-adaptation-v1.json). It is a separate signal from English-answer evaluation. The current chat's four live constructed requests are described in [PRIVATE-CHAT.md](PRIVATE-CHAT.md), with private engineering records in `runs/chat-preview-v1/`. The eight evidence records and their validators live in a different preparation track, documented in [EVIDENCE-FIRST-PACK.md](EVIDENCE-FIRST-PACK.md).

## Commands that work now

Run from the project root using the prepared `.venv`. These are **offline checks**; choose those relevant to the change. Do not rerun the full suite for a documentation-only edit.

```sh
# Draft structure and private source-hash checks; summary only, no model call.
.venv/bin/python -m bibleprep.evidence

# Draft validator changes.
.venv/bin/python -m unittest tests.test_evidence -v

# Private review export changes (implemented P1).
.venv/bin/python -m unittest tests.test_evidence_review -v

# Separate component eligibility registry/projection (implemented P2 tooling).
.venv/bin/python -m unittest tests.test_evidence_eligibility -v

# Constructed evidence planner and normalized collection accounting.
.venv/bin/python -m unittest tests.test_evaluate_evidence tests.test_evidence_collection -v

# Constructed native-result and frozen blinded-review handling; no live transport.
.venv/bin/python -m unittest tests.test_evidence_native tests.test_evidence_blinded_review -v

# Constructed exact native requests, paired preferences and declared collection gate.
.venv/bin/python -m unittest tests.test_evidence_requests tests.test_evidence_pairwise -v

# Source lookup and numbering changes.
.venv/bin/python -m unittest tests.test_chat_sources -v

# Chat inference/HTTP changes; transports are mocked.
.venv/bin/python -m unittest tests.test_chat_model tests.test_chat_server tests.test_chat_server_review -v

# Native diagnostics or v3-style sampling/accounting changes.
.venv/bin/python -m unittest tests.test_native_diagnostics_v1 tests.test_evaluate_instruction_revision tests.test_summarize_instruction_revision_partial -v

# Inspect the historical runner's actual options, without generating.
.venv/bin/python -m bibleprep.evaluate_instruction_revision --help
```

For a saved evidence receipt, use `--out runs/<new-run-name>/<new-receipt-name>.json`, replacing both placeholders. The validator requires a new filename in a private directory and refuses overwrite. Do not write detailed records into public `reports/`.

The implemented [evidence review export](EVIDENCE-REVIEW.md) adds private JSON and standalone HTML with a traceable issue queue. Use `.venv/bin/python -m bibleprep.evidence_review --out-dir runs/<new-review-directory>` with a new directory name. The current completed packet is `runs/evidence-review-v1/final/`; do not overwrite it. Combined validator/review tests passed 22 cases. This is source-preparation tooling, not the proposed model-comparison runner below.

To use the already prepared private chat:

```sh
.venv/bin/python -m bibleprep.chat_server --port 8765 --budget 5
```

Opening [the local page](http://127.0.0.1:8765/) is not a generation request; submitting a question spends provider sampling funds. The allowance is estimated per process, resets on restart and is not an account cap. If a server is already running, use it rather than starting a duplicate. Use only constructed examples for recorded engineering checks. User conversations are not evaluation fixtures or training data by default.

Do not add `--execute` to historical training/evaluation commands as a way to “continue.” They encode completed, version-specific experiments; some reject a second attempt and deliberately do not support resume. The generic `bibleprep.evaluate` defaults to an older Groq/gpt-oss setup and is not the selected B runner.

## Completed pilot and later broader design

Six GT01/AT03 components have conditional private delivery decisions. The completed pilot used [notice-complete delivery](EVIDENCE-NOTICE-DELIVERY.md), exact native requests and the [single-run pilot runner](EVIDENCE-PILOT-RUNNER.md). Run its focused checks with `.venv/bin/python -m unittest tests.test_evidence_pilot -v`. Its questions are now development material. The completed guidance comparison separately used six selected components across HT01, HT07 and GC01 with the exact v4 notice manifest. The larger historical-evidence design below remains proposed and is separate from the authorized Candidate G sequence.

**Later broader question:** Does reviewed evidence improve B's English answers, and are failures caused by missing evidence, retrieval or interpretation?

`bibleprep.evaluate_evidence` remains a constructed offline planner with no live execute option. `bibleprep.evidence_pilot` is the separate, frozen single-run native boundary used for the completed known-topic pilot; it is not a generic benchmark interface. `manifests/evidence-evaluation-v1.json` and `reports/evidence-comparison-v1.json` remain proposed artifacts for a later broader evaluation. Keep future concealed questions, criteria and answers in a new ignored run directory until exposure and publication decisions are recorded; publish only portable hashes, counts and limitations.

| Condition | Weights | Input evidence | Comparison purpose |
|---|---|---|---|
| B-memory | Retained B | None | Same model without a supplied source packet |
| B-packet | Same B | Fixed, reviewed eligible packet selected before generation | Whether B can use the relevant evidence when supplied |
| B-lookup | Same B | The frozen lookup policy's actual output | Whether the implemented source selection supplies enough relevant context |
| A-matched, optional | Contemporary unchanged full Inkling | Same fixed packet as B-packet | Needed for a fresh claim that fine-tuning itself helps under matched evidence |

Keep the system instruction and sampling settings identical where possible; the declared evidence input is the treatment. Do not disable sources in the user’s running chat to collect a control. Implement controls in the evaluation runner. A packet must not contain expected answers or scoring criteria. Unavailable eligible evidence is a recorded limitation, not permission to invent or silently import it.

Start with a proposed **30 single-turn cases**: eight primarily Hebrew, six Aramaic, six Greek, four broad/application cases and six general-English controls. Across the twenty language cases include complete translation, grammar, textual alternatives, historical-context claims and dating distinctions; tags may overlap, row counts may not. Select exact passages only after checking eligible evidence and exclusions. Three core conditions mean **90 planned requests**; adding A-matched makes **120**. This allocation is a starting design, not a frozen or authorized run.

General controls check retained ordinary abilities, not biblical expertise; the same six cases may have identical no-evidence inputs across the core conditions, which should be reported as repeat controls rather than independent evidence benefits. Add a separately specified conversational suite for follow-ups, numbering changes, reference replacement and broad questions with no reference. Count every turn as a request and include it in the cap; do not silently append live browser checks to the model benchmark.

The eight prepared starter topics may support a useful **development** comparison. Questions about those familiar records do not become an independent final test by being reworded. Reserve distinct passage/witness/issue families for a later fresh generalization check. If limited Aramaic coverage requires family reuse, declare the overlap and narrow the claim instead of promising clean independence.

## Freeze sequence and leakage controls

1. State the hypothesis, primary comparison and eligible source snapshot. Record what existing B training, prior SFT, known evals and development work have exposed. Unknown base pretraining cannot be excluded retroactively.
2. Have an evaluation author prepare questions, source-based expected behavior, acceptable alternatives, critical errors and category labels without consulting candidate answers. The training/prompt author receives only exclusion metadata until their artifact is frozen. In a shared repository this is procedural separation, not access control. If separation is unavailable, label the work development-only.
3. Reserve source/passage/witness families and near-duplicate questions. For a future training change, exclude these from the new training/validation material and audit quotations/overlap. Record inherited exposure in B rather than calling the entire base unseen. Do not mix English and MT numbering in exclusion keys.
4. Independently check criteria against exact source locators and record reviewer qualifications. Where qualified review is pending, report AI source review honestly; it cannot certify reconstructed wording. Resolve material pre-output defects with new versioned artifacts.
5. Freeze questions/criteria hashes, source/use snapshots, prompt and lookup code hashes, checkpoint identity, tokenizer/native renderer versions, fixed settings, case/arm order, stop rules, review method and estimated cap **before any candidate generation**. Conceal answers and arm labels from reviewers until their judgments are frozen.
6. Run the offline dry run and validate its planned slot inventory. Obtain any missing execution allowance for the concrete paid plan, then sample each planned slot once. Keep the label key private until integration.

The current native chat defaults provide a reference: effort 0.7, temperature 0, seed 20260905, output ceiling 8,192 tokens and whole-operation deadline 300 seconds. The chat input ceiling is 24,000; older matched evals use 6,000. Choose the new input bound based on actual packets and freeze it; do not inherit mismatched limits silently. Output allowance includes native reasoning, so an answer can be incomplete even with few visible final tokens. Private raw diagnostics remain separate from final answers.

Before a paid run, verify current official prices. Reserve worst-case cost for **every** planned request from input/output ceilings, plus explicitly described storage and uncertainty contingencies. Reconcile returned token estimates and provider invoice separately. Existing $10 experiments, the chat's $5 process allowance and the Candidate G authorization do not authorize this separate proposed historical-evidence benchmark.

## Judging and decision rules

Use per-case source review and masked paired preferences; do not rank models by training loss, speed, string similarity or a single judge's overall score. Record the following separately:

| Dimension | Evidence to inspect |
|---|---|
| Translation/grammar | All requested clauses; negation, agency, condition, aspect/voice where relevant; acceptable English alternatives |
| Textual accuracy | Which edition or witness actually attests a reading; omission versus lacuna; corrections, ketiv/qere and editorial brackets |
| Historical context | Claim supported by the cited source; reported scholarship versus inspected primary evidence; composition/event/witness/edition dates kept distinct |
| Source use | Relevant packet retrieved, claim supported at locator, contrary evidence retained, no invented citations or claims of verification |
| Question intent | Focused textual answer or useful Bible-based reflection as asked; contemporary application distinguished without a mandatory lecture |
| Completion and dialogue | Required content supplied, limits/errors disclosed, reference inheritance correct, no answer-selection retries |
| General retention | Semantic correctness on controls; valid alternate phrasing is not a failure |

Predeclare a severity rubric. Critical examples include reversed negation that changes meaning, fabricated manuscript attestation, invented quotation attribution, and unsafe certainty in a personal reflection. Distinguish these from a reasonable disputed translation and from a missing provider response.

Suggested promotion gate for the **limited private evidence feature**: zero observed critical errors, no increase in requested-content omissions on matched completed Bible cases, more preferred than less-preferred answers for the primary comparison, and no semantic regression on general controls. Freeze the exact gate before generation. A tie or failed gate means retain the current default and diagnose; it does not justify extra sampling until a win appears. Passing a small AI-reviewed set is not a public accuracy certification or evidence of error-free behavior elsewhere.

Also predeclare a collection-completeness gate across all planned slots. A condition must not appear better merely because its hardest requests failed or never returned a complete answer. Count critical errors in all returned reviewable content, including partial answers. If collection cannot satisfy the frozen completeness requirement, report the decision as inconclusive even if preferences on a smaller completed subset are favorable.

Report preferences/ties and completion by category, with matched denominators, all planned slots and failure dispositions. Show B-packet versus B-memory separately from B-lookup versus B-packet. Retrieval hit/coverage measures and byte hashes are engineering metrics, not proof of historical correctness. For public claims, add qualified review of textual/linguistic judgments and a fresh evaluation beyond the familiar development topics.

## Failures, reports and reproduction

Journal each request before submission. Preserve native stop reason, final-content presence, generated token count and estimated/reserved cost, including output-limit responses. Do not automatically resubmit a timeout or uncertain failure. Stop according to the frozen arm/run rule. Missing, unsubmitted and returned-but-incomplete are separate states.

Review all returned final answers, including partial ones. Keep review inputs bound to native receipt hashes, freeze reviews before unmasking, and disclose reviewer role overlap. If a tooling defect or collection failure needs a contingency, preserve the original protocol/output and record a separate correction with its timing; never retroactively claim it was predeclared.

Write a new private run directory and a shareable report containing the hypothesis, versions/hashes, exposure caveats, settings, planned/completed counts, category results, failures, costs, decision and limitations. Publish question text only after it is retired from concealment and its source rights permit publication. Hidden model reasoning, live checkpoint locations, credentials and personal conversations remain private. Update [DECISIONS.md](DECISIONS.md) and the [living state](../manifests/execution-state.json); preserve all historical reports.


## Current attribution-guidance comparison

The [new method](GUIDANCE-COMPARISON-COLLECTION.md) is implemented and frozen. Six Bible questions use exactly the selected HT01/HT07/GC01 components from the v4 registry and guidance-comparison notice manifest. Two general controls have empty evidence. Each question receives `B-original` and `B-guided` inputs with the same checkpoint, evidence and sampling settings; the only prompt difference is the versioned guidance. This tests guidance, not fine-tuning or retrieval benefit.

Private operational records:

- Implementation freeze and engineering evidence: `runs/guidance-collector-v1/`.
- Eight questions, checked criteria and source/exposure review: `runs/guidance-collector-v1/evaluation/`.
- Active protocol: `runs/guidance-comparison-v1/protocol-v2.json`, SHA-256 `8198f82a8b1a638487f524d4910868007155b17fdd47f9857e179392d15c6b78`.
- Native request inventory and preparation receipt: `runs/guidance-comparison-v1/prepared-native.json` and `preparation-receipt.json`.
- Existing one-shot collection: `runs/guidance-comparison-v1/live/`. Inspect it; do not rerun, resume or overwrite it.
- Completed masked review: `runs/guidance-comparison-v1/review/` contains both packets, frozen individual/paired judgments, the pre-map receipt and `integration.json`. Packet generation and integration have already run; preserve them, do not execute them again.

The selected passages were in B's raw-text training and all three families were previously researched. The new questions are development evidence, not an unseen-source generalization benchmark. There is no Aramaic coverage in this bounded comparison.

Review every valid final answer, including partials, and every material factual assertion. Check extra claims against appropriate primary sources: absence from the selected input is not proof of falsehood. Record unsupported attribution, a source-only scope violation, and unresolved factual verification separately. Practical safety counsel can be contemporary application. Judge ordinary controls semantically; formatting lapses are distinct from comprehension failures. Do not require raw project identifiers in normal conversational prose.

For a positive proposed-trial result, require all sixteen answers and six Bible pairs complete, zero guided material errors, unresolved material assertions, attribution/scope errors and requested-content omissions, more guided Bible preferences than original preferences, and all four general-control answers semantically correct. The stricter rule was selected before the questions and outputs. Smaller constructed tests cannot return this recommendation. Any positive development result still requires a separate product decision; it does not authorize training or establish expert accuracy.

Focused offline checks: `.venv/bin/python -m unittest tests.test_guidance_collection tests.test_guidance_review -v`. The accepted run passed fifteen tests plus parent source/native and masked-review integration. Keep earlier protocols and tools unchanged.

Actual result: sixteen complete/native-verified answers, all sixteen individually reviewed, six Bible pairs and four semantically correct controls. Guided preferences were 1 / 2 / 3 and two guided attribution findings failed the gate. Estimated sampling cost was $0.09301348. See [the result and review limitations](GUIDANCE-COMPARISON-RESULTS.md). Candidate G's separate evaluation covers Aramaic as well as Hebrew, Greek, application and general retention; all thirty cases passed independent source review and are now frozen.

## Completed Candidate G comparison

The [G source/row plan](CANDIDATE-G-DATA-PLAN.md) is mechanically and source-bound checked. Its 24 validation slots are target-loss data, separate from the thirty fresh B/G answer questions. All 104 new English target rows passed independent AI review; sixteen exact prior training rows supply rehearsal. The resulting 96/24 dataset, six-update recipe and collector were frozen before the fresh questions were authored. Planning and mechanical checks remain distinct from scholarly certification.

The thirty questions cover ten Hebrew, eight Greek, six Aramaic and six general-English cases. Independent source review passed all thirty cases and 67 cited verses. The final evaluation SHA-256 is `450606703aa454f9d0fcf7715e8da6ee2456942367355d8b7e7428c237b8afc4`; its corrected question-set SHA-256 is `8e5ccbca37a06878b6ae7ff7076b2cb9cbc30d07c4ec692703d3b58db902ce4b`. All Bible evaluation verses were in B's raw-text training; Daniel 4 and Ezra 6 were also used in earlier development or validation work, and John 9 shares a prior source family. Report the set as new questions and development evidence, not unseen-source generalization.

The source review, current preflight, exact notice and evaluation freeze were completed before training. G then completed exactly six updates, both full checkpoints were saved and all four required B/G checkpoint roles were verified. All 60 native answers completed without retry or recollection. Two fresh GPT 5.6 Sol reviewers who authored neither targets nor questions froze all 60 individual and 30 paired judgments before label integration.

The frozen collection rule had sixty planned slots and would stop on the first uncertain, partial or malformed response, including a transport error without text, with no retry, resume or recollection. No such stop occurred: 60/60 answers completed and were reviewed. Identity masking remained procedural, and style may still have revealed an arm.

Every predeclared promotion and retention gate remained unchanged. G/B/tie was 3/10/11 across the 24 Bible pairs; both models answered all six general controls correctly. Retention passed, while the preference gate failed independently, so B remains selected. Finding counts are AI-review flags, not factual-accuracy scores; root review disputes the James material-error flag for both arms and treats some omissions as rubric/notice-level. Preserve those qualifications in the severity audit without revising the frozen decision. The [final result](CANDIDATE-G-RESULTS.md) also records the one-sample variability and source-exposure limits. Do not recollect or begin another training iteration automatically.
