# Meforash launch progress

September 10, 2026. The owner authorized moving from the research preview toward a hosted product, retaining Inkling B. No further training is required for this milestone.

## Experience

The beta interface is branded Meforash and presents an open question field. It has no suggested-question chips or mandatory modes. Training, source, and privacy details are expandable. Model answers render a bounded subset of Markdown through safe DOM text nodes, with source editions and original-language passages in a separate panel.

Invitation authentication remains in place for the hosted owner beta. Guest access, Supabase accounts, saved conversations and a fair request queue are subsequent integration tasks, not existing features. No invitation has been sent to another person. The initial hosted owner allowance is $5 total estimated inference spend; this is not a recurring daily reset or a provider invoice cap.

## Constructed conversation check

Four unchanged-B requests completed, using the existing system prompt, native settings and explicit passage lookup. The private protocol reserved $0.33287424 under a $0.40 ceiling. Returned token estimates total $0.01500910; the provider invoice is unreconciled.

| Constructed request | Completion time | Product observation |
|---|---:|---|
| Hebrew context of Psalm 23:1 | 35.336 s | Relevant source explanation, but appended a reflection to a narrow textual question. |
| Follow-up about guaranteed money | 16.176 s | Distinguished poetic trust from a guarantee of financial abundance. |
| Responding to disappointment by a friend | 25.572 s | Provided Bible-based reflection; modern boundary/forgiveness formulations remain interpretations, not direct translations. |
| Unrelated Python sorting function | 13.874 s | Provided general-purpose code, confirming that topical fine-tuning does not enforce a service-use boundary. |

These are constructed development checks reviewed by the integrating AI assistant, not an independent scholarly benchmark or traffic performance estimate. The first timing includes local initialization. No repeated sampling, prompt change, promoted starter example, or model switch followed. Usage limits must be enforced independently of answer topic. Broad personal questions remain within the intended product scope.

## Hosting and publication

A separate Railway project, service and persistent volume now host the owner-access beta. Runtime assets are kept in an allowlisted private bundle, separate from the public source and from the server-side API key. See [deployment instructions](RAILWAY-BETA-DEPLOYMENT.md).

The Linux container built successfully with the pinned CPU runtime. The uploaded 25-file bundle passed in-container B provenance, source, tokenizer and renderer verification. HTTPS sign-in, unauthorized rejection, foreign-origin rejection, a real source-backed B answer, and logout revocation passed. The constructed hosted answer took 32.416 seconds and added $0.00464031 estimated inference spend. Desktop and 390-pixel-wide sign-in layouts were visually inspected.

The source-only suite passed 552 tests; 94 asset-dependent tests were explicitly excluded. A legacy privacy assertion was corrected to match the complete synthetic question ID rather than the same two characters inside a UTC timestamp; its prior bytes were preserved privately and no experimental result changed. Supabase migrations and 31 SQL assertions are prepared but have not run against PostgreSQL.

A subsequent deployment preserved the exact $0.00464031 accounting balance; no extra model request was made for the restart check. The reviewed initial source commit was published to the public GitHub repository on September 11, 2026. Supabase project selection and custom-domain DNS remain pending.

Both retained B checkpoint expiries were removed and verified after a storage-cost notice. Estimated ongoing storage for the sampler and training state together is $2.016734/month at $0.10/GB-month. Model weights remain private; no export or training took place.

Integration review also fixed an empty-Markdown-marker progress bug in the answer renderer. The hostile-formatting regression now includes empty heading and list markers, and passes without allowing model HTML or links to execute.


## September 11 product follow-up

The public model name is Meforash 0.1, mapped to unchanged original-text-only B in [model versioning](MODEL-VERSIONING.md). The hero says “Fine-tuned on original languages.” No new training or prompt change accompanies this naming.

Streaming is a prospective transport change. Tinker documents streaming text and separate thinking events for fine-tuned checkpoints through its [Anthropic-compatible endpoint](https://tinker-docs.thinkingmachines.ai/tinker/compatible-apis/anthropic/). Our deployed native sampling route returns completed answers. Before switching, verify exact B access, input rendering and effort equivalence, first-answer-token latency, final completeness, disconnect accounting and exclusion of thinking events from browser output. Retain the current route until that check succeeds. The compatible endpoint remains beta with variable latency; no speed improvement has been measured.

The owner approved a dedicated Meforash Supabase project under Rowant Labs, three guest questions before sign-in, and an initial allowance of 20 questions per account per day that the operator can adjust. The project was created in US East (Ohio) on the Micro compute size, independently verified `ACTIVE_HEALTHY`, and linked with the local Supabase CLI. No migration has been applied. Guest access, authentication, quota enforcement and saved-history integration remain unimplemented; invitation access and session-only conversation memory are unchanged. Global and per-account limits must survive restarts, and guest limits need abuse controls independently of model topic.

The approved sign-in flow preserves the guest's active conversation through authentication using temporary same-tab storage. It restores that conversation to the signed-in page's in-memory state and clears the handoff data after use or abandonment. Signing in does not automatically save the conversation to persistent history; saving remains a separate explicit action.


## Account implementation follow-up

Guest access, same-page email-code sign-in, adjustable 20-question UTC daily account allowances, and temporary sign-in continuity are implemented and tested locally. The dedicated email sender is verified and SMTP is configured. Public rollout is still gated while hosted checks and actual email delivery are verified. See [account access](ACCOUNT-ACCESS.md). No history migration, saved-history interface, queue, streaming change or training was included.


## Hosted accounts — September 11, 2026

Guest access and email accounts are deployed with three guest questions and an adjustable 20 questions per account per UTC day. The existing private usage ledger was backed up before its transactional schema migration. Hosted access discovery, secure guest cookies, remaining allowance and foreign-origin rejection passed. Supabase code verification and Resend SMTP authentication were verified independently; real-inbox delivery still needs an explicitly authorized test. No training or paid model generation accompanied this account rollout.

The current small beta retains single-generation concurrency: busy requests consume no question. A fair waiting queue is a follow-up rather than a prerequisite for this bounded rollout. Saved history remains disabled. The custom main domain still needs connection and HTTPS verification; the Railway URL is the active origin. See [account access](ACCOUNT-ACCESS.md).


## Canonical domain preparation — September 11, 2026

The owner authorized connecting meforash.com and changing the visible label to Beta. Cloudflare now has Railway's apex traffic record and ownership TXT record, with DNS-only routing. Railway ownership and its HTTPS certificate are verified. The canonical app and Supabase auth origin are now https://meforash.com. Support email forwarding is configured separately; mail DNS remains intact.

The UI patch replaces the Private beta badge and adds fixed-route GET/HEAD redirects from the old Railway hostname only when the configured origin is https://meforash.com. API POST origin checks remain strict. The legacy invitation form remains an operator fallback; normal public access uses guests and email accounts. A domain change does not transfer browser cookies or temporary conversation storage across origins. Existing users may need to sign in again; this change does not enable persistent history.


Canonical-domain checks verified HTTPS, the Beta label, public/email access discovery, operator login and the 31,152-source inventory, old-host redirect, and foreign-origin rejection. The test connection received the expected guest-issuance rate limit from earlier engineering checks; no limits or spending records were reset. No model generation or email delivery test was performed by this cutover.


A public guest-issuance failure now keeps the public interface visible and offers email sign-in when available, rather than exposing invitation credentials. The composer stays disabled until a valid session exists; temporary conversation/draft recovery and cancellation are tested. The legacy invitation form remains reserved for invitation-mode operation. Fourteen browser scenarios and ten preview tests passed for this follow-up.

## Live account journey — September 11, 2026

The owner confirmed real inbox delivery and live acceptance of the eight-digit sign-in code. A fresh tab retained the account session. Two actual model answers completed, including a follow-up distinguishing Psalm 23 from a promise against suffering; allowance changed from 20 to 19 to 18. After sign-out, a fresh tab returned to guest access. One real guest answer completed and reduced its allowance from three to two. These are product smoke checks, not a scholarly benchmark. No generation was retried. Guest-to-account conversation and draft continuity and re-login allowance verification remain in progress.

The test exposed stale account controls when logout succeeded but new guest issuance was rate-limited. The interface now offers email sign-in and disables the unavailable guest composer in that case; a failed logout separately reports that sign-out could not be confirmed. Sixteen browser regression scenarios and ten preview tests passed. No quota records were reset, and no saved-history migration, model change, or training was included.

## Progressive answers enabled — September 11, 2026

Retained B now uses the explicitly reviewed compatible-chat streaming transport in the hosted beta. Six streaming comparison answers completed, with no material new regression found in five usable native/stream pairs by independent AI engineering review. One unavailable native baseline was preserved and followed by two separately frozen source checks. The hosted operator check observed eight progressive snapshots and a complete answer; two hosted tests created exactly two complete billing rows totaling about one cent estimated. The original native transport remains the default in code and a deploy-time rollback option. See [comparison and hosted checks](STREAMING-COMPARISON-V1.md). No model weights, training or saved-history behavior changed.
