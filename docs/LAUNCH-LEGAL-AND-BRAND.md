# Launch legal, policy and brand decisions

September 11, 2026. This is a launch-review checklist, not legal advice or an adopted policy. The proposed [privacy policy](PRIVACY-POLICY-DRAFT.md) and [terms of service](TERMS-OF-SERVICE-DRAFT.md) are drafts and are not effective merely because they exist in the repository.

## Resolved drafting inputs

- The operator is **Rowant Labs LLC**, a Nebraska limited liability company.
- The public support contact is **support@meforash.com**.
- The initial audience is **adults age 18 and older**. This reduces child and teen privacy and contracting risk; it does not replace enforcement or legal review.
- Application conversations are not saved as account history and are not used by Meforash for training. Any materially different future data use must be prospective, clearly disclosed, and separately consented to where appropriate.
- The service may change models, features, and free limits. Any future charge requires advance pricing and recurring-billing terms plus affirmative opt-in.

## Decisions and implementation still required

1. **Adoption and acceptance:** obtain focused legal review, add effective dates and a reviewed business mailing address, publish conspicuous links, and implement versioned acceptance for both guests and accounts. Preserve the version and acceptance evidence. Do not describe the drafts as live before this exists.
2. **Adults-only operation:** choose and implement a proportionate age representation or gate, avoid marketing directed to children, and create a support procedure for reports involving minors. Terms alone do not determine whether a service is child-directed. The FTC explains that COPPA protects children under 13, covers persistent identifiers, and can apply to a general-audience service with actual knowledge of collection from a child. See the [FTC COPPA FAQ](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions).
3. **Deletion and retention:** create a manual request runbook that verifies the requester and coordinates Supabase account deletion, local-session revocation, and applicable provider requests. Approve retention periods for durable user identifiers and usage/accounting rows. Do not promise instant or complete automated deletion while no deletion interface exists.
4. **Provider review:** verify current Tinker conversation retention/training terms and settings, plus Railway, Supabase, Resend, Cloudflare, and Google logging, retention, security, subprocessors, incident notice, and deletion support. Keep public language bounded to verified facts rather than promising zero provider retention or a processing location.
5. **Material changes:** choose a notice channel and lead time for material policy, model, feature, and limit changes. Preserve prior policy versions. Do not convert earlier privacy commitments into retroactive blanket consent; the [FTC warns against quietly expanding data uses through revised terms](https://www.ftc.gov/policy/advocacy-research/tech-at-ftc/2024/02/ai-other-companies-quietly-changing-your-terms-service-could-be-unfair-or-deceptive).
6. **Legal risk allocation:** counsel should determine governing law, venue, dispute handling, warranty language, permissible liability limits, and insurance needs. The drafts intentionally invent no arbitration clause, jurisdiction, indemnity, or numeric liability cap.
7. **Brand and open source:** complete a conflicting-mark search, confirm Rowant Labs LLC owns or is licensed to use final brand assets, and adopt a trademark-use policy. Apache-2.0 governs released project code and documentation but does not grant broad trademark rights; review any brand assets already released under it.
8. **Model release:** keep hosted-service launch separate from any adapter publication. Before releasing weights, verify base-model and provider terms, source obligations, export completeness, hashes, model card, and independent load compatibility. Open application code does not make private conversations or the retained adapter public.

The policy, age, deletion, and acceptance controls should be complete before broader promotion. Provider review, security response planning, and legally reviewed service terms remain necessary even for a free beta.
