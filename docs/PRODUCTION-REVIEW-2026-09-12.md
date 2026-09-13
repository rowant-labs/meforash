# Production and publication review

**Review date:** September 12, 2026
**Scope:** the public source tree, deployed beta architecture, account and analytics data paths, GitHub publication controls, and possible future publication of retained Inkling adapter B.

This is a technical release review, not a penetration test, privacy certification, legal opinion or expert assessment of biblical accuracy. No model export, weight download, training, invitation or weight publication was performed for this review. The sign-in templates and application changes were deployed separately as part of the launch work.

## Decision

The current deployment is suitable for a deliberately bounded public beta with active operator monitoring. It is **not ready for broad production promotion or traffic**. The dominant constraint is intentional single-flight generation: one process accepts one answer at a time and rejects every simultaneous answer with HTTP 409. A live integration check measured 22.85 seconds to completion, 21.73 seconds to first visible text, and a simultaneous second request returning 409. There is no queue, fairness rule or service-level throughput evidence.

Adapter B should remain private. Tinker's documented PEFT export path makes an adapter-only artifact the best first publication option later, but B has never been exported or independently loaded. Its exact provider base-weight revision, converted tensor coverage and output parity remain unverified. Export or publication requires a separate owner decision.

## Prioritized findings

| Priority | Finding | Evidence and consequence | Required disposition |
|---|---|---|---|
| P0 | One global generation slot | `BetaApplication` has one process-wide `running` flag; `ChatModel` also has a non-blocking single-flight lock. A slow answer can exclude every other user for up to the 300-second generation deadline. The live simultaneous request returned 409. | Keep traffic explicitly bounded. Before broad promotion, implement a bounded fair queue or an equally clear admission design, publish the expected wait/busy behavior, and measure sustained latency and rejection rates. A queue improves fairness; it does not create provider capacity. |
| P0, partly fixed | Provider-failure recovery requires an operator restart | An unexpected transport/provider error blocks the `ChatModel` instance until restart. This review fixes false readiness: `/health` now returns 503 for an existing blocked/closed model, and new submissions reject before quota or cost reservation. Offline tests cover these states and lazy startup. | Follow [the restart runbook](BETA-READINESS.md), preserving uncertain accounting. Automated recovery and ongoing health monitoring are not established by this change; Railway deployment health checks alone are not a continuous restart supervisor. Exercise recovery before broad traffic. |
| P1 | Horizontal scaling is not safe as a simple replica-count change | The busy flag and result jobs are process memory. SQLite makes local allowance accounting atomic but is not a distributed generation lock or shared job store. A second process can admit another model request while losing access to the first process's result token. | Define the desired provider concurrency first. For multiple replicas, add shared admission, durable/shared job state, cost reservation semantics and routing or affinity; then load-test the deployed topology. |
| P1 | Privacy depends on operational and third-party controls outside this tree | Conversation text and selected source context go to Tinker. The app deliberately avoids storing prompts, answers, email addresses and raw IPs in SQLite, but holds results in process memory and may hold a sign-in handoff in browser `sessionStorage` for up to ten minutes. Cloudflare's remote analytics script runs in the same page context on the canonical site. Railway/Cloudflare logs, volume encryption, backups and staff access were not inspected here. | Document and verify operational retention, backup, encryption and access settings. Make an explicit decision about the analytics script trust boundary on the conversation page. Add a deletion/revocation runbook and a retention schedule for pseudonymous ledger records. |
| P1 | Public-repository controls are partly configured | The repository is public. GitHub secret scanning and push protection are now enabled and the API reported zero open secret-scanning alerts. `main` remains unprotected, no workflow is tracked, and Dependabot security updates are disabled. | Protect `main` and require an appropriate review/check policy once a stable source-only CI job exists. Enable or consciously schedule dependency alerts/updates. Review or disable other public surfaces such as the wiki if unused. |
| P1 | Full source attribution should be easier to find in the app | The runtime bundle preserves OSHB and SBLGNT notices and source cards link upstream, but the compact browser attributions do not reproduce all upstream requested attribution wording. | Add a persistent source-credits view containing the pinned editions, full attribution text, license links and modification statement before materially expanding source display or redistributing prepared text. Obtain legal review for any uncertain interpretation. |
| P2 | Email authentication has a monitoring baseline, not enforcement | DKIM and SPF resolve for the Resend sender. A scoped `_dmarc.auth.meforash.com` record now publishes `v=DMARC1; p=none; adkim=r; aspf=r`. It is non-enforcing, has no aggregate report address, does not change root-domain policy, and does not prove inbox placement. | Inspect real delivered-message `Authentication-Results` for SPF/DKIM/DMARC alignment. Add reviewed reporting if wanted, then consider quarantine/reject only after the evidence supports it. |

P0 means the item blocks broad traffic or a general production claim. It does not require shutting down the explicitly limited beta while the owner accepts the stated behavior and monitors it.

## Verified behavior and privacy boundaries

The following points were verified from the current code, tests or live integration checks:

- Hosted session cookies are `Secure`, `HttpOnly` and `SameSite=Strict`. Mutating requests require exact host and origin checks; CORS is not enabled. Responses use `no-store`, clickjacking and content-sniffing defenses, a restrictive content security policy, and `no-referrer`.
- Model answers and source text are rendered as text/DOM nodes. Model-supplied markup and links do not become active HTML. Source links are limited to GitHub HTTPS URLs.
- The request decoder rejects duplicate JSON keys and non-finite numbers. HTTP bodies are capped at 192 KiB; validated conversations are further limited by message count and content constraints. Source selection is capped at 40 verses and three references.
- Application server request logs are suppressed and provider-child output is redirected. Tinker telemetry-disabling environment values are set by the runtime launcher.
- The SQLite ledger stores verified Supabase user UUIDs, token hashes, keyed email/IP hashes, request identifiers, timestamps, status, terms acceptance and cost accounting. It does not intentionally store prompts, answers, raw email addresses or raw IP addresses.
- Conversation and source content are held in browser memory and server memory. During email sign-in only, the browser can place messages, source cards and the draft in `sessionStorage` for up to ten minutes; restore, cancellation, new-chat and logout paths clear it. Completed server jobs expire after fifteen minutes when cleanup is next triggered, so an idle process may retain them longer in memory until later activity or shutdown.
- Cloudflare Web Analytics is injected only for the canonical HTTPS site. The code sends no custom conversation events, and the public site identifier is not a credential. The remote script remains a third-party code dependency in the page that holds conversation state; this review does not claim that present or future script behavior is incapable of reading it.
- Live checks blocked an unauthenticated result poll and revoked the tested session on logout. The configured email allowlist/site URL point to `meforash.com`; email codes are six digits with a 600-second lifetime and a 30-per-hour send limit.
- The owner reported a successful real-iPhone sign-in/autofill test after the email template rollout. This is a functional device check, not an inbox-deliverability guarantee.
- The application has no automated account deletion flow. The privacy text routes deletion requests to support. Deleting an upstream Supabase identity does not by itself document local session revocation and ledger-retention handling.

Data sent to Tinker is covered by the project's provider relationship and current [Tinker Terms](https://thinkingmachines.ai/legal/terms/), but provider, hosting and mail-service control-plane settings were not independently audited. The privacy policy accurately identifies the main intended recipients; jurisdiction-specific consent, deletion and retention requirements still need qualified review.

## Concurrency and scaling facts

The web server uses a thread per HTTP request, while generation has one global process slot. Browsers poll roughly every 900 milliseconds. There is no application-level cap on simultaneous poll/request threads, and no measured behavior under many polling clients. The available timing observations are functional examples, not a latency distribution or throughput benchmark.

The current design provides deterministic cost admission for one process, but it does not establish:

- provider capacity for concurrent B generations;
- fairness or maximum wait time under bursts;
- behavior through deploys, restarts or a lost in-memory result;
- multi-process or multi-replica result routing;
- recovery from the model's permanently blocked failure state; or
- resource limits under many authenticated polls or deliberately slow clients.

Before broad traffic, collect at least p50/p95/p99 time-to-first-text and completion latency, busy/rejection rate, queue wait if introduced, disconnect/cancellation behavior, memory and thread count, and cost under a representative mix of short and source-assisted conversations.

## GitHub publication posture

At review time, `https://github.com/rowant-labs/meforash` was public, the reviewed local HEAD matched `origin/main`, and there were no GitHub Releases or published weight artifacts. The current tree contained no tracked `.env`, private run directory, raw/prepared corpus, SQLite ledger or private checkpoint locator. Commit authors used a GitHub noreply address.

The source-only suite passed **601 selected tests** and reported **94 asset-dependent tests excluded**; excluded tests are not passes. Integration checks also reported **114 targeted application/account tests** passing, including account, beta, preview, model, streaming, sources, Railway, usage and auth-email coverage.

After the readiness and inline-agreement changes, the frozen source-only suite passed **605 tests**, with the same **94 asset-dependent exclusions**. The browser suites passed **26 scenarios**. A 390-pixel browser check confirmed the direct email-to-code flow, absence of an agreement dialog, intact OTP attributes, and no horizontal overflow using mocked email delivery.

The publication scan has bounded meaning:

- GitHub secret scanning and push protection are enabled. GitHub documents default secret scanning as covering recognized secret types in full Git history; zero open alerts does not cover ordinary personal information, unsupported credential formats or every generated artifact. See [GitHub's secret-scanning description](https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning).
- A local current-tree review found no actual credential assignment, private model locator, personal filesystem path, production database or conversation log in tracked files.
- A targeted local pattern scan covered all 29 commits and classified its matches as validators, synthetic canaries, blank configuration fields or documented placeholders. It was not a comprehensive PII search or an independent security assessment.
- Issues, wiki pages, releases, package registries, caches, forks and future commits are separate publication surfaces. Their content was not established by scanning the tracked tree.

The top-level README and [open-source release candidate](OPEN-SOURCE-RELEASE-CANDIDATE.md) were updated in this review so their launch and repository claims describe the current public state while preserving dated historical results.

## Adapter B publication options and license evidence

| Option | Current verdict | Main conditions |
|---|---|---|
| Keep B private on Tinker; publish code, methods and aggregate results | **Recommended now** | This is the current state and needs no weight export. Keep checkpoint identifiers and private execution records out of public artifacts. |
| Publish a PEFT/LoRA adapter only | **Best first weight artifact after separate approval** | Export into private staging; identify and pin the exact provider base-weight revision; verify converted tensor coverage, including trained attention, MLP and unembedding parameters; hash the artifact; load it against that base outside Tinker; compare representative outputs; complete license/attribution and model-card review. |
| Publish a merged full Inkling model | **Not recommended as the first artifact** | Tinker documents this path, but it duplicates a roughly 1.9 TB base and adds major hosting, integrity and redistribution burden. It still requires every adapter-only gate and a fuller base redistribution review. |
| Publish the training-state checkpoint | **Keep private** | It contains optimizer/resume material rather than the minimal inference artifact. Publish only for a distinct reproducibility purpose after a separate rights, privacy and security review. |

Verified license and tool evidence:

- The official [Inkling repository](https://huggingface.co/thinkingmachines/Inkling) identifies the base as Apache-2.0 at revision `828496eeae4c243ff1a22f7f28ff83694f2f7bc9`. That exact repository snapshot exposes Apache-2.0 metadata, but no standalone `LICENSE` or `NOTICE` file was found in its file listing. The local manifest pins tokenizer assets to that revision; it does **not** prove that Tinker's base weights for B used the same revision.
- Inkling's model card links the separate [Thinking Machines Model Acceptable Use Policy](https://thinkingmachines.ai/model-acceptable-use-policy/), which states that it governs model weights, parameters, associated materials and modified versions. A future release packet must include and assess that policy alongside the Apache metadata; this review does not resolve their legal interaction or characterize B as unencumbered open-source weights.
- Tinker's official [LoRA deployment tutorial](https://tinker-docs.thinkingmachines.ai/tutorials/deployment/lora-adapter/) documents conversion into PEFT adapter files and a separate merged-model path. Its [Hub publication tutorial](https://tinker-docs.thinkingmachines.ai/tutorials/deployment/publish-hub/) documents publishing an adapter or merged model. Documentation establishes a supported workflow, not that this particular B checkpoint converts completely or reproduces Tinker outputs.
- The pinned [OSHB license](https://github.com/openscriptures/morphhb/blob/3d15126fb1ef74867fc1434be1942e837932691f/LICENSE.md) describes the WLC text as public domain and licenses OSHB lemma and morphology work under CC BY 4.0 with specified attribution. The project preserves the pinned source, notice and modification provenance.
- The official [SBLGNT license](https://www.sblgnt.com/license/) licenses SBLGNT under CC BY 4.0. The project preserves its pinned revision, copyright attribution, license and modification provenance.

CC BY 4.0 permits sharing and adaptation with attribution, a license link and change indication. Whether learned adapter parameters legally constitute adapted source material is outside this technical review. A B model card should identify both training sources, editions/revisions, complete requested attributions and known corpus limitations regardless of that legal conclusion.

## Evidence still needed for a broad production decision

Broad production promotion remains blocked until the P0 issues are fixed and exercised. The next review should also require:

1. representative concurrency/load results and a tested generation-failure recovery path;
2. verified infrastructure log retention, persistent-volume encryption/access, backup/restore behavior and edge security headers;
3. a documented account deletion, local-session revocation and ledger-retention procedure;
4. inspection of delivered email authentication headers and a deliberate decision about stronger DMARC policy;
5. a protected-branch/CI/dependency-maintenance policy appropriate to a public service; and
6. full source credits in the browser plus qualified review of privacy terms and any planned model artifact.

The existing development evaluations support the choice of B among tested candidates. They do not establish expert accuracy, whole-Bible reliability, safety for sensitive pastoral decisions, or a general production quality threshold.

## Deployment verification

Application commit `5ac8d1a` deployed successfully to Railway. Canonical homepage, Terms, Privacy, JavaScript and health routes returned 200; live JavaScript bytes matched the reviewed files. A stale-version auth request returned 403 before sending email. The deployed 390-pixel sign-in check reached the OTP field without an agreement dialog, retained the autofill attributes, did not auto-submit, and had no horizontal overflow. Email delivery was mocked for this final browser check; the earlier real-iPhone success remains the owner-reported end-to-end check. No additional paid generation or weight operation was needed for these interface checks.
