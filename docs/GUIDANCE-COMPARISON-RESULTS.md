# Attribution-guidance comparison results

September 9, 2026. **Keep retained Inkling B and the current chat behavior.** The added guidance did not pass the predeclared adoption gate. On six Bible questions it was preferred once, less preferred twice, and tied three times. This is a small development result, not evidence that guidance generally harms the model or that another fine-tune will solve these problems.

## What was tested

Both conditions used the same saved original-language fine-tuned B adapter, question, selected evidence, notices, native renderer and sampling settings. Only a generic system-guidance suffix differed. This measures the effect of that guidance on B; it does not compare trained versus untrained weights. The existing chat was not changed.

Eight questions produced sixteen answers: six Bible questions across Genesis 4:8, Isaiah 53:11 and the selected Pilate clause of Luke 3:1, plus two ordinary English controls. One Bible question requested contemporary reflection. All three passages had been included in B's raw-text adaptation and researched in the project. They were new to the earlier evidence pilot, not unseen source material. No Aramaic case was included.

The implementation was frozen before question authoring. Questions, criteria, exact source/use notices, checkpoint identity, settings and native requests were frozen before generation. Individual and paired reviewers received separately shuffled packets without condition labels. Both reviews were validated and frozen before the private mapping was opened. Reviewers were AI assistants with disclosed project involvement: the individual reviewer had authored the questions and reviewed sources/code; the paired reviewer had authored review tooling and reviewed sources. Neither review is specialist certification, and wording can still hint at a condition despite concealed labels.

## Results

| Measurement | Original guidance | Added guidance |
|---|---:|---:|
| Complete / planned answers | 8 / 8 | 8 / 8 |
| Preferred Bible answers | 2 | 1 |
| Tied Bible pairs | 3 shared | 3 shared |
| Answers with attribution findings | 0 | 2 |
| Answers with source-scope findings | 1 | 0 |
| Answers flagged for material factual errors | 0 | 0 |
| Answers with unresolved material assertions | 0 | 0 |
| Requested-content omissions | 0 | 0 |
| Semantically correct general controls | 2 / 2 | 2 / 2 |

The two guided attribution findings differ in severity. One answer called a supplied project English phrase its own rendering. Another accurately called a quotation the supplied rendering but omitted its model-authored project provenance, which the frozen criteria required. The latter is a disclosure shortfall under this test's strict attribution rule; it is not a false ancient-language claim.

The original-guidance reflection invoked unspecified Scripture elsewhere despite an explicit instruction to use only the supplied passage. Its ordinary practical safety advice was allowed as contemporary application. This source-only restriction applies to that question; it is not a new requirement that all life-applicable answers use only one verse. The paired reviewer also objected to treating the field setting as isolation. That concern contributed to the preference rationale but was not a separate individual-review factual-error flag. Preserve that distinction rather than treating the zero factual flags as verification of every interpretive phrase.

The individual review recorded zero findings in its requested-content omission field; the separately classified required-provenance disclosure shortfall remains. All four control answers were semantically correct. These checks are too small to establish general retention, ancient-language mastery or whole-Bible historical reliability.

## Decision and cost

The predeclared gate required all answers complete, more guided wins than losses, correct controls, and no guided material, unresolved, attribution/scope or omission findings. The guided condition failed the preference and attribution requirements. **Do not adopt the suffix or load these historical-evidence packets into chat on the strength of this run.** The retained fine-tuned model itself remains B.

All sixteen requests completed, with no partial output, uncertain request, retry or unsubmitted slot. Native receipts were verified. Reported usage was **30,712 input tokens and 7,603 generated tokens**, giving **$0.09301348** estimated sampling cost at the checked rates. The full reservation was $0.85852160 under a $2 operator allowance. This is usage-based accounting, not a reconciled invoice.

No new training, checkpoint retention change, weight export, public deployment or publication occurred. Existing experiments and the sixty-file implementation freeze were preserved.

## Next work

Follow the [candidate G preparation plan](CANDIDATE-G-PREPARATION.md): teach evidence-conditioned English answers that accurately distinguish a named ancient edition, supplied project rendering, the assistant's own translation, historical inference and requested contemporary reflection. The hypothesis needs reviewed examples and prospective testing; this result does not demonstrate that training is necessary or sufficient. Earlier E/F instruction passes also did not justify replacing B, so repeating them is not the plan.

Private input permissions do not clear historical evidence for training or release. Audit training eligibility first, then prepare a separately versioned dataset. Keep the next evaluation's exact questions and answer keys away from training authors until the dataset and recipe are frozen. Include Hebrew, Greek and Aramaic, broader interpretation/application and general retention checks; label known-source exposure honestly. Present the concrete dataset, recipe, evaluation and cost ceiling to the owner before any new training. Recurrence remains optional and deferred.

Serving is a separate practical issue: the [current feasibility review](INKLING-B-SERVING-FEASIBILITY.md) confirms the existing Tinker path and explains why another provider's unchanged Inkling offering does not establish compatibility with B.

## Reproduction and records

The [method](GUIDANCE-COMPARISON-COLLECTION.md) describes the collector, review rules and engineering checks. The [public aggregate](../reports/guidance-comparison-v1.json) records counts and binding hashes without private prompts, outputs or checkpoint references. Exact private records are under `runs/guidance-comparison-v1/`: active `protocol-v2.json`, `live/collection.json`, the masked review packets, both frozen judgments, the pre-map receipt and `review/integration.json`. The protocol SHA-256 is `8198f82a8b1a638487f524d4910868007155b17fdd47f9857e179392d15c6b78`.

Do not rerun, retry, resume or overwrite this collection. Its questions and findings are now development evidence. Future methodological changes require new versioned artifacts and a fresh prospective evaluation.
