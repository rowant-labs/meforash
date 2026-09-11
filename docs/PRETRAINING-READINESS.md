# Preparation and first Inkling experiment

Latest result: the [revised English-target comparison is complete](INKLING-REVISION-RESULTS-V3.md). Original-text-only B remains the main development checkpoint, with E/F preserved. On 24 Bible questions, F was preferred to B on five, less preferred on six, and tied on thirteen, with three requested-content omissions versus one in B. All 94 returned answers were reviewed; E's incomplete collection permits only a four-question Hebrew comparison. The earlier experiments and original preparation below remain preserved.

Updated September 6, 2026. **The Inkling calibration, full 136-update raw-text development pass, and all 24 English adapter answers are complete.** The pass processed **3,280,433 input tokens**. A fixed 12-window held-out Hebrew/Greek sample showed **77.3% lower negative log likelihood**, a text-prediction measure rather than a translation-accuracy score. The loss sample contains no Aramaic, and overall English-answer improvement remains unestablished. Read the [training methods and measurements](INKLING-TRAINING.md) and [completed source-checked answer review](INKLING-ADAPTATION-RESULTS.md).

The [large-model comparison](LARGE-MODEL-COMPARISON.md) selected full Inkling, with Kimi K2.6 as the closest challenger and Inkling-Small as the earlier cost/speed reference. The [first gpt-oss baseline](BASELINE-RESULTS-2026-09-05.md) and its preparation remain historical controls, distinct from the completed Inkling training.

## Current Inkling result

| Item | Measured result |
|---|---|
| Development training | 136 updates; 2,169 sequences; 3,280,433 input tokens; 3,229,825 scored targets |
| All-chapter preparation | 2,299 sequences; 3,484,503 input tokens; available for a future final run |
| Preserved development holdout | 130 sequences; 204,070 input tokens; 69 chapters |
| Fixed loss-monitoring sample | 12 Hebrew/Greek windows; NLL 0.050675 → 0.011513; no Aramaic windows |
| English adapter evaluation | 24 / 24 complete answers; original baseline and contemporary unchanged-model repeat retained |
| Integrity | All 31,153 selected reading fragments retain their prior split and exact text; native tokenizer checked against pinned HF assets |
| Checkpoints | Training-state and sampling checkpoints saved; private inference exercised; 30-day retention |
| Serving limits | Export/load compatibility and public custom-adapter serving remain unverified |

The [Inkling preparation manifest](../manifests/preparation-inkling-v1.json) records tokenizer pins and counts. [Training and evaluation results](INKLING-TRAINING.md) distinguish the completed calibration from the fresh full pass, record matched prompts and service variation, and separate cost estimates from provider invoice reconciliation. Completion measures answer delivery, not historical or linguistic accuracy.

## Historical gpt-oss preparation

The following table preserves the original gpt-oss-tokenized preparation. These are **historical tokenizer counts**, not the input counts of the completed Inkling pass.

| Item | Measured result |
|---|---|
| Hebrew/Aramaic source | OSHB/WLC, 39 book files, 929 chapters, 23,213 source verse records |
| Greek source | SBLGNT, 27 books, 260 chapters, 7,939 source verse records |
| Total coverage | 66 book files, 1,189 chapters, 31,152 source verse records |
| Prepared windows | 2,299 sequences; maximum 2,048 input tokens; no verse truncation |
| Complete corpus | 3,482,204 processed input tokens; 3,428,523 ancient-text body tokens |
| Development training split | 2,169 sequences; 3,278,264 processed tokens; 1,120 chapters |
| Development holdout | 130 sequences; 203,940 processed tokens; 69 chapters |
| Integrity audit | Every selected reading fragment appears once; exact Unicode token round-trip; no chapter overlap |
| Software checks at that stage | 137 tests passed before Inkling training implementation; frozen 24-case large comparison completed |
| Historical API spending | Token-price estimates and uncertain reservations are separated in the [baseline report](BASELINE-RESULTS-2026-09-05.md), with provider invoice reconciliation pending |

These are counts from the actual downloaded editions and tokenizer, not English translation estimates. The Hebrew Bible is represented using the repository's 39-file organization; this does not establish an ancient book order or favor a particular modern canon. Source verse numbering differs from some English Bibles. In particular, the Greek source has numbering gaps that were preserved rather than filled from another edition.

The historical machine-readable record is [preparation-v1.json](../manifests/preparation-v1.json), with [audit results](../manifests/audit-v1.json). Both preparations use the same source inventories and reading choices. Full per-book inventories, source file hashes, pinned commits, and licenses are in the [Hebrew manifest](../manifests/oshb.json) and [Greek manifest](../manifests/sblgnt.json).

## Textual choices made explicit

The Hebrew base uses the written/main **ketiv** layer. Qere readings, morphology, notes, and paragraph markers remain in the audit data, but are not added as ordinary words to the first raw-text training arm. Vowels and accents remain as supplied; unpointed words are not reconstructed. The underlying text is public domain according to upstream, while annotations require CC BY attribution. See [Hebrew preparation](HEBREW-PREPARATION.md).

The Greek base preserves SBLGNT's main text and doubtful single-bracketed wording. Its shorter ending of Mark, longer ending of Mark, and John 7:53–8:11 are retained as **separately labeled supplements**: 25 verse fragments across three editorial groups. A verse can contain both primary and supplemental text, explaining why the audit covers 31,153 reading fragments from 31,152 verse records. These are features of the chosen edition, not newly adjudicated manuscript readings. See [Greek preparation](GREEK-PREPARATION.md).

No Unicode normalization is applied. Source hashes and the pinned tokenizer catch changes. Complete verses are packed in passage order, within source, chapter, language, and reading layer; numbering gaps interrupt continuity. Chapters connected by an editorial group stay in the same split, and sequence metadata preserves doubtful-wording continuation. Each sequence has a short source/passage/layer header. Its prediction loss is masked out, so the learning targets are ancient text plus an end-of-text token. There are no English translations, answers, commentaries, or user chats in this training arm.

The historical gpt-oss preparation contained approximately 2.85 million Hebrew, 46,277 Aramaic, 250 mixed-language, and 588,485 Greek processed tokens. Current Inkling counts by language are recorded in its separate manifest. Aramaic is a small portion of the source and has no windows in the preserved holdout; assess it separately through the English questions and a future frozen evaluation. No oversampling has been silently applied. Any later weighting is an experimental decision to record.

This is complete coverage of the selected Hebrew/Aramaic Bible and Greek New Testament editions. Septuagint, deuterocanonical collections, DSS transcriptions, and a comprehensive manuscript apparatus are **not yet in the corpus**. The [scope inventory](../manifests/corpus-scope.json) keeps those gaps visible. The Masoretic base cannot be advertised as the earliest recoverable reading everywhere; biblical text alone also cannot supply all its historical context.

## Cost from the actual files

The completed Inkling pass processed 3,280,433 development-training positions, estimating **$18.40 in training compute** at the recorded $5.61/M rate. Calibration, validation, sampling, and checkpoint/storage contingency are additional; the [training report](INKLING-TRAINING.md) itemizes the experiment's estimates. These are not reconciled invoice amounts. The recorded Inkling price includes a temporary discount. [Inkling pricing snapshot](../manifests/comparison-large-pricing-v1.json)

The original gpt-oss figures remain historical estimates: at the recorded default 32K rate of $0.737/M, development training would have cost **$2.42**, or **$2.57** for all chapters. No gpt-oss training pass was executed. The [historical pricing snapshot](../manifests/tinker-pricing.json) records September 5 prices from [Tinker's model table](https://tinker-docs.thinkingmachines.ai/tinker/models/).

The estimates count prepared, unpadded input positions. The completed calibration verified training mechanics and checkpoint inference; it did not establish invoice reconciliation for masking, padding, or batching. Validation forward passes, sampling, repetitions, retries, storage, review, and hosting are separate costs.

The Inkling runner enforced a shared **$50 estimated reservation cap**, including checkpoint/storage contingency, for the completed calibration and development pass. It is a local submission guard, not a provider-enforced dollar ceiling. The earlier $5 development-pass proposal applied only to gpt-oss and was superseded. Future proposed allocations remain caps rather than spending targets. A commercial base-model API's low price does not establish a price for serving this custom adapter.

## Reproduce the preparation

Python 3.13 was used locally. Run from the repository root. These commands reproduce the **historical gpt-oss preparation**. The fetch step downloads public source checkouts and a roughly 28 MB tokenizer, never full model weights.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-prep.txt
.venv/bin/python -m bibleprep.fetch
.venv/bin/python -m bibleprep.hebrew
.venv/bin/python -m bibleprep.greek
.venv/bin/python -m bibleprep.tokenize
.venv/bin/python -m bibleprep.audit
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m bibleprep.evaluate
```

The last command only prepares a baseline plan. API execution requires an explicit flag, prices, a budget, and a locally configured key. Source preparation validates pins before producing data. Repeated runs reproduce the artifacts; an intentionally changed source version requires review and new manifests. Exact installed dependency versions from this preparation are recorded in [requirements-prep.lock.txt](../requirements-prep.lock.txt).

Historical artifacts are local and ignored by Git under `data/prepared/v1/`. Inkling artifacts use the separate `data/prepared/inkling-v1/` directory, each with `train.jsonl`, `validation.jsonl`, and `all.jsonl`. After installing `requirements-training.txt` and preparing the pinned Inkling tokenizer assets described in the [comparison setup](LARGE-MODEL-COMPARISON.md), `.venv/bin/python -m bibleprep.prepare_inkling` reproduces its local preparation without model API calls. The [training report](INKLING-TRAINING.md#reproduce-locally) distinguishes planning commands from paid execution.

Each prepared row already contains aligned `input_ids`, `target_ids`, and `weights`. Metadata, passage text, and verse IDs allow inspection. Inkling includes its native beginning token as masked input context. Do not shift the targets a second time or feed evaluation rubrics into the trainer.

## Completed work and proposed follow-up

1. **Preparation, calibration, training, and English sampling are complete.** Pinned/native tokenizer checks, source integrity, shifting/masking, budget controls, and checkpoint inference were exercised. Native-versus-HF checks are not live-server tokenizer verification, and the provider's base-weight revision remains unpinned. The [training report](INKLING-TRAINING.md) records these limits.
2. **Source review is complete for the diagnostic comparison.** The original unchanged model, its contemporary repeat, and the adapter each returned 24 complete answers. [Concealed-label AI review](INKLING-ADAPTATION-RESULTS.md) checks meaningful language, quotation, and reflection differences. This is not expert certification or a formal blind study; overall English improvement remains unestablished. The repeated base control matters because unchanged-model responses also varied.
3. **The English instruction comparisons are complete.** The original 104-training/16-validation dataset and C/D comparison were followed by the gentler E update and the [v3 target audit and revision](INKLING-TARGET-REVISION-V3.md). All 120 old targets were audited; fourteen tasks were broadened, with no clear material factual error found in the original narrow targets. F then completed seven updates from B. In the [latest comparison](INKLING-REVISION-RESULTS-V3.md), F versus B was 5 preferred / 6 less preferred / 13 tied on 24 Bible questions, with three requested-content omissions versus one in B. All 94 returned answers were reviewed; A/B/F each completed 30 questions and passed six simple general fixtures. E stopped after four answers and one error, leaving 25 unsubmitted questions; no absent answers were graded. Retain B provisionally and preserve E/F. No further SFT change is justified by loss alone; define a distinct hypothesis and freeze another evaluation before any new iteration. All reviewed questions are now development evidence, not a final public benchmark.
4. **Preserve the working private checkpoint path while checking future portability.** Existing checkpoints have 30-day retention. Review retention or export before expiry; export/load compatibility and public custom-adapter serving remain unverified. Private inference success does not establish a recurring public-serving cost or deployment readiness.

The development holdout tests adapter-era transfer only: the base model may already have seen these passages. A final all-chapter run can use `all.jsonl` after choosing the recipe; its old holdout must then be labeled as seen during adaptation. The current question set is a development pilot. Create and freeze a separate final evaluation before optimizing prompts and training settings extensively.

The repository remains local and unpublished. Code, manifests, notices, tests, and decision records are intended for publication; raw files, credentials, private notes, and model/run artifacts remain excluded pending the [publication process](PUBLICATION.md).
