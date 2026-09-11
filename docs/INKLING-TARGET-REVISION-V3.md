# English target revision v3

**Data prepared September 6, 2026; the preparation itself made no training calls.** The subsequently authorized [controlled F comparison is now complete](INKLING-REVISION-RESULTS-V3.md) and retains B provisionally, with E/F preserved. This document records preparation and the historical proposal. An audit of all 120 English instruction examples found a gap in the kinds of tasks represented, rather than clear factual errors in the existing answers. Fourteen training examples explicitly request a complete translation of their supplied passage followed by the original textual explanation.

The [gentler calibration](INKLING-CALIBRATION-V2.md) produced complete native answers on all 30 questions, but E omitted requested content in three Bible answers and did not clearly improve on B. That motivates this revision. It does not establish that the training examples caused those omissions or that broader targets will fix them.

## What the audit found

| Subset | Examples audited | Finding | Revision |
|---|---:|---|---|
| Hebrew textual | 40 | No explicit request to translate the entire supplied passage | Expand eight training prompts and answers |
| Aramaic textual | 24 | Every example supplies one verse; one already requests a whole-verse translation and two request selected parts | Expand four training tasks to cover their entire existing verse |
| Greek textual | 40 | The two explicit complete multi-verse translation tasks were both reserved for validation | Expand two training prompts and answers |
| Life application | 16 | The targets fit their questions and distinguish contextual meaning from reflection | Preserve all examples |

All original targets were assessed as adequate for their actual requests, with no clear material factual error found. A narrow grammar answer is not defective merely because its prompt supplies a longer passage. This is an AI audit, not proof of error-free data or human scholarly certification. The [case-level audit](../reports/instruction-target-audit-v3.json) records each decision and the hashes of the private review evidence.

The dataset remains **104 training examples and 16 validation examples**. Exactly 14 training examples change; the other 90 training examples and all 16 validation examples retain their original bytes. Source references, exact ancient text, edition layers, IDs, ordering, chapter groups and split remain unchanged. All application examples retain the accepted intent-based behavior. No user conversations or reasoning traces are added.

| Revised training IDs | Added coverage |
|---|---|
| IH004, IH006, IH013, IH021, IH028, IH031, IH037, IH040 | Complete existing Hebrew passages, followed by the existing focused explanation |
| IA004, IA006, IA010, IA020 | All clauses of each existing Aramaic verse, including speakers, commands, negation and reported action |
| IG002, IG035 | Complete existing Greek passages, followed by grammar explanations |

The ten Hebrew/Greek additions cover multiple verses. The four Aramaic additions cover individual verses; this revision still contains no multi-verse Aramaic training task. Extending its source spans would change the source-exposure inventory and requires a separate design.

## Source review and preservation

Each changed example was checked by an AI reviewer other than its author against the pinned original-language passage and relevant occurrence annotations. The review binds the full candidate content, including prompt, answer, source metadata and notes. All fourteen received approval before assembly. Reviewers share project context and have other project roles; this is not an independent human panel.

Translations were composed for the exact supplied source text. Written/read alternatives and editorial layers were preserved. For example, Ruth's oath uses an explicitly explained idiomatic English rendering, Psalm 51 retains a defensible grammatical construction, and Job's supplied written form remains intact in the evidence. Multiple defensible translations should not be scored as wrong solely for differing wording.

The revised dataset was frozen before its authors accessed the new evaluation questions or criteria. The frozen dataset hash is `5603342caed02a6b3210d554e131d6b8955fdb17601dff6e7e1a388880de5be2`. Authored drafts, review receipts and complete training rows remain local and excluded from publication pending data-release review; public manifests and aggregate findings preserve the methodological record. This release state is not a fully reproducible public SFT dataset.

## Verified local preparation

The [revision plan](../manifests/instruction-revision-plan-v3.json) and [preparation manifest](../manifests/preparation-instruction-v3.json) bind the original and revised data, all fourteen approvals, exact source versions and the unchanged native renderer. The new versioned preparer checks the original preparation first, rejects unreviewed or out-of-scope changes, then rebuilds the native training sequences without API calls.

| Artifact | Examples | Input positions | Supervised positions | Maximum input length |
|---|---:|---:|---:|---:|
| Revised training | 104 | 65,573 | 16,598 | 1,425 |
| Unchanged validation | 16 | 10,837 | 2,344 | 1,504 |

Training adds 1,419 input positions and 1,044 supervised positions relative to v1. All examples fit the 8,192-token limit without truncation. Native effort 0.7, final-only targets, masked prompts, exactly one target shift and unnormalized source Unicode remain unchanged. Fifteen focused tests passed, including real native rendering and rejection of stale reviews, changed validation, changed sources, token corruption and accidental overwrite. A separate code review found no material issue, and the actual written artifacts passed deterministic offline verification. All fourteen frozen v2 runtime/dependency hashes remain unchanged.

With the locally retained reviewed inputs and pinned dependencies, preparation and verification run from the repository root:

```sh
.venv/bin/python -m bibleprep.prepare_instruction_revision --plan manifests/instruction-revision-plan-v3.json
.venv/bin/python -m bibleprep.prepare_instruction_revision --plan manifests/instruction-revision-plan-v3.json --verify
```

The first command refuses to overwrite an existing preparation. The second rebuilds in memory and verifies the saved artifacts. Both operate without model calls. These commands cannot yet reproduce the full SFT dataset from a public clone because the reviewed input rows and private review receipts have not been released.

## Fresh evaluation

The [frozen evaluation](../manifests/instruction-target-revision-evaluation-v3.json) has **30 cases: seven Hebrew, seven Aramaic, six Greek, four application and six general-English fixtures**. Its 19 supporting chapter families avoid all 102 English SFT training/validation families. Its explicit supporting verses and prompts also avoid all five prior evaluation datasets. Source checks cover 65 referenced verses against 18 pinned source files.

All 19 chapter families were present in the completed original-text training split, and the base model's prior exposure is unknown. This tests new questions about previously exposed sources; it is not an unseen-text evaluation. The seven Aramaic cases are clustered in two chapter families used in earlier evaluations, although their explicit verses are fresh. That constraint limits conclusions about broader Aramaic transfer.

The evaluation uses documented source-excerpt extraction. OSHB excerpts preserve direct main/ketiv words, remove slash separators, and omit separate punctuation/note/qere elements; the resulting serialization differs from training's processed verse text. This does not silently change the training corpus. The [separate pre-output review](../manifests/instruction-target-revision-criteria-review-v3.json) approved all 30 cases and records acceptable alternative translations, annotation exceptions and scoring clarifications before any model answers existed. Its supplement was bound to the execution protocol; no material prompt defect was found.

The preparation plan binds the strict, question-free [compatible exclusion inventory](../manifests/instruction-target-revision-exclusions-v3-compatible.json). An earlier inventory contained additional metadata rejected by the strict loader; it and a later equivalent projection are retained as freeze records. Only the compatible inventory referenced by the plan is operative. Evaluation questions and scoring criteria are never opened by the training-data preparer.

## Historical comparison proposal

The following proposal predates execution; current results, reservations, corrected sampling seed and the incomplete E collection are recorded in the [completed comparison](INKLING-REVISION-RESULTS-V3.md).

The next bounded experiment would train **F from B**, with a fresh optimizer and the same gentle settings used for E: rank 8, learning rate 2e-5, batch size 16, the same example order, and one epoch of seven updates. The change is the reviewed dataset version. F would not continue from E, because that would also change the amount of prior English training.

Compare contemporary **A, B, E and F** once each on the fresh 30-question set: 24 Bible questions and six constructed general-English fixtures. Keep source accuracy, requested-content coverage, native completion, task focus and life-application quality separate. General fixtures should use fixed codes, numeric answers or structured values, with semantic review distinct from exact formatting checks. Review all final or structurally available partial answers with concealed arm labels; avoid selective retries or choosing the winner from validation loss, latency or answer length.

This is a bundled data-composition test: prompt scope, target length and supervised-token volume change together. It cannot isolate translation coverage from answer length or prove broad historical expertise. Prior raw-text and base-model exposure, repeated development cycles, limited Aramaic chapter diversity and AI reviewer overlap remain limitations.

At the preparation-phase September 6 pricing check, one revised training epoch plus two validation forwards conservatively priced at the training rate estimated **$0.49**. A four-arm, 120-request evaluation reserved at the full 6,000-input/8,192-output token ceilings estimated **$5.95**. Adding **$3 checkpoint/storage contingency** gave a conservative **$9.44 proposal within a $10 local cap**. Nothing had been reserved or spent during this proposal phase. The later execution separately rechecked prices and reserved up to $6 for sampling. [Historical cost assumptions and prerequisites](../reports/instruction-revision-proposal-v3.json), [official Tinker prices](https://tinker-docs.thinkingmachines.ai/tinker/models/).

At the end of preparation, execution still required a separately frozen protocol, verified checkpoint receipts and current pricing before paid submission. Those prerequisites and the authorized comparison were subsequently completed and are documented separately. No training, sampling, budget reservation, harness, deployment or publication occurred during this preparation phase. The source editions still do not constitute a complete manuscript apparatus or a reconstruction of all earliest readings.
