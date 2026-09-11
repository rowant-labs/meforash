# Inkling guidance comparison collection and review

September 9, 2026. The new two-condition collection and masked review tools are implemented and checked with constructed responses. They extend the [source and input preparation](ATTRIBUTION-COMPARISON-PREPARATION.md). The retained original-language Inkling adapter B, its training, the private chat and the earlier three-condition pilot remain unchanged.

## Frozen development run

The private driver has passed its sixteen-slot constructed dry run, including rejection of changed files, stale provider metadata and mismatched criteria without credential or transport access. It preserves the exact pilot system prompt. Sixty implementation and dependency files were frozen before the separate question author began work. The parent then reviewed the eight questions, all local source references and twenty-three JSON locators, and clarified factual truth versus supplied-source support, ordinary safety application, and control semantics versus formatting.

The active protocol is private `runs/guidance-comparison-v1/protocol-v2.json`, SHA-256 `8198f82a8b1a638487f524d4910868007155b17fdd47f9857e179392d15c6b78`. Its exact sixteen native inputs passed preparation before inference began. An earlier protocol packaging attempt was rejected offline for an unsupported optional file path; it is preserved. Only that metadata entry changed in v2; implementation, questions, criteria, model, guidance and settings did not change.

Collection and both masked reviews are complete. All sixteen answers completed; guided Bible answers were preferred once, less preferred twice and tied three times. Two guided attribution findings failed the prospective gate. Retain the original guidance; see [the results](GUIDANCE-COMPARISON-RESULTS.md). Never rerun or resume the existing private collection.

## Method

Compare `B-original` with `B-guided`: the same saved adapter, question, complete evidence and notices, with only the versioned system guidance added. The completed development comparison has six Bible questions across HT01, HT07 and GC01, plus two general controls, producing sixteen planned answers. The selected passages have prior source-text training and project research exposure; new question wording does not make this an unseen-source benchmark. This comparison tests guidance on a fine-tuned model, not the causal benefit of fine-tuning or whole-Bible expertise.

[`guidance_collection.py`](../bibleprep/guidance_collection.py) regenerates both inputs, renders exact native tokens, binds source, notice, model, settings, protocol and code hashes, and reserves the entire collection before execution. It alternates which condition goes first by case. The caller must explicitly enable execution and supply a credential; the default operation prepares requests offline.

Each submission is durably recorded before the native call. The collector preserves valid final text, including partial answers, with private native receipts and a complete slot inventory. A partial, blank, malformed or uncertain result stops all later submissions. There is no automatic retry or resume. Verification rechecks native prompt tokens, final text, receipts, usage, order and the saved summary. Private artifacts use restricted permissions and exclusive creation.

The primitive accepts explicit checkpoint and rate bindings. An exact experiment driver must separately resolve retained B, validate the current provider metadata and prices, verify every frozen file before each call, and supply the exact question inventory. Captured registry objects do not by themselves detect a changed registry file on disk. These driver responsibilities are part of live readiness.

[`guidance_review.py`](../bibleprep/guidance_review.py) produces separately masked individual and paired packets, with a private mapping. Every returned final answer is reviewed, including partial text. Unsubmitted or unreviewable answers remain in the denominator without becoming semantic failures. Individual and paired judgments must be frozen before the private mapping is accepted for integration. Masking conceals labels and collection order; answer style may still suggest a condition. Review roles and project involvement must be disclosed.

## Prospective decision rule

Before seeing the new questions or answers, the parent selected a conservative rule: all sixteen answers and all six Bible pairs must complete; the guided condition must have zero material errors, unresolved material assertions, attribution or scope errors, and requested-content omissions; guided Bible preferences must exceed original preferences; and all four general-control answers must be semantically correct.

Review covers volunteered material claims as well as requested coverage. A claim not established by the supplied evidence is not automatically false: record unsupported attribution separately, check appropriate sources, and retain unresolved claims explicitly. Descriptive pair counters record the presence of a category of error in each answer; they do not match individual error identities across answers. The zero-error guided thresholds prevent different errors or omissions from canceling one another.

A passing development comparison would support consideration of a limited private trial. It would not automatically change chat, certify historical accuracy, establish readiness for public use, or authorize training.

## Engineering verification

Seven collector tests and eight review tests passed. Compatibility checks also passed. Parent review corrected the numeric-versus-named reasoning-setting mismatch, verified stop-reason derivation, and tightened the decision rule. Independent collector review also caught whitespace-only content being treated as a partial answer; that was corrected before integration. Independent review then tightened the distinction between constructed fixture checks and the actual sixteen-answer decision: fixture integrations now always remain descriptive and cannot return the trial recommendation.

An offline integration used the actual selected source bundles and the cached native tokenizer with the SDK and network mocked. Eight complete constructed answers were preserved and verified. A separate partial case preserved one final text and left seven slots unsubmitted; an uncertain case left seven slots unsubmitted. The corresponding review integration reviewed eight, one and zero texts, retained every planned slot and pair, and correctly refused a positive result for incomplete or deliberately deficient fixtures. These are software checks, not model-quality results.

The collector preserves the full reservation and reports known returned usage separately from uncertain accounting. A submitted request without a terminal journal event after process loss requires manual accounting and cannot pass normal verification; it must not be retried automatically. Any uncertain submitted slot retains its full reservation until reconciled. Provider-internal retry counts and invoices may remain unavailable.

The read-only preflight on September 9 confirmed both private B checkpoint kinds were available and unexpired, with their existing October 6 expiry. The checked [official Inkling rates](https://tinker-docs.thinkingmachines.ai/tinker/models.json) were $1.87 per million input tokens and $4.68 per million output tokens under a temporary discount. Sixteen slots with 8,192-token input and output ceilings reserve **$0.85852160** under the **$2** operator allowance. Recheck availability and rates at execution time; the estimate is not an invoice.

Private checks and receipts are under `runs/guidance-collector-v1/`. The [living queue](../manifests/execution-state.json) records the exact next step. No new training has occurred. After the answer comparison, use remaining failures to propose a distinct candidate G with reviewed data, fresh evaluation and a cost estimate; present that proposal to the owner before training. Recurrence remains optional and deferred.
