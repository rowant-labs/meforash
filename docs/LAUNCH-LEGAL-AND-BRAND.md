# Launch policies, brand and model release

September 11, 2026. Working recommendations, not adopted legal terms or legal advice. Operator identity, jurisdiction, audience age and public contact address remain owner decisions. No registration, policy acceptance change or weight publication is performed by this document.

## Immediate website wording

The owner requested “Trained on original languages” for the welcome headline. Fine-tuning is training; the detailed description continues to identify selected Hebrew, Aramaic and Greek editions and the existing base-model adaptation. Do not imply training from scratch, access to original manuscripts, complete recovery of an original text, or established translation accuracy.

## Privacy and service terms

Prepare a dedicated privacy policy and service terms before broader promotion. The policy must describe actual collection and processing: guest/session cookies, temporary ten-minute same-tab sign-in recovery, account email and identifiers, durable usage records, and conversation processing by Tinker. Distinguish the app's lack of server chat history from provider retention; verify provider contracts and settings before making retention or no-training promises on their behalf. Supabase manages authentication, Resend sends codes, and Railway hosts the app. Saved history remains disabled.

Define retention and deletion procedures, a working public contact address, audience age, operator identity and applicable legal scope. Privacy law applicability depends on jurisdiction and activities; a small or free service is not automatically exempt. California's CalOPPA can apply to commercial online services collecting personal information from California residents. See [California's privacy-policy guidance](https://oag.ca.gov/sites/all/files/agweb/pdfs/cybersecurity/making_your_privacy_practices_public.pdf) and [FTC business privacy guidance](https://www.ftc.gov/business-guidance/privacy-security/consumer-privacy).

Service terms should address eligibility, acceptable use, adjustable free allowances, model limitations, availability, account termination, applicable warranty/liability limitations and dispute handling. Explain that generated interpretation or personal reflection may be wrong and does not carry divine or professional authority. Use conspicuous terms acceptance for guests as well as account users; privacy disclosure is not blanket consent to all processing. Do not invent an arbitration clause, governing law, legal entity or liability cap before owner decisions and jurisdiction-specific review.

No policy makes the operator immune from liability. Clarify whether Rowant Labs is a legal entity or a trade name, then obtain focused legal advice on entity structure, terms and suitable insurance. The [SBA explains how business structure affects personal liability](https://www.sba.gov/blog/2018/2018-07/choosing-right-business-structure-three-factors-consider/). Entity separation is not a guarantee against every personal or company claim.

## Open code and retained brand

Recommendation: retain Apache-2.0 for original code/documentation, keep official Meforash releases and hosting under the owner's control, and prepare a separate trademark-use policy. Apache-2.0 already excludes broad trademark permission in section 6; it does not prohibit all factual references or attribution. Forks may reuse licensed code, including commercially, while avoiding confusing branding or implied endorsement. Do not retroactively claim published Apache-licensed logo artwork has lost its copyright permissions; review existing grants when separating future brand assets.

Search for conflicting marks and names before investing in registration; the domain alone is not trademark clearance. Determine the actual trademark owner before filing. Do not use the registered symbol without registration. See [USPTO trademark basics](https://www.uspto.gov/trademarks/basics/what-trademark), [trademark search](https://www.uspto.gov/trademarks/search) and [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0).

Omarchy provides a useful product analogy: its public repository distributes code under MIT while presenting a recognizable official project. That does not establish its precise trademark arrangements or supply a legal template for Meforash. [Official repository](https://github.com/omacom/omarchy).

## Model release

Do not publish weights merely because the application code is open source. The initial repository intentionally excludes B's adapter. Describe the current release as open-source application code with a hosted custom model, not a fully reproducible open-weight model release.

A possible later release is a versioned adapter and model card under an organization on Hugging Face, plus corresponding GitHub code, recipes, evaluation results, hashes and source notices. Before that release, verify exact base-model and provider export terms, source obligations, complete adapter tensor export, base compatibility and an independent load test. A LoRA adapter is not the full base model; avoid representing it as independently runnable. Release only the reviewed sampler artifact, not an archive of private runs or credentials. See [publication policy](PUBLICATION.md), [B model card](MODEL-CARD-INKLING-B.md) and [serving feasibility](INKLING-B-SERVING-FEASIBILITY.md).

A model license and a trademark policy solve different problems. Publishing reusable weights can preserve brand rights while allowing others to operate their own models; brand ownership does not prevent all competition.
