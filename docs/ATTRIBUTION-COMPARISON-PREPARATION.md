# Inkling attribution comparison preparation

September 9, 2026. The owner accepted continuing with retained Inkling B. Recurrence remains optional research and is not a prerequisite for another Inkling fine-tune. This increment prepares the next evidence-guidance comparison; no new model answers or training results are reported.

## What the comparison will test

The [completed pilot](EVIDENCE-PILOT-V1.md) exposed a source-range error and a project-translation attribution error outside its original narrow grading criteria. The [versioned guidance](EVIDENCE-ANSWER-CONTEXT.md) addresses those distinctions. Compare the existing system prompt with that prompt plus the guidance, holding the question, evidence and model fixed.

The proposed inventory remains six Bible questions across three families and two general controls, each in two conditions: sixteen answers. This tests guidance on an already fine-tuned model. It does not isolate the benefit of fine-tuning, compare retrieval methods, or establish whole-Bible accuracy. Follow the [evaluation runbook](EVALUATION-RUNBOOK.md) for the actual prospective protocol and review criteria.

## Selected source scope

The minimal selection consists of an edition observation and an original-language/project-English reading for each family:

| Family | Selected content | Limits |
|---|---|---|
| HT01: Genesis 4:8 | The [pinned WLC](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Gen.xml) speech introduction and field setting; exact main/ketiv verse text and the identified project rendering. | Does not establish why the speech content is absent or which wording is earliest. |
| HT07: Isaiah 53:11 | The [selected WLC](https://raw.githubusercontent.com/openscriptures/morphhb/3d15126fb1ef74867fc1434be1942e837932691f/wlc/Isa.xml) seeing/satisfaction sequence and exact verse text with the identified project rendering. | The selected line lacks the noun translated “light”; other witness readings and contested grammatical choices require separate evidence. |
| GC01: Luke 3:1 | The [selected SBLGNT](https://raw.githubusercontent.com/LogosBible/SBLGNT/c4d241a9c1c479a55b989ba35a4976c1d0b8052c/data/sblgnt/text/Luke.txt) clause describing Pilate's governing activity, with its identified project rendering. | Does not itself name a Latin administrative office or supply the whole verse. |

These families were not in the Mark/Daniel evidence pilot, but they were already researched in this project. All three selected passages occur in B's original-text training split. Earlier English instruction material also covered Genesis 4:6–7; that material was not trained into B, but it creates additional project-author exposure to the chapter. The checked prepared English splits contained no Isaiah 53 or Luke 3 row. New questions about these families constitute a controlled development comparison, not an unseen-source generalization test. Source-corpus exposure, prior English training/evaluation exposure and new-question disclosure must be recorded separately.

The Hebrew original strings were checked against fresh parsing of the pinned source XML. An independent AI source review checked the Luke clause and its project English. These are narrow AI checks with disclosed project-role overlap, not human specialist certification. The wider Qumran/Samaritan findings and Pilate inscription remain outside the minimal selection; their review and use questions are separate.

## Verified private delivery

The new private v4 registry records narrow scholarly reviews and conditional model-input/display decisions for these six components. It preserves all 83 component identities and source hashes and leaves the other 77 component records unchanged. Across the registry, twelve components now have conditional private display/input decisions; training, redistribution and adapter-release decisions remain pending for all 83 historical-evidence components.

The new notice manifest contains eight entries: the four original notices unchanged and four new notices covering eight required associations for the selected six components. Exact source-specific changes and project English authorship remain visible. The earlier six approved components continue to require their original manifest; copying its notices into the new manifest does not silently rebind those earlier decisions.

Parent integration verified three constructed source pairs and one empty-evidence control, including fresh dependency checks, identical evidence/question bytes, and regeneration. It also confirmed that the old six components still work with their original notices. These are eight prepared input objects, not generated answers or the proposed sixteen-slot evaluation. No source has entered the private chat.

## New offline input preparation

[`evidence_guidance_comparison.py`](../bibleprep/evidence_guidance_comparison.py) prepares explicit `B-original` and `B-guided` conditions. Each evidence-bearing preparation repeats current source, review, use and notice verification. It checks the exact component selection, preserves the question and complete evidence bytes, and permits only the versioned guidance difference in the system prompt. The returned inventory binds the inputs, source selection, registry, notices, guidance and implementation hashes. Regeneration rejects a modified saved pair.

General controls have empty evidence in both conditions; the guided control still receives the same generic guidance. They do not fabricate an empty approved source bundle. The helper has no provider transport, native tokenizer renderer, credentials, file writer, chat integration or training operation.

Six new constructed tests and the upstream answer-context and delivery compatibility checks passed, seventeen tests in total. They cover identical evidence/question bytes, guidance-only differences, empty controls, stale dependencies, invalid selections and tampering. Independent review found that an already-guided base prompt could produce a misleading once-versus-twice comparison; the helper now rejects that setup, with regression checks for evidence and control cases. The final independent review found no remaining material issue within this helper's scope. These checks establish software behavior, not answer quality.

The completed pilot's request, collection and review tools assume three different conditions. The new two-condition helper does not silently reuse those labels or become a live runner. A versioned two-condition native preparation/collection/review path still needs to bind exact prompts, settings, requests, costs, all planned slots and partial/failure outcomes.

The next implementation should reuse the pinned native renderer and diagnostic primitives while giving this comparison its own two-condition inventory. Exercise complete, output-limited, uncertain and unsubmitted outcomes with constructed inputs first. Interleave the conditions under a recorded order, reserve the full run cost before collection, preserve every returned final answer, and freeze individual and paired reviews before revealing condition labels. Do not rewrite the old pilot's arm names or receipts to accommodate this experiment.

## Before generation or training

The minimal source delivery package is ready for private use under its recorded conditions. Finish and check the two-condition native collection/review path, freeze that comparison implementation, then author and independently review the eight new questions and expected coverage. Freeze the full protocol before generating answers. Check the retained B checkpoint and current inference costs at execution time. Review every material assertion, including volunteered claims, rather than checking requested coverage alone.

Source eligibility, prepared inputs and passing software checks do not demonstrate that the guidance works. Promotion requires the prospective answer comparison. Use any remaining failures to choose a distinct candidate G training hypothesis, with reviewed data, fresh evaluation and an explicit cost estimate. Present that proposal before training. The existing B model, chat and frozen experiments remain unchanged.

Private preparation records are under `runs/attribution-comparison-prep-v1/`; source records, reviews and prepared evidence stay excluded from publication. The living queue is [`execution-state.json`](../manifests/execution-state.json).
