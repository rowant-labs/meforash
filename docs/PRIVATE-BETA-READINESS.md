# Private beta readiness

September 10, 2026. The retained original-language fine-tuned Inkling B works through the native Tinker backend. An invite-only backend and browser candidate now pass24 combined offline tests, including3 deferred-response browser scenarios; visual browser and hosted verification remain outstanding. The existing preview is local, and no hosted application or invitations have been created.

## Measured backend check

A bounded engineering probe made three native B requests using constructed one-word/arithmetic prompts. All three returned complete final answers. The first process request took **31.86 seconds**; the two warm requests took **8.17 and 8.16 seconds**. A simultaneous second request was rejected immediately as busy, as intended by the current single-flight backend. The estimated sampling cost was **$0.00276835**, against a $0.10 allowance; billing is not reconciled.

The first timing includes local renderer initialization and cannot identify provider cold-start time. These are tiny engineering prompts, not biblical quality tests, a latency distribution, a hosted-network measurement or evidence of multi-user throughput. The existing backend supports one in-flight answer. It should not be advertised as supporting concurrent generation.

Read-only metadata immediately before the check confirmed that both B checkpoints were private and unexpired. Their recorded expiration remains October 6, 2026. No retention setting was changed. The sampler is about 5.042 GB and the training state about 15.125 GB. Preserve both before expiration or establish a tested restoration path; inference availability does not prove external export compatibility. See [serving feasibility](INKLING-B-SERVING-FEASIBILITY.md).

## Concrete hosting target

Use a long-lived Python service for native Tinker inference and serve the existing interface from that service for the smallest beta. Vercel can host the interface later if a separate frontend is useful; that adds cross-origin and authentication work. A Railway deployment can host the Python service, subject to checking its actual runtime, memory use and request/proxy behavior. Supabase is optional for invite authentication and per-user usage records.

The existing `chat_server` is deliberately restricted to loopback hosts. Its local cookie and process budget are not public authentication or durable multi-user accounting. Changing its bind address is insufficient for a hosted launch.

The new [beta backend candidate](BETA-BACKEND-CANDIDATE.md) implements hash-only invitation login and sessions, exact origin checks, durable SQLite per-user and total cost reservations, conservative restart accounting, request/rate limits, single-flight generation and safe errors. Sixteen offline tests passed, including local HTTP authentication tests with a fake model. It uses a separate local port and leaves the existing preview unchanged. No new provider requests or invitations were made by this candidate.

Before a hosted beta, complete:

1. Visually verify the implemented [browser login/session candidate](BETA-PREVIEW-CANDIDATE.md). Its local HTTP and simulated browser checks pass, including stale-response suppression after New chat/logout and preservation of editorial/source-reference details.
2. An actual deployment with pinned runtime/tokenizer/source assets, private B checkpoint receipts, server-side secrets, persistent SQLite storage and one process/replica behind a same-origin HTTPS proxy.
3. Hosted checks of login, passage lookup, complete final-only generation, timeout/busy behavior, unauthorized access and accounting across restarts. Local fake-model tests do not establish these behaviors in a cloud environment.
4. Checkpoint preservation and a bounded recovery test within the chosen provider. External PEFT export and Fireworks import remain unverified.

The first beta should collect voluntary product feedback and error reports; it should not silently turn conversations into training data. Keep the source edition, evidence limits and model adaptation description visible. A fine-tuned model can still mistranslate, omit content or invent historical claims.

## Model decision

The candidate G experiment is separate from deployment. Its frozen baseline evaluation prompt differs from the private chat's product prompt, and its retained rehearsal rows preserve their older prompt framing. A successful comparison would support a candidate model preference in the tested workflow. Before replacing B in the app, verify the selected checkpoint through the actual chat prompt and source-delivery path. No automatic model switch is part of the comparison.
