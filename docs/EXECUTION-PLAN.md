# Execution plan

Launch update (September 10, 2026): Meforash now has a Railway owner-access beta with a verified Linux runtime and a completed HTTPS B answer. Public guest access, saved-account integration and custom-domain DNS remain pending. See [launch progress](LAUNCH-PROGRESS.md). Launch work takes priority over further model research or training.

Current execution status (September 10, 2026): the bounded [Candidate G sequence is complete](CANDIDATE-G-RESULTS.md). G completed six updates; both full checkpoints and all four required B/G roles were verified. All 60 answers and 30 pairs were reviewed. Across the 24 Bible pairs, G was preferred on 3, B on 10, with 11 ties. Retention diagnostics passed, but the frozen preference gate independently failed, so retain B. Finding counts are AI-review flags, not factual-accuracy scores; the root review disputes the James material-error flag applied to both arms and treats some omissions as rubric/notice-level, without changing the preference failure. Estimated execution cost is $1.58403889; with the $3 storage contingency it is $4.58403889, below the $7.66376908 reservation. No further training, recollection or promotion is authorized. The B local preview has been restarted and its HTTP/source status verified without a model request; the later hosted beta work is recorded above. Evaluation-severity review is relevant before another training proposal, not a prerequisite for this owner beta. See the [frozen method](CANDIDATE-G-EXPERIMENT.md) and [living state](../manifests/execution-state.json).

Updated September 10, 2026. This is the current forward plan. Earlier training protocols and results remain historical records; this document does not reopen their experiments. The [evaluation runbook](EVALUATION-RUNBOOK.md) specifies where and how to test, the [agent handoff](AGENT-HANDOFF.md) gives a starting prompt, and the [living execution state](../manifests/execution-state.json) tracks the next work packages.

## Objective and current position

Build an **English-speaking Bible assistant whose answers are grounded in the earliest recoverable biblical wording and its historical context**. Actual original-language fine-tuning remains central. The product should answer precise textual questions and broad life questions; offer Bible-based, non-denominational reflections when the question calls for them. People should not need ancient-language knowledge or a reference number to ask a useful question. See the accepted [charter](PROJECT_CHARTER.md).

We have a real fine-tuned model and a private conversational prototype. We have not established dependable whole-Bible historical expertise. Training on a selected edition is not the same as training on every early witness, and fluent English is not proof of accurate translation. The next stage joins better evidence, measured English answers, and further training only where a distinct hypothesis warrants it.

| Area | Measured or implemented | Remaining gap |
|---|---|---|
| Base and adapter | Full `thinkingmachines/Inkling`; retained original-language adapter **B**, rank 8, LR 1e-4, one development pass: 136 updates, 3,280,433 input positions | Base-weight revision is not fully pinned; permanent preservation and external loading are unproven |
| Source corpus | Complete prepared OSHB/WLC and SBLGNT editions: 66 book files, 31,152 source verse records; training excludes development holdout chapters | Selected editions are not a unified original text; additional early witnesses, versions and historical comparanda are incomplete |
| Learning evidence | 77.3% lower NLL on 12 held-out Hebrew/Greek windows | Text prediction only; no Aramaic in that sample and no established overall English accuracy gain |
| English instruction experiments | C/D, gentler E, revised-target F and Candidate G completed; B retained | Latest G versus B: 3 preferred / 10 less preferred / 11 ties on 24 Bible questions; retention passed and preference failed. Audit severity labels before any distinct future proposal |
| Private chat | B answers English questions with explicit passage lookup and source cards at the local preview | No topical search, historical dossier retrieval, public account service or production hosting |
| Historical evidence | Eight private research drafts; six GT01/AT03 components have conditional private input/display decisions through verified notices | The subset has AI review without expert certification; all training uses and most components remain pending, and 32 of the planned forty records remain |
| Open source | Portable code/docs, manifests, licensing records and publication checks | No remote, commits or public release; a key plus a clean clone cannot recreate private B |

The latest comparison is documented in [v3 results](INKLING-REVISION-RESULTS-V3.md); source preparation in [the first pack](EVIDENCE-FIRST-PACK.md); chat behavior in [the private chat guide](PRIVATE-CHAT.md). The earlier base-model size screen is complete. Do not restart model shopping without a specific serving or quality problem.

## Order of work

P0's metadata/pricing preparation and P1's offline implementation are complete. P0 retention changes remain pending. P2 has a six-component conditional delivery subset but broader source work remains. P3 completed the actual known-topic pilot. P4's guidance diagnosis and P5's Candidate G sequence are complete. B beta hosting/recovery readiness and an evaluation-severity audit are the next bounded work; chat loading remains separate.

| ID | Work package | Dependency and completion evidence |
|---|---|---|
| P0 | Preserve B and prove how it can be restored | Read-only checks and priced proposal complete; retention decision and later restore verification remain |
| P1 | Build the private evidence review export and gap queue | Complete: eight records, 130 review tasks, 22 passing tests and unchanged v1 hashes; see [results](EVIDENCE-REVIEW.md) |
| P2 | Resolve starter-pack source/use gaps and expand coverage | P1 helps prioritize; separately recorded scholarly review and component-use decisions; eligible subset may advance before all forty finish |
| P3 | Freeze and run the known-topic evidence pilot | Complete: exact source/criteria/protocol freeze, 18/18 native collection and review, bounded cost, narrow decision |
| P4 | Diagnose evidence output and broaden evaluation | Guidance comparison complete; its failed attribution gate supplied Candidate G's distinct hypothesis and prospective evaluation |
| P5 | Execute the bounded Candidate G experiment | Complete: 60/60 answers reviewed; G/B/tie 3/10/11 on 24 Bible pairs; retention passed, preference gate failed, B retained |
| P6 | Prove sustainable serving for the actual adapter | P0 identity/restore work; exact model compatibility, measured cost/latency, bounded multi-user backend |
| P7 | Publish the inspectable project, then launch a bounded public beta | Publication checks and honest reproduction instructions; app launch additionally needs P4 quality review and P6 serving |

Code/docs can be published before all model work is finished. P7's repository release does not depend on proving every historical claim, provided unreviewed/nonredistributable artifacts stay excluded and limitations are explicit. Public beta requires a stronger quality and operating review than the private research preview.

## P0 — preserve the trained model

Read-only preparation is now complete: at **September 8, 2026 01:52:24 UTC** (September 7 local time), both retained B checkpoints were available and private in the same owned Inkling run. The sampler is about 5.04 GB and expires **October 6 at 15:58:33 UTC**; the training state is about 15.13 GB and expires five seconds earlier. Keeping both is estimated at **$2.02/month** at the checked storage rate. See [the concrete preservation proposal](CHECKPOINT-PRESERVATION.md). Expiry removal remains pending an owner decision; this metadata check does not prove a restore or external export. The new private receipt is `runs/checkpoint-preservation-v1/read-only-metadata.json`; the original checkpoint records remain `runs/inkling-original-text-v1/checkpoints.json`.

1. Inspect the existing receipt and local installed SDK; recheck provider availability if the observation is stale. Never print credential values, checkpoint URIs or raw provider responses. Verify the training-state checkpoint separately from the sampler.
2. Check current official Tinker documentation for retention extension, download/export, restore, storage/egress cost, and Inkling support. Historical links in [the training plan](training-plan.md) are discovery pointers, not proof of current support.
3. Record a concrete choice: retain/extend the provider checkpoint, download a supported artifact, or both. Include exact base/tokenizer/template dependencies and how to verify artifact identity. Retain existing provenance receipts unchanged; a renewed provider location needs a separate migration record.
4. Complete preservation under an applicable explicit allowance; otherwise present the concrete priced operation for approval. Do not infer purchase authorization from an expired experiment cap. Perform a bounded restore/inference check when authorized, and record what it proves and the next expiry.

If the checkpoint has expired, stop B-dependent generation and report that fact. Continue offline work; never silently substitute A or repeat training. No checkpoint refresh automation is currently configured. Aim to settle preservation well before the recorded expiry, not on its final day.

## P1 — completed review export

**Complete:** a local, model-free review export for the existing eight records. [The tool report](EVIDENCE-REVIEW.md) gives commands, counts and limits. Its final private packet is `runs/evidence-review-v1/final/index.html` with a companion JSON export. All 695 internal HTML links resolve, deterministic rebuilding matches, and all sixteen v1 source-file hashes remain unchanged. The 130 queue entries are traceable review tasks, not 130 established factual errors.

Implemented module: [evidence_review.py](../bibleprep/evidence_review.py), with [constructed tests](../tests/test_evidence_review.py) and a [separate engineering reference map](../manifests/evidence-reference-map-v1.json). The original [public inventory](../manifests/evidence-first-pack-v1.json), [draft validator](../bibleprep/evidence.py) and source records remain unchanged. The contract below is retained for maintenance; do not rebuild this milestone on resumption.

Required behavior:

- Read the eight hash-bound v1 JSON records without modifying them or their Markdown companions. Use the draft validator and validate source-byte references. Preserve null hashes and unverified locators rather than manufacturing completeness.
- Produce private JSON plus a readable HTML or Markdown index with tables for claims, supporting/contrary citations, readings and attestation, four date categories, component rights, and unresolved issues. Every row must point back to its record ID and field/citation ID.
- Derive a gap queue with issue ID, affected claim/component, reason, evidence needed, next action and status. Distinguish missing source bytes, uncertain witness/line attribution, scholarly judgment, and use restrictions; a hash alone resolves only the first.
- Preserve actual schema names: `citations[].id/source_id/locator/pinned_version/content_sha256`, `readings[].id/entity_type/stable_entity_id/attestation`, `claims[].supporting_citation_ids/contrary_citation_ids/assessment/limitations`, the four `dates` fields, `rights_by_component`, and `review.unresolved_issues`. Consult the schema for complete types.
- Make a **separate explicit reference mapping** for later indexing. Draft chapter keys are not canonical: AC01 uses `Ezra.4`, while other records use source-prefixed keys such as `oshb:Gen.4`. Normalize through a reviewed mapping with source/edition coordinates and reject ambiguity. Do not join by raw string equality or rewrite v1 to make keys match.
- Confine output to ignored private directories; reject symlink/path escapes and overwrite attempts. Escape rendered text, do not automatically fetch URLs, and expose no workspace files through the chat server. No API key or model call is needed.

Done means all eight appear exactly once, links resolve, gaps reflect the inputs, deterministic content is reproducible, v1 hashes remain unchanged, and focused tests cover cross-reference errors, contradictory/unknown rights, null source hashes, reference ambiguity, unsafe rendering and path confinement. Publish the reusable code and a concise preparation report; keep generated research content private.

## P2 — make evidence eligible, then broaden it

The target remains [twenty textual dossiers plus twenty context notes](HISTORICAL-EVIDENCE-MILESTONE.md), not eight passages as the product's permanent scope. Work in bounded batches, preserving Hebrew, Aramaic and Greek coverage and distinguishing biblical text, alternative witnesses/versions and historical comparisons.

The first bounded HT01 / HT07 / AT03 source-gap batch is complete: three additive records contain thirteen findings with exact transcription/edition locators and retained source snapshots. Read the [P2 follow-up report](SOURCE-GAP-REVIEW-P2.md) and [inventory](../manifests/source-gap-followups-p2-v1.json). P2 remains partial. The separate [component registry/projection](EVIDENCE-ELIGIBILITY.md) and [specialist question packet](SPECIALIST-REVIEW-PACKET.md) are now implemented; further source expansion remains pending. A later v3 registry now grants six conditional private input/display decisions through notice-complete delivery; all other uses remain pending. The queue separately records fourteen missing snapshots, fourteen missing immutable versions and nine unchecked attestations across the pack; these overlap and must not be counted as independent factual failures. Preserve v1 and record any corrected research in a new version. Directly supported findings may advance while inaccessible sources remain explicitly reported gaps; no draft automatically gains app or training eligibility.

For the first pack, prioritize exact Hebrew witness attestations and line locators; the Daniel Hebrew/Aramaic boundary and separate Greek versions; Mark's edition-versus-manuscript readings and correction layers; and the limits of the Assyrian, Persian, administrative-Aramaic and Pilate comparisons. A secondary scholarly report may remain useful when accurately attributed; it must not be promoted to a direct manuscript transcription.

The [STEP lexical review](../licenses/STEP-LEXICAL-REVIEW.md) identifies a separate permission notice for the selected Hebrew definitions. Do not import them under a generic repository license. Existing noncommercial/no-derivatives components also need separate use decisions or suitable replacements. Retain distinct app-display, redistribution, training and adapter-release statuses per component.

The current validator intentionally accepts only research drafts. **The separate versioned review/eligibility registry and export projection are now implemented** for whole claims/readings and their citation dependencies; do not weaken the v1 validator or flip draft flags to get content into chat. Bind each decision to exact record/component hashes, use, reviewer role, rationale and unresolved limitations. AI checks remain labeled AI checks. A specialist review requires an actual qualified review, not an invented reviewer name or an LLM grade.

Prepare a short, answerable review packet before requesting outside help. The owner has not authorized external messages or commissions. If a specialist is unavailable, finish the source inventory, reproducible references, constructed-fixture engineering and runner preparation. Partial eligible coverage can ship privately with explicit gaps; do not wait for exhaustive manuscript coverage or turn an unavailable source into invented text.

## P3–P4 — evaluate and integrate evidence

P3's constructed planner, accounting, native-result handling, exact request preparation, paired review, notice-complete delivery, coordinator and live pilot runner are implemented. The actual [known-topic pilot](EVIDENCE-PILOT-V1.md) froze its source-bound protocol before generation and returned 18/18 native-verified answers. All eighteen answers and twelve pairs were reviewed before label-map integration. The run used 24,529 input and 8,517 generated tokens, with an estimated sampling cost of $0.08572879 and no reconciled invoice, under a $0.9658368 reservation and $2 cap.

The frozen narrow gates passed: B-memory had two critical-error answers and three omission answers, while the packet and lookup arms each had zero under the stated criteria; packet versus memory was 3 preferred, 0 less preferred and 1 tie. Packet and lookup received identical rendered inputs, so their 1/2/1 result demonstrates generation variability rather than retrieval gain. A separate parent audit found an additional Daniel language-boundary error and blurred project-gloss/source attribution in a lookup answer. The criterion-scoped zeros do not certify all claims. Keep B and the private chat unchanged. That diagnosis and a separate three-family, sixteen-answer guidance comparison are complete. The [guidance result](GUIDANCE-COMPARISON-RESULTS.md) failed its adoption gate and supplied the attribution/scope findings addressed by the frozen Candidate G experiment.

Use the [evaluation runbook](EVALUATION-RUNBOOK.md). Freeze fresh questions and source-based criteria before using known failures to alter the prompt or evidence-selection policy. Conceal the evaluation contents from training/prompt authors until their artifacts are frozen; disclose any unavoidable role overlap.

First test lookup deterministically: eligible evidence only, exact references and follow-ups, safe rendering, context limits, no unsupported witness claims, and explicit “no evidence found.” A later topical-search increment should retrieve relevant passages for broad English questions and preserve their context. Start with a simple local index and inspectable rankings; embeddings, a database and an agent loop are options to justify with failures, not prerequisites.

Then compare retained B with no supplied evidence, B with a fixed reviewed evidence packet, and B with the actual lookup result. This isolates access to evidence from evidence selection and from the model's interpretation. Add a contemporary unchanged A under matching evidence if making a claim about the fine-tune's benefit. Keep the serving model and native format fixed during the evidence comparison.

Use development diagnostics on the eight familiar topics as development evidence. They cannot establish independent generalization. If the approved subset cannot support the frozen fresh questions, continue engineering and curation; do not fill the gaps with draft claims or alter the questions after seeing answers.

The application should give readable English answers and expandable evidence: edition/witness, wording or translation, locator, important alternatives and uncertainty. Source cards identify supplied evidence; claim-to-citation links must actually support the associated claim. Preserve narrow translation focus, complete requested clauses, and useful non-denominational reflection for personal questions. Fine-tuning does not remove the base model's prior influences.

## P5 — completed Candidate G experiment

The [Candidate G experiment](CANDIDATE-G-EXPERIMENT.md) was the distinct follow-up selected from the P4 attribution and coverage findings. Its 104 new examples passed independent AI review; sixteen exact old training rows supplied rehearsal. The 96/24 dataset, six-update recipe, collector and thirty-question evaluation were frozen before execution. G completed six updates, and all 60 answers and 30 pairs were reviewed. The [final result](CANDIDATE-G-RESULTS.md) retains B: G/B/tie was 3/10/11 across 24 Bible pairs, failing the preference gate even though every retention diagnostic passed. No retry or recollection occurred. Recurrence remains optional and deferred.

The design follows this P4 error analysis:

- If a relevant source was not retrieved, fix retrieval first.
- If B misreads a correctly supplied passage or fails to translate all requested clauses, test targeted source-to-English supervision using reviewed examples and explicit alternatives.
- If the model conflates witnesses, reported readings or dates even with correct evidence, test training that keeps those distinctions visible.
- If original-language domain adaptation on newly eligible early-witness/context material is the hypothesis, retain source labels and split by passage/witness families. Do not concatenate incompatible witnesses into an invented original.

The frozen method separately named G, started from preserved B with a fresh optimizer, and documented masks, sampling balance, tokenizer/template, limits and cap. It forbade rerunning E/F, adding epochs, changing the gates or recollecting after a failure. Collection completed without invoking the stop contingency.

The predeclared rule required the English-answer and retention gates together. Candidate G passed retention and failed preference, so no promotion or further training follows. Preserve B, G and all negative results. Before any distinct future training proposal, audit the evaluation's severity labels and prepare a newly frozen independent evaluation; do not reuse this result to justify automatic recollection or another run.

## P6–P7 — serve and publish

The [dated serving review](INKLING-B-SERVING-FEASIBILITY.md) is complete: native Tinker inference works, while exact B export and Fireworks import remain unverified. Next check converter/base/target compatibility locally before a bounded serving measurement. The current path is browser → local Python service → B on Tinker, with source lookup local. Vercel can host a future frontend; a long-running backend can run on Railway or another suitable service. Supabase is optional for public accounts, eligible-source indexing and usage records. These are architecture candidates, not deployed services or newly verified price recommendations.

Before choosing public infrastructure, prove the actual Inkling adapter works under the provider's current terms, concurrency and timeout constraints. Tinker private inference already works; external export/load and serving support remain unverified. If evaluating Fireworks or another host, verify the **exact base, adapter format, tokenizer and native reasoning template**, rather than treating generic LoRA support as sufficient. A portability failure does not authorize silently replacing the trained model.

Measure median/tail latency, completed answers, input/output usage including reasoning, concurrent-request behavior and cost per completed conversation. Record estimated and invoiced cost separately. Public controls need authentication or bounded anonymous use, rate limits, a global spending ceiling, cancellation/failure semantics and explicit data retention. Keep secrets on the server and hidden model reasoning out of the user interface. Chat content remains excluded from training by default.

For the repository, follow [publication practices](PUBLICATION.md). Publish original code/docs, choices, provenance, evaluation methods/results and a model card; distribute data/adapters only where permitted. Verify a clean clone and state exactly which private/third-party artifacts are still required. Review the exact files, history and author metadata before first publication; previous local scans are snapshots, not permanent clearance. The user allows public development, so prepare a concrete release without restarting a general discussion about whether the project should be open source.

## How to keep this plan current

After a bounded task, update the living state with completed artifacts, validation, the next action and a specific blocker if one exists. Add meaningful decisions to [DECISIONS.md](DECISIONS.md). Do not rewrite completed protocols, datasets, reports or private receipts; corrections get a new version with timing and rationale. Update this plan when direction changes, keeping observed results separate from proposed gates.

Routine offline edits, source reading, tests and review preparation can proceed under the project request. Candidate G's authorization is exhausted. Any different paid experiment or use of unused ceiling headroom needs a distinct protocol and spending allowance. Current work should advance B beta hosting/recovery readiness and the evaluation-severity audit without automatic training or recollection.
