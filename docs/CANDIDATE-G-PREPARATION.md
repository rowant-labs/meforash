# Candidate G preparation plan

September 9, 2026. **Prepare the data first; do not train yet.** The next candidate would continue from the original-language fine-tuned Inkling B. It would keep the same architecture and test a distinct learning objective: accurate English answers from explicitly supplied biblical evidence, including translation provenance, evidence limits and question-appropriate reflection.

The [guidance comparison](GUIDANCE-COMPARISON-RESULTS.md) did not justify adopting its added prompt. Earlier E/F instruction passes also did not justify replacing B. Those small results motivate testing different supervision; they do not establish that another training run will help. Recurrence remains optional and deferred.

## Proposed data and recipe

The [source and row plan](CANDIDATE-G-DATA-PLAN.md) now defines **96 training examples and 24 new validation examples**. Source families and rehearsal records are checked; new questions and English targets remain unwritten. This is not a prepared or approved training dataset.

| Training group | Proposed rows |
|---|---:|
| Complete English answers from supplied original-language evidence | 40 |
| Rendering attribution, edition/witness distinctions and evidence boundaries | 24 |
| Paired textual and life-applicable questions, with the response matching intent | 16 |
| Reviewed rehearsal from existing Hebrew, Aramaic, Greek and application examples | 16 |

The 80 new training examples should cover at least 40 passage/source families. Validation needs additional disjoint families. Begin with the already pinned biblical editions and independently reviewed project explanations; this does not require collecting forty new manuscript witnesses. Set explicit Hebrew, Aramaic and Greek quotas after the source inventory. Keep the historical evidence gaps visible and do not create a single supposedly original text by combining readings.

Train only on checked final English answers, with input prompts masked from the loss and no reasoning traces. The provisional recipe follows the gentler E/F mechanics: B weights as parent, rank-8 LoRA, fresh optimizer, learning rate 0.00002, batch 16, one pass and six updates. Preserve the baseline prompt; the rejected guidance suffix is not silently added to G. Exact native rendering, target masks, sequence limits, ordering and settings must be independently checked before a run is proposed.

## First execution package: source and data plan

1. Inventory candidate training and validation families, with exact edition/component references, permitted uses, authorship, source notices and exposure records. The current historical-evidence registry has **83 components with training decisions pending**; its twelve conditional private-display approvals do not clear training or release. Existing corpus permissions and new evidence-component decisions must remain distinct.
2. Record training-use decisions for every proposed input and target component. Exclude unresolved material. Do not infer permission for restricted definitions or apparatus from a neighboring source's license.
3. Define row IDs, family-disjoint splits, coverage quotas and a source-check rubric. Build a small validator using constructed fixtures before authoring targets. No real evaluation answers belong in this validator.
4. Independently review every authored target for source support, complete requested coverage, natural English attribution, defensible translation alternatives and useful application. AI review must be identified as such; it is not expert certification.
5. Freeze the dataset and recipe, then have a separate author create fresh evaluation questions and scoring criteria without sharing them back to training authors. Record any unavoidable role overlap.

Training examples should teach concise, natural attribution where relevant. They should not train the assistant to repeat internal author IDs, refuse every question beyond a short excerpt, or attach a historical lecture to every personal reflection.

## Evaluation and cost before the owner decision

Use matched B/G answers with identical evidence, baseline prompt and native sampling settings. The fresh inventory must cover Hebrew, Aramaic, Greek, interpretation, contemporary application and ordinary English retention. Freeze exact counts and success criteria before generation. Review whole answers and pair preferences with concealed labels; include incomplete and missing outcomes. Keep raw-text and existing English holdout diagnostics separate from new conversational evidence. Loss alone cannot select G.

At the September 9 temporary rate of $5.61 per million training positions, the proposed 96 training and 24 validation rows, each capped at 8,192 positions, reserve at most **$6.62 for one training pass and two validation forwards**. This is a conservative ceiling, not an expected bill or a complete experiment budget. Additional retention diagnostics, B/G answer sampling, checkpoint storage and uncertainty reserves must be counted separately. The final proposal will replace ceiling estimates with exact rendered token counts and a complete spending cap after checking current prices and B retention. [Official Tinker pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/).

Return to the owner with the reviewed dataset, frozen recipe/evaluation, complete cost reservation and remaining limitations **before starting training**. The owner's explicit training hold remains active. Source and dataset preparation may continue under the owner's instructions. This document does not authorize training, serving migration or model promotion.
