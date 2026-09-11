# Original-language Inkling adaptation

This completed experiment tests whether one pass over the selected Hebrew/Aramaic and Greek editions improves English access to their wording. The base is full `thinkingmachines/Inkling`, selected in the [large-model comparison](LARGE-MODEL-COMPARISON.md). Source-text prediction improved, while the [72-answer source review](INKLING-ADAPTATION-RESULTS.md) found mixed English results and continuing errors. Preparation and training results below must be distinguished from demonstrated translation or historical accuracy.

## Provider guidance and experimental choices

Thinking Machines' [cross-entropy API](https://tinker-docs.thinkingmachines.ai/tinker/losses/cross-entropy/) accepts token sequences, shifted targets, and weights. This supports original-text adaptation without a question-and-answer dataset. The objective is a **sum** of weighted negative log probabilities. We report negative log likelihood per contributing target token separately; a lower value means better prediction of this edition's text, not necessarily better English interpretation.

The native Inkling tokenizer declares document beginning `begin_of_text` (200028) and ending `endoftext` (199999). The [pinned tokenizer adapter](https://github.com/thinking-machines-lab/tinker-cookbook/blob/1f962eda3a2cec8de284725f2adc9978e93dfcd3/tinker_cookbook/tokenizer_utils.py) exposes ordinary text encoding and the native end token. Our sequence design is beginning token, metadata, unchanged original-language text, ending token. The beginning token supplies input context; all metadata prediction targets are masked. Body and document-ending predictions contribute to loss. Inputs and targets shift exactly once. This is our raw-document experiment, **not a provider-validated Inkling continued-pretraining recipe**. Chat turn ending `content_model_end_sampling` (200006) is a different boundary and is not substituted for the document ending.

Whole verses remain together in windows of at most 2,048 input positions. Books, languages, edition layers, and discontinuous passages remain separate. Hebrew main text follows the selected ketiv; preserved qere records are not silently substituted. Greek supplemental readings remain labeled separately. The existing chapter-family split is preserved, including linked editorial groups. The development pass excludes held-out chapters; a separately prepared all-chapter artifact remains available for a later final run. Source choices and missing ancient versions are documented in the [preparation report](PRETRAINING-READINESS.md).

The [pinned learning-rate utility](https://github.com/thinking-machines-lab/tinker-cookbook/blob/1f962eda3a2cec8de284725f2adc9978e93dfcd3/tinker_cookbook/hyperparam_utils.py) explicitly lacks an Inkling calibration. We therefore start with generic supervised settings rather than claiming an optimized recipe:

| Setting | Initial experiment |
|---|---|
| Adaptation | LoRA rank 8, attention/MLP/unembedding enabled |
| Learning rate | Constant 0.0001 |
| Adam | β₁ 0.9, β₂ 0.95, ε 1e-8; no weight decay or clipping |
| Objective | Summed cross-entropy with binary target weights |
| Batch | 16 sequences, with a smaller final batch |
| Order | Deterministic shuffle, seed 20260906 |
| Duration | Separate small calibration, then one fresh development-corpus pass |
| Validation | Frozen 12-sequence selection from held-out Hebrew/Greek chapters, before and after |
| English evaluation | Same frozen 24 diagnostic questions, unchanged supplied-excerpt/no-excerpt configuration, native medium effort 0.7 |

These settings follow the [generic supervised loop](https://github.com/thinking-machines-lab/tinker-cookbook/blob/1f962eda3a2cec8de284725f2adc9978e93dfcd3/tinker_cookbook/supervised/train.py), with a smaller adapter rank as a project choice. Rank 8 still implies approximately 1.27 billion adapter parameters by the provider's component counts, about 2.53 GB for bf16 weights alone; actual exports and optimizer checkpoints can be larger. That calculation motivates the footprint choice and does not establish sufficient capacity or accuracy.

The preserved validation split contains 122 Hebrew and 8 Greek sequences, **no Aramaic or mixed-language sequences**. The selected 12-sequence monitoring sample includes six Hebrew and six Greek windows. This limits validation-loss evidence for Aramaic; the English question evaluation includes Aramaic cases. The split is retained for comparison rather than changed after inspecting responses.

## Cost, checkpoints, and controls

Current unsuffixed Inkling has a 64K service context and a temporary training price of $5.61 per million tokens. Forward/prefill is listed at $1.87 per million; we reserve the higher training rate for validation as a conservative local estimate. All processed input positions count in that estimate, including masked metadata. The billing definition for masking/padding has not been verified against an invoice. [Provider pricing](https://tinker-docs.thinkingmachines.ai/tinker/models/)

The combined calibration and full-run estimated budget is capped locally at $50, including a $3 checkpoint/storage contingency per run. The initial two-run reservation totals $24.99, of which $6 is that contingency. This is a request-submission guard, not a provider-enforced dollar ceiling. Checkpoint storage is separately listed at $0.10/GB/month; the installed billing schema also includes checkpoint operation counts without a unit price stated on that pricing page. Model sampling is budgeted separately. [Billing API](https://tinker-docs.thinkingmachines.ai/tinker/api-reference/restclient/)

The runner reserves estimated compute before each operation, records completion durably, and stops on uncertain outcomes. Stopping the local process is not evidence that a provider-accepted operation was canceled. An uncertain optimizer update is never independently replayed. Checkpoint references, journals, and billing identifiers remain in ignored private run files. Both a training-state checkpoint and a sampling checkpoint are saved; their role differs as described in the [save/load guide](https://tinker-docs.thinkingmachines.ai/tinker/quickstart/#save-and-load-weights). Initial checkpoint retention is 30 days, with provider storage charges possible; export and long-term retention must be reviewed before expiry.

Provider base-weight revisions remain unpinned. Tokenizer revisions, local code, dataset hashes, seeds, and request settings are recorded, but they cannot make an unexposed server revision reproducible. Public adapter hosting and loading an exported Inkling adapter outside Tinker remain unverified.

## Reasoning and a future harness

Inkling already supports reasoning and tools. Native thinking effort is controllable; zero encourages an answer without reasoning but is not a hard prohibition. Future chat supervision should use the matching native renderer and effort conditioning. [Thinking effort](https://tinker-docs.thinkingmachines.ai/cookbook/inkling/thinking-effort/), [native renderer training boundaries](https://tinker-docs.thinkingmachines.ai/cookbook/inkling/tml-renderers/)

This corpus has no generated reasoning traces, English-answer targets, or user conversations. We leave reasoning conditioning out of raw-document training and retain the existing medium setting for English evaluation. A later harness can add source lookup, witness comparison, and evidence checks around the adapted model. Neither a harness nor reasoning-specific training is part of this first pass. Preserving those abilities is an evaluation question, not an assumption guaranteed by LoRA.

## Status

Inkling preparation is complete in [its versioned manifest](../manifests/preparation-inkling-v1.json): 2,169 development-training sequences contain **3,280,433 processed tokens**, estimating **$18.40 for one training pass** at the checked rate. The all-chapter artifact contains 3,484,503 processed tokens ($19.55), and 130 validation sequences contain 204,070 processed tokens. Calibration, validation, sampling, and storage are additional. Every one of the 31,153 reading fragments retains its prior split: 1,120 training chapters and 69 held-out chapters. Complete token-ID parity between the native tokenizer and pinned HF assets, plus unchanged Unicode, were checked during preparation; live server tokenizer parity remains unverified.

Local preparation, training, adapter evaluation, and aggregate-report checks passed. These include target shifting and masking, budget reservation before requests, termination of a stalled worker, stopping after uncertain training outcomes, checkpoint loading, and matched evaluation prompts. The [calibration result](../reports/inkling-calibration-v1.json) is complete: one update over 21,943 input positions, both checkpoint forms saved, and four English answers completed using the same prompt tokens as the base comparison. Weighted held-out NLL changed from 0.050675 to 0.051598 (slightly worse). This is a mechanics result, not evidence of improvement. The Daniel 2:20 infinitive analysis error remained; the Proverbs answer attributed one quotation wording to multiple English versions. Median answer latency was 63.2 seconds, with $0.025 estimated sampling cost.

The unchanged model also varies across repeated requests with identical prompt tokens and requested sampling settings. A [contemporary repeat of the same 24 questions](../reports/inkling-repeat-control-v1.json) completed as a variation control for $0.168 estimated sampling cost. All 24 returned matching prompt-token hashes and requested generation settings, but every full generated-token hash and exact final-answer string differed. This does not identify the cause of variation or measure accuracy; the original baseline remains the primary reference. Source review uses three concealed condition labels per question and considers grammar, citation fidelity, and reflection separately. This is diagnostic AI review, not a formal blind study or expert validation.

The final adapter evaluation used a 300-second request deadline, compared with 240 seconds for baseline calls, because calibration checkpoint sampling was slower. Input/output ceilings, effort, temperature, and seed remained unchanged; deadlines and observed latency are reported separately.

The fresh full development pass **completed all 136 updates**, processing 3,280,433 input positions and 3,229,825 scored targets. Both checkpoint forms were saved. The fixed held-out sample changed from **0.050675 to 0.011513 NLL per scored token**, approximately **77.3% lower loss**. This is measured text-prediction improvement on the 12-window Hebrew/Greek sample, not a translation-accuracy score; prior base-model exposure to these texts is unknown. The calibration adapter is retained separately; its update was not carried into the full-pass model.

The [aggregate report](../reports/inkling-adaptation-v1.json) records completed training and English evaluation. The final checkpoint answered all 24 frozen questions in three parallel groups of eight. Every paired prompt-token hash matches the original baseline; all three groups used the same adapter checkpoint. There were no request errors, incomplete answers, unresolved requests, or missing usage records.

| English evaluation | Original unchanged model | Contemporary unchanged repeat | Original-text adapter |
|---|---:|---:|---:|
| Complete answers | 24 / 24 | 24 / 24 | 24 / 24 |
| Processed input tokens | 8,252 | 8,252 | 8,252 |
| Generated tokens, including reasoning | 35,095 | 32,609 | 23,866 |
| Median request time | 21.8 seconds | 36.0 seconds | 59.2 seconds |
| Estimated sampling cost | $0.180, previously incurred | $0.168 | $0.127 |

Request times include service overhead and differ in concurrency, cold loading, and service conditions. They do not isolate an adapter speed penalty or predict public hosting performance. The evaluation contains 17 supplied-excerpt cases and seven without an excerpt; it is not a complete paired test of both evidence settings on every question.

The [incremental reservation/estimate](../reports/inkling-experiment-cost-v1.json) for this experiment is **$25.31**: $24.99074760 for calibration and full training, $0.02523628 for four calibration answers, $0.16804136 for the contemporary unchanged repeat, and $0.12712412 for final adapter sampling. This includes **$6 of checkpoint/storage contingency**, leaving **$19.31 of estimated compute and sampling**. The original baseline and earlier model comparisons were already incurred and are excluded from this incremental total. The machine-readable adaptation report has a different, explicitly named comparison scope that includes the original baseline and excludes the repeat control and calibration sampling; its total should not be described as new expenditure. No total here is a reconciled provider invoice.

The completed [English source review](INKLING-ADAPTATION-RESULTS.md) records every case. The adapter improves some explanations and quotation fidelity, retains several sound translations, and still makes material errors. It corrects the requested Daniel 6:11 forms while introducing two stem errors in Ezra 4:21; all forgiveness answers need factual repairs. General English-answer improvement remains unestablished. Preserve this adapter and test a separately reviewed explanation dataset in the next controlled comparison before choosing another raw-text pass.

## Reproduce locally

Install the pinned runtime from `requirements-training.txt`. Preparation requires the previously pinned source artifacts and tokenizers. The following planning command reads no credentials and submits no model operations:

```sh
python -m bibleprep.train_inkling --phase calibration
```

Live calibration requires an explicit `--execute`; the runner loads the local ignored `.env`. Run directories must be new. After reviewing a completed calibration checkpoint, a fresh full pass uses `--phase full --calibration-run runs/<completed-calibration> --execute`. The runner supports no automatic resume after uncertainty.

Evaluate a completed adapter with `python -m bibleprep.evaluate_adapter --checkpoint-file runs/<training-run>/checkpoints.json`, adding explicit input/output prices, budget, and `--execute` for paid sampling. Its defaults match the frozen 24-question baseline protocol. A planning evaluation creates a private run record, so use a fresh run directory for execution.
