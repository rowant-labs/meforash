# Known-topic English evidence pilot v1

Status: completed actual provider pilot; all eighteen answers were verified and reviewed. The predefined narrow gates passed, with additional source-attribution issues found in the separate parent audit. This is a development comparison of the retained original-text fine-tuned B model. Training remains on the owner's separate research hold.

The pilot asks whether supplying reviewed source evidence improves English answers about two familiar passages: Mark 1:1 in SBLGNT and the language boundary/address in Daniel 2:4 in OSHB/WLC. Four Bible cases and two simple general-English controls produce eighteen planned answers across B-memory, B-packet and B-lookup. These are two source families, not a fresh whole-Bible benchmark. The comparison does not isolate the effect of fine-tuning itself.

Each fixed packet and exact lookup selection contains the same conditionally eligible components with verified attribution, license notices, changes and source limitations. Their rendered inputs are identical in this pilot. Report any answer differences as generation variability; this fixture does not establish production retrieval quality. B-packet versus B-memory is the main evidence comparison.

## Prospective method

Questions and criteria remain in private `data/evidence/pilot-v1/`. The source author and parent AI reviewer checked the exact edition excerpts, acceptable English renderings and scope limits before generation. They have overlapping project roles and no human specialist certification. Calibrated uncertainty is not a fabricated source claim, though missing requested content still counts as an omission. An edition representing a manuscript tradition is distinct from independently collating or proving the original manuscript wording.

The protocol was frozen before generation and binds the source registry, exact notice manifest, questions, criteria, settings, review gates, retained checkpoint, implementation and request inventory. Individual and pair reviewers receive opaque identifiers without arm labels; answer wording may still reveal the evidence condition. Reviews must be saved and their exact file hashes recorded before the private arm map is opened for integration.

All returned final content, including partial answers, is reviewed. Eighteen complete answers and four matched-complete Bible pairs per contrast are required for a conclusive pilot. Missing or uncertain slots remain in the planned denominator. The evidence conditions must have no critical source errors; the memory baseline may contain errors for evidence to correct. The packet must not increase requested-content omissions and must receive more preferences than the memory condition. General controls require semantic correctness in every arm. Passing only supports further testing with new source families; it does not promote the model or establish production accuracy.

## Sampling and cost

Use effort 0.7, temperature 0, seed 1702, an 8,192-token input ceiling and an 8,192-token output ceiling, including generated reasoning. One attempt per slot; an incomplete or uncertain result stops the full inventory. Each submitted request keeps its maximum reservation until accounted for, with unsubmitted requests reported separately. The native process deadline is 300 seconds per request; uncertain requests are not retried automatically.

On September 9, 2026 UTC (September 8 locally), the provider's official pricing data lists the existing 64K Inkling sampler at $1.87 per million input tokens and $4.68 per million output tokens. Eighteen requests at both full ceilings reserve **$0.9658368**; the operator limits this evaluation to **$2** within the owner's continuing authorization for reasonable project evaluation. No cache discount is assumed. These are sampling estimates, not an invoice or a new storage/training allowance. [Official pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/).

A read-only check matched retained B's private rank-8 Inkling sampler and its original receipt; its recorded expiry remains October 6. No retention setting changed. Private pricing, identity, preparation and eventual execution receipts are under `runs/evidence-pilot-v1/`.

## Result

All 18 planned answers completed, with zero failed or partial requests, retries, or unsubmitted slots. Native verification matched every returned final answer to its receipt and exact prompt. Recorded usage was 24,529 input tokens and 8,517 generated tokens including reasoning, estimating **$0.08572879** in sampling at the frozen rates; the provider invoice has not been reconciled. The immutable generic reservation record retains its legacy fixture-rate label; a separate actual-pilot cost receipt binds the verified official pricing snapshot.

Both reviews were saved and hashed before the condition map was opened. All eighteen returned answers and twelve paired comparisons were reviewed. Two AI workers performed individual and paired judgments with overlapping source/engineering roles; the parent reviewed the revealed answers afterward. These are development judgments, not independent human expert certification.

| Condition | Complete / planned | Bible answers with a criterion-defined critical error | Bible answers with a requested-content omission | General controls correct |
|---|---:|---:|---:|---:|
| B from memory | 6 / 6 | 2 / 4 | 3 / 4 | 2 / 2 |
| B with fixed evidence | 6 / 6 | 0 / 4 | 0 / 4 | 2 / 2 |
| B with lookup evidence | 6 / 6 | 0 / 4 | 0 / 4 | 2 / 2 |

The fixed packet was preferred to memory on **3 of 4 Bible cases**, with **0 less preferred and 1 tie**. The two memory errors concerned the selected Greek edition's displayed wording. The omission count includes answers that did not explicitly identify requested edition annotations; the rubric distinguishes those omissions from incorrect claims. Error and omission counts can overlap within an answer.

Lookup versus fixed packet was **1 preferred / 2 less preferred / 1 tied** across the same four Bible cases. Both conditions received identical rendered inputs, so this is answer variability, not evidence that retrieval improved or worsened performance. All four lookup source closures were verified. There were no missing pairs; all general-control pairs tied.

### Separate parent audit after review freeze

The predefined gates passed. They did not inspect every possible extra claim in an answer. The parent found an additional error in a lookup answer that described a Hebrew introduction as extending across a Daniel verse range that includes Aramaic speech. A local check of the pinned XML confirms Aramaic tagging in that range. The same answer blurred the project-authored English gloss with what the upstream edition supplies. These observations are recorded separately; the frozen reviews and their aggregate scores have not been rewritten.

The evidence answers also repeated internal source identifiers and lengthy notice language. Required attribution and license notices must remain available, while the conversational answer should distinguish original text, project English rendering, and supporting record metadata clearly.

This supports continued testing of **the existing fine-tuned B model with checked evidence**. It does not establish the benefit of fine-tuning itself, complete historical coverage, general retrieval quality, or public readiness. In particular, the table's zeros apply only to the frozen criteria and must not be advertised as an absence of all errors.

### Next step

Keep B and the private chat unchanged. First investigate source packaging, extra unsupported claims, and attribution of English glosses; then freeze questions from new source families with explicit coverage for those failure modes before another evaluation. This pilot's questions are now development material.

Before any new training, obtain the owner's promised research topic, complete that research, and revisit a distinct training hypothesis and evaluation plan. The current continuation does not lift the training hold. No training, retention change, source addition to chat, public deployment, or publication occurred in this pilot.

See the [runner method](EVIDENCE-PILOT-RUNNER.md), [evaluation runbook](EVALUATION-RUNBOOK.md), and [execution plan](EXECUTION-PLAN.md).
