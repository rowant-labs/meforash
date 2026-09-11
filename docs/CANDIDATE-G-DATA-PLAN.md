# Candidate G source and data plan

September 9, 2026. The candidate G source and row plan is prepared for reviewed target authoring. It defines **96 training rows and 24 validation rows**. No new questions or English target answers have been authored, no training data has been compiled, and no new training or model sampling has occurred.

G would start from retained original-language Inkling B. Its proposed purpose is to improve English answers from accurately identified biblical evidence: complete explanations, honest translation attribution, evidence limits and useful reflection when requested. The [earlier guidance comparison](GUIDANCE-COMPARISON-RESULTS.md) did not establish an improvement, so its extra prompt is not being adopted. This is a new supervision hypothesis, not a new architecture or a demonstrated solution.

## Concrete inventory

| Language | New training chapter families | New validation chapter families | Planned training rows, including rehearsal | Planned validation rows |
|---|---:|---:|---:|---:|
| Hebrew | 22 | 6 | 50 | 12 |
| Greek | 14 | 4 | 34 | 8 |
| Aramaic | 4 | 2 | 12 | 4 |
| **Total** | **40** | **12** | **96** | **24** |

Each new family contributes two planned rows. The 80 new training rows comprise 40 direct textual/explanation tasks, 24 attribution/boundary tasks and 16 intent tasks. The intent group uses eight family pairs, intended to contrast focused textual questions with questions inviting contemporary reflection. Sixteen existing training examples are selected for rehearsal. Validation has 12 direct, six boundary and six intent rows on separate chapters.

The selected coverage spans 1,419 unique verse IDs across the new families and rehearsal references. These are source coverage envelopes, not finalized model inputs or 1,419 authored examples. Later authors should select enough context for each question; final native rendering must satisfy the 8,192-position ceiling without silently truncating a passage or target. Chapter separation uses the pinned editions' coordinates, including the Hebrew Bible's source numbering.

The Aramaic training families are Daniel 2–3 and Ezra 4–5, restricted to their Aramaic spans. New validation uses Daniel 6–7. Mixed language boundaries are checked from the processed word-language annotations; a book's name does not determine the language of every verse. Daniel 4 and Ezra 6 remain protected historical English-validation chapters; Daniel 5 and Ezra 7 remain protected by the earlier frozen evaluation exclusions.

## Source and permitted-use scope

Use only the pinned WLC main/ketiv text encoded by OSHB and the selected SBLGNT Greek text layer. The OSHB notice identifies its underlying WLC text as public domain while licensing the OSHB work separately. SBLGNT's official license is CC BY 4.0. The planning decisions are limited to identified source-text inputs with their required provenance and notices; they are not blanket approval for every file or future target. [Pinned OSHB notice](https://github.com/openscriptures/morphhb/blob/3d15126fb1ef74867fc1434be1942e837932691f/LICENSE.md), [SBLGNT license](https://sblgnt.com/license/).

Keep morphology, definitions, apparatus, qere alternatives, historical dossiers and English targets outside these narrow input decisions. The 83 historical-evidence components retain their earlier pending training decisions. No existing registry or source text was changed. A new English rendering needs its own authorship, support review and use record; source-text eligibility does not establish its accuracy. Dataset redistribution and adapter release remain separate decisions.

This inventory does not add earlier manuscript witnesses or turn the selected editions into recovered autographs. It supports a controlled English-answer training hypothesis while the wider historical-evidence work remains open.

## Exposure and separation

All selected verse IDs were present in B's completed raw-text adaptation. This is therefore development on known source material, not unseen-text evaluation. The Hebrew and Greek new-family choices avoid matches in the checked earlier English-training and evaluation inventories. Absence of a match is limited to those inspected records; base-model pretraining and unrecorded semantic exposure remain unknown.

The scarce Aramaic chapters have earlier project exposure. In particular, the two new Aramaic validation families have explicit development-exposure exceptions. They remain disjoint from every G training and rehearsal chapter; the exception does not override protected historical holdouts. Do not describe them as pristine validation material.

The sixteen rehearsal selections come from the existing training split. Two otherwise available old training rows, IG028 and IH022, were excluded because they overlap protected raw-text holdouts. Existing validation examples and the earlier evaluation exclusion chapters are also excluded. The old reviewed and prepared row records are separately bound by hashes; JSONL record hashes exclude the line separator.

## What the checks establish

The [planning validator](../bibleprep/candidate_g_plan.py) checks exact counts, distinct canonical chapter families, language quotas, declared source/permission bindings, exclusions and training/validation separation including rehearsal. It rejects authored question/answer fields and claims that this plan is training-ready. Twelve constructed tests cover invalid plans and important boundary cases.

A separate actual-file check verifies source and notice hashes, selected verse IDs and chapter/language metadata, B-training membership and the exact sixteen prepared rehearsal records. Independent source/code review checks the supporting records. These checks validate the planning artifacts; they do not certify translation quality, legal conclusions or scholarly accuracy, and do not approve as-yet unwritten targets.

The machine-readable [public inventory](../manifests/candidate-g-data-plan-v1.json) contains source-family and row metadata without English target text, private checkpoint references or personal material. Detailed source/use decisions, raw/processed provenance, exposure records, authoring rubric and review receipts remain private under `runs/candidate-g-data-plan-v1/`.

## Next execution package

Prepare the target-record format and exact source excerpts/notices, then author the **104 new question/answer examples**: 80 for training and 24 for validation. Carry the sixteen selected rehearsal records forward with their exact provenance. Review targets independently in bounded batches, correcting unsupported assertions, missing requested material, translation attribution and inappropriate application before inclusion. Keep natural English explanations central; do not train repeated internal IDs or a blanket refusal to discuss broader questions.

Freeze the reviewed dataset and recipe before a separate author creates the fresh B/G evaluation. That evaluation must cover Hebrew, Greek, Aramaic, interpretation, application and general retention; these source/row planning checks are not that evaluation. Finally, present the exact token counts, complete cost reservation, frozen evaluation and remaining limitations to the owner **before any training**. The [preparation plan](CANDIDATE-G-PREPARATION.md) retains the provisional recipe and incomplete compute ceiling; no complete run budget exists yet.
