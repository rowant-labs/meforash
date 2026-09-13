# Meforash

Explore the Bible in English through a model fine-tuned on Hebrew, Aramaic, and Greek biblical texts. A project by Rowant Labs.

Meforash supports close reading and broader reflection without requiring a verse reference or a mode selector. It uses retained **Inkling adapter B**, with explicit passage lookup from the selected OSHB/WLC and SBLGNT editions. Those editions are not a complete reconstruction of the earliest text, and fluent answers still need critical reading.

**Launch work:** [current progress and measured conversation checks](docs/LAUNCH-PROGRESS.md).

**Status (September 12, 2026):** original-language fine-tuning and several controlled development comparisons are complete. B remains selected after the [Candidate G comparison](docs/CANDIDATE-G-RESULTS.md). The [public source repository](https://github.com/rowant-labs/meforash) and Railway-hosted beta at [meforash.com](https://meforash.com) are live with limited guest access and optional email accounts. The repository documents actual results, including unsuccessful experiments. A clean clone can run offline checks and reproduce source preparation, but cannot serve the private B checkpoint without the owner's runtime assets and provider access.

The intended experience supports both detailed questions about a passage's earliest recoverable wording and context, and broad questions about meaning and present-day life. Translation and textual questions receive focused explanations. Life-applicable questions can receive Bible-based, non-denominational reflections, with contemporary application distinguished from historical interpretation. Evaluation compares the adapted model with the unchanged model on English questions.

**Continue development:** the [execution plan](docs/EXECUTION-PLAN.md) consolidates current state and next work. Use the [evaluation runbook](docs/EVALUATION-RUNBOOK.md) for test locations and future comparison design, and the [agent handoff](docs/AGENT-HANDOFF.md) to resume with another development assistant. The [living task queue](manifests/execution-state.json) separates completed milestones from proposed work.

## Using the beta

Visit [meforash.com](https://meforash.com). Adults 18+ can ask three guest questions, then sign in with a six-digit email code to keep asking. Signed-in accounts currently receive twenty questions per day. Saved conversation history is not implemented; signing in during a conversation preserves the current conversation through the sign-in flow.

- Press **Enter** to send or **Shift+Enter** for a new line; the send button also works.
- Available answer text streams from Railway to the browser. The model can still take time before producing visible text.
- New questions scroll into view. The page follows growing answers until the reader scrolls away, then resumes near the bottom.
- Source cards display passages supplied as context, not independent verification of every answer claim.

The beta serves retained B through Tinker with a bounded [concurrent serving pool and FIFO queue](docs/CONCURRENT-BETA.md): **three simultaneous generations**, up to **twelve waiting requests**, and a **120-second queue timeout**. This limits active generations, not the total number of people who can visit. Authentication, quota checks, source lookup and provider access stay on the server; provider credentials are never sent to the browser. See the live [Privacy Policy](https://meforash.com/privacy) and [Terms](https://meforash.com/terms).

The [streaming and memory update](docs/STREAMING-EFFICIENCY.md) shares one native renderer across requests. Three overlapping live browser requests completed with progressive text and no fallback polling; warm container memory snapshots fell from 2.89 GB to 1.58 GB. These are bounded engineering checks, not a sustained-load guarantee or proof of faster model reasoning. The current provider endpoint remains beta; supported production capacity and [alternative hosting for the exact adapter](docs/INFERENCE-OPTIONS.md) remain unresolved. No provider inquiry has been sent and no weights have been exported or published.

The [historical-evidence milestone](docs/HISTORICAL-EVIDENCE-MILESTONE.md) defines the next source-expansion work; early-witness and context coverage remains incomplete. The separate loopback preview remains available for prepared local development through `.venv/bin/python -m bibleprep.chat_server`.

## Research and evaluation


The [first historical-evidence research pack](docs/EVIDENCE-FIRST-PACK.md) now contains **eight private drafts** across Hebrew, Aramaic and Greek, with source provenance, textual alternatives and historical context. All pass structural checks; none is expert-certified or loaded into chat/training. The reusable validation code and public inventory record the preparation and its gaps.

The [private evidence review tool](docs/EVIDENCE-REVIEW.md) now presents those eight records with linked claims, citations, textual alternatives and **130 traceable review tasks**. These are review tasks, not established factual errors. The historical [checkpoint preservation proposal](docs/CHECKPOINT-PRESERVATION.md) verified both B checkpoints and estimated about $2.02/month to keep them; expiry has since been removed from both retained checkpoints.

The [first source-gap follow-up](docs/SOURCE-GAP-REVIEW-P2.md) adds thirteen findings across Genesis 4:8, Isaiah 53:11 and Daniel 2, with exact transcription/edition locators and explicit restoration limits. These remain private research records; source eligibility and specialist review are pending.

The [evidence-use registry](docs/EVIDENCE-ELIGIBILITY.md) separates scholarly review from app, redistribution, training and adapter-release decisions. A [nine-question specialist packet](docs/SPECIALIST-REVIEW-PACKET.md) prepares remaining factual review. [Six edition components have narrow AI source reviews](docs/SOURCE-COMPONENT-REVIEW-P2.md) and conditional private input/display decisions through [notice-complete delivery](docs/EVIDENCE-NOTICE-DELIVERY.md). The planning, accounting, native-result, exact-request, blinded-review and coordination layers now support both constructed checks and the completed actual pilot. The broader source inventory, specialist review, chat integration and a fresh-source comparison remain unfinished.

**Training evidence:** the first original-language Inkling calibration and full development-corpus pass are complete: **136 updates over 3,280,433 input tokens**, followed by **24 complete English answers**. The prepared sources cover 66 book files and 31,152 source verse records; development training preserves a chapter holdout. Negative log likelihood fell **77.3% on a fixed 12-window held-out Hebrew/Greek sample**. That measures text prediction, not translation accuracy or Aramaic performance. Overall English-answer improvement remains unestablished. See the [training methods and measured results](docs/INKLING-TRAINING.md) and [source-checked answer review](docs/INKLING-ADAPTATION-RESULTS.md).

The [earlier model comparison](docs/LARGE-MODEL-COMPARISON.md) selected full Inkling, retaining Kimi K2.6 as the closest challenger and Inkling-Small as the earlier cost/speed reference. Private checkpoint inference now works and powers the hosted beta. Expiry was removed from both retained B checkpoints, but export/load compatibility and supported production serving outside the current beta remain unverified. No model weights have been published.

The [English instruction comparison is complete](docs/INKLING-INSTRUCTION-RESULTS.md): both fine-tunes used the same 104 training examples, with 16 reserved for validation, and all 96 evaluation requests were source-reviewed. The original-text-only adapter remains the leading experimental checkpoint: it was preferred over unchanged Inkling on 11 questions, less preferred on four, and tied on nine. Instruction-only training showed no clear gain; the combined adapter hit the output limit on three questions and omitted requested content in others. This small AI review does not establish whole-Bible accuracy. New compute/sampling estimates are $1.69, plus $6 checkpoint/storage contingency.

The [gentler English calibration is also complete](docs/INKLING-CALIBRATION-V2.md). E used the same examples with a fivefold lower learning rate and completed all 30 new questions. On the 24 Bible cases it was preferred to B on seven, less preferred on eight, and tied on nine, with three requested-content omissions versus none in B. Keep B as the main development checkpoint and preserve E for refinement. All six simple general-English fixtures were semantically correct for every arm. This round estimates **$1.04 compute/sampling plus $3 checkpoint/storage contingency**, with the invoice unreconciled.

The [revised English-target comparison is complete](docs/INKLING-REVISION-RESULTS-V3.md). F trained from B on the dataset with fourteen broadened tasks, then all 94 returned answers were source-reviewed. F versus B was **5 preferred / 6 less preferred / 13 tied**, with **three requested-content omissions versus one in B**. Retain B provisionally and preserve F. A/B/F each completed all 30 questions and passed all six simple general fixtures; E stopped after four answers and one request failure, leaving 25 questions unsubmitted with no selective retry. Comparisons involving E cover only four Hebrew questions. This round accounts for **$1.01 estimated/reserved compute and sampling plus $3 checkpoint/storage contingency**, within its $10 cap; the invoice remains unreconciled. Broader targets did not establish an answer-quality gain over B.

The project is intended to make its source choices, training methods, costs, evaluations, revisions, and limitations inspectable. The code and methodological documentation are public; credentials, operational records and unreviewed source material remain private. Open-source software does not automatically make every source dataset or model artifact redistributable.

- [Live streaming, memory measurements and validation](docs/STREAMING-EFFICIENCY.md)
- [Inference options for the retained adapter](docs/INFERENCE-OPTIONS.md)
- [First historical-evidence pack: preparation and limits](docs/EVIDENCE-FIRST-PACK.md)
- [Candidate G comparison: results and decision](docs/CANDIDATE-G-RESULTS.md)
- [Private chat: use, sources, privacy and limits](docs/PRIVATE-CHAT.md)
- [Historical evidence: next collection milestone](docs/HISTORICAL-EVIDENCE-MILESTONE.md)
- [Revised English-target comparison: results and decision](docs/INKLING-REVISION-RESULTS-V3.md)
- [English-target audit and data revision](docs/INKLING-TARGET-REVISION-V3.md)
- [Gentler English calibration: results and decision](docs/INKLING-CALIBRATION-V2.md)
- [Earlier English instruction results](docs/INKLING-INSTRUCTION-RESULTS.md)
- [English instruction methods and data](docs/INKLING-INSTRUCTION-EXPERIMENT.md)
- [Original-language Inkling training experiment](docs/INKLING-TRAINING.md)
- [Inkling adaptation results and source review](docs/INKLING-ADAPTATION-RESULTS.md)
- [Large-model comparison and current selection](docs/LARGE-MODEL-COMPARISON.md)
- [Earlier five-model comparison](docs/MODEL-COMPARISON.md)
- [First live baseline results](docs/BASELINE-RESULTS-2026-09-05.md)
- [Native Tinker runner](docs/TINKER-BASELINE.md)
- [Preparation results and next steps](docs/PRETRAINING-READINESS.md)
- [Project charter](docs/PROJECT_CHARTER.md)
- [Decision history](docs/DECISIONS.md)
- [Whole-Bible training plan](docs/training-plan.md)
- [Source research](docs/source-research.md)
- [Models and training services](docs/model-research.md)
- [Current provider comparison](docs/PROVIDER-CHOICE.md)
- [Hosting research](docs/hosting-research.md)
- [Evaluation plan](docs/evaluation-plan.md)
- [Broad questions and application tests](docs/application-evaluation.md)
- [Publication and privacy practices](docs/PUBLICATION.md)

To reproduce data acquisition, parsing, tokenization, and integrity checks, follow [the preparation commands](docs/PRETRAINING-READINESS.md#reproduce-the-preparation). Preparation runs locally without model API calls. Raw source files, prepared training data, and run records are ignored by Git; third-party license notices and reproducible manifests are retained.

Original project code and authored documentation are offered under [Apache-2.0](LICENSE). Third-party texts, annotations, model weights, and datasets retain their own licenses and attribution requirements. No third-party corpus or model weights are bundled in the public repository.

See the [project notice](NOTICE), [brand policy](docs/BRAND-POLICY.md), and [security reporting instructions](SECURITY.md). The software license does not grant permission to present an independent fork as the official Meforash service.
