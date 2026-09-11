# Meforash launch progress

September 10, 2026. The owner authorized moving from the research preview toward a hosted product, retaining Inkling B. No further training is required for this milestone.

## Experience

The beta interface is branded Meforash and presents an open question field. It has no suggested-question chips or mandatory modes. Training, source, and privacy details are expandable. Model answers render a bounded subset of Markdown through safe DOM text nodes, with source editions and original-language passages in a separate panel.

Invitation authentication remains in place for the first hosted verification. Guest access, optional Supabase accounts, saved conversations and a fair request queue are subsequent integration tasks, not existing features. No invitation has been sent to another person. The initial hosted owner allowance is $5 total estimated inference spend; this is not a recurring daily reset or a provider invoice cap.

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

A subsequent deployment preserved the exact $0.00464031 accounting balance; no extra model request was made for the restart check. The public GitHub repository was created, but the CLI credential became invalid before the first push. The reviewed initial source commit is being prepared locally. Supabase project selection and custom-domain DNS remain pending.

Both retained B checkpoint expiries were removed and verified after a storage-cost notice. Estimated ongoing storage for the sampler and training state together is $2.016734/month at $0.10/GB-month. Model weights remain private; no export or training took place.

Integration review also fixed an empty-Markdown-marker progress bug in the answer renderer. The hostile-formatting regression now includes empty heading and list markers, and passes without allowing model HTML or links to execute.
