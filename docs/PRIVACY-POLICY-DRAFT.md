# Meforash privacy policy — draft

**Draft prepared September 11, 2026. Not effective or adopted. Owner and legal review are required before publication.**

This draft describes the current Meforash beta at `meforash.com`. Meforash is operated by **Rowant Labs LLC**, a Nebraska limited liability company ("Rowant Labs," "we," "us," or "our"). Questions and privacy requests may be sent to **support@meforash.com**.

## Information Meforash handles

**Questions and answers.** When you ask a question, Meforash sends the current conversation and any displayed source-passage context to Thinking Machines' Tinker service to generate an answer. The Meforash application does not save conversation history to its database. The browser normally keeps the conversation only in the current page's memory. The server temporarily holds active requests and recent results in memory so the page can retrieve an answer. Completed results are limited in number and become eligible for activity-triggered cleanup after fifteen minutes; an idle process may retain them in memory until later activity or shutdown.

**Temporary sign-in recovery.** When you open email sign-in, the page may place the visible conversation, source cards, and unsent draft in that browser tab's session storage for up to ten minutes. This recovery copy does not contain your email address, sign-in code, or provider token. It is cleared after recovery, cancellation, a new conversation, or sign-out. Closing the tab may clear it sooner, depending on the browser.

**Account and authentication data.** If you request an email sign-in code, Supabase receives the email address and may create or update an authentication account; Resend delivers the authentication email through Supabase's configured mail service. Meforash's local ledger stores a verified Supabase user identifier, hashed session tokens, keyed email digests used for rate limiting, authentication-challenge records, and expiry times. It does not store the plain email address in that ledger. Invitation access, where available to operators or selected testers, uses an invitation identifier, a salted secret hash, and a hashed session token.

**Cookies and similar identifiers.** Meforash uses necessary, host-only cookies for guest, account, authentication-challenge, or invitation sessions. Hosted cookies are `Secure`, `HttpOnly`, and `SameSite=Strict`. Guest cookies may last up to 400 days, account sessions up to 30 days, and authentication challenges up to ten minutes. Expired local records are removed during later application cleanup rather than by a guaranteed real-time deletion job. Meforash does not currently use advertising cookies or application analytics.

**Usage, security, and connection data.** The local ledger retains request identifiers, an account/guest/invitation identifier, timestamps, quota day and status, and reserved or estimated actual inference cost. It also stores keyed digests derived from email addresses and network addresses, plus timestamps, to limit abuse. Raw network addresses are not stored in the local ledger. Railway and other infrastructure providers may process connection information and logs under their own settings and terms.

**Support communications.** If you email us, we receive the address, message, and other information you choose to provide. Do not send sensitive personal information that is unnecessary for the request.

## Why we use information

We use this information to provide requested answers and source displays; authenticate users; preserve a short sign-in handoff; enforce free-use, cost, and security limits; diagnose failures; respond to support and privacy requests; protect Meforash and its users; and meet applicable legal obligations.

Meforash does **not** use conversations submitted through the application to train its models. We will not reinterpret this commitment retroactively through a quiet policy change. A future proposal to use conversations or identifiable user content for training would require clear advance disclosure and a separate, prospective opt-in where appropriate. This application promise does not make an unverified promise about a service provider's independent retention or model-improvement practices; those must be assessed under the applicable provider agreement and settings.

## Service providers and disclosures

We use the following providers for the functions described here. Their own processing, logging, retention, and subprocessors still require contract and settings review before this draft is adopted:

- **Railway** hosts the application and may process network and operational data.
- **Supabase** provides email authentication and stores authentication-account information.
- **Resend** delivers sign-in emails through Supabase.
- **Thinking Machines / Tinker** processes conversation text and supplied source context when you request an answer.
- **Cloudflare** provides domain-name service and routes messages sent to the support address.
- **Google** provides the mailbox that receives support messages. The public contact does not expose a personal email address.

We may also disclose information when reasonably necessary to comply with law, protect rights or safety, investigate abuse, or complete a business transaction subject to appropriate notice and safeguards. The current service does not sell personal information or use it for targeted advertising. Links to GitHub or other sites are governed by those sites' own privacy practices when you follow them.

## Retention and deletion

The periods above describe current technical expirations for browser handoffs and authentication records. Rate-limit events are designed for a 24-hour window and are removed during later cleanup. Durable account identifiers and usage/accounting records do not yet have an approved general retention schedule.

Meforash does not currently provide automated account deletion. You may ask for access, correction, or deletion by emailing **support@meforash.com**. We will verify the request, identify records under our control, coordinate with relevant providers where applicable, and explain what was deleted or must be retained for security, accounting, dispute, or legal reasons. Deleting a Supabase authentication account alone may not remove local sessions or usage records, so those steps must be coordinated manually.

## Your choices

You may use limited guest access without creating an email account, subject to current limits. You can clear the visible conversation with **New conversation**, close the tab, sign out, or clear site data in your browser. These actions do not necessarily erase an active provider request, a temporary server result, provider records, or durable security and usage records. Because saved history is not enabled, there is no account conversation archive to view or delete.

Depending on where you live, applicable law may provide additional rights. Contact us to make a request. We will not discriminate against a user for exercising a right protected by law.

## Adults only

**Draft owner decision: Meforash is intended only for people age 18 or older.** We do not knowingly offer accounts to or collect personal information through the service from anyone under 18. If you believe a minor has provided information, contact **support@meforash.com** so the situation can be reviewed and appropriate deletion steps taken. Age-screening and minor-report handling must be implemented and legally reviewed before this draft is adopted.

## Security and international processing

Meforash uses access controls, hashed or keyed identifiers, restricted cookies, request limits, and a limited server ledger. No system is completely secure. Service providers may process information in locations governed by their own infrastructure, contracts, and applicable law; this draft does not promise a particular processing location.

## Changes to this policy

If this policy becomes effective, its effective date and prior versions should be retained. Material changes should receive clear advance notice. Changes will apply prospectively unless the user gives any additional consent required by law. Posting a broader policy will not create blanket or retroactive consent to use previously collected conversations for AI training or another materially different purpose. The FTC has warned that quietly expanding data uses through retroactive policy changes may be unfair or deceptive. See the [FTC's February 2024 guidance](https://www.ftc.gov/policy/advocacy-research/tech-at-ftc/2024/02/ai-other-companies-quietly-changing-your-terms-service-could-be-unfair-or-deceptive).

## Contact

Rowant Labs LLC  
Nebraska, United States  
**support@meforash.com**

**Before adoption:** add the company's reviewed business mailing address and an effective date.
