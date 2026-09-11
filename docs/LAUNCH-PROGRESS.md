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
