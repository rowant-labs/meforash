# Meforash Privacy Policy

**Effective date and version:** September 12, 2026 (`2026-09-12`)

Meforash is operated by **Rowant Labs LLC**, a Nebraska limited liability company ("Rowant Labs," "we," "us," or "our"). This Privacy Policy explains how we handle information when you use Meforash at `meforash.com`, contact us, or use a related Meforash service that links to this policy.

Meforash is intended only for people age 18 or older.

## Information we handle

### Questions, conversations, source passages, and answers

When you ask a question, Meforash sends the current conversation and any supplied source-passage context to Thinking Machines' Tinker service to generate an answer. Your questions may reveal information you consider sensitive, including religious or philosophical beliefs, health concerns, or relationship details. Include only information you choose to have processed for an answer.

Saved conversation history is currently off. Meforash does not automatically save your conversations to its database. The browser normally keeps the visible conversation in the current page's memory. The server temporarily holds active requests and recent results in memory so your browser can retrieve an answer. Completed results become eligible for cleanup after fifteen minutes when later request or polling activity runs; an idle server process may retain them until later activity or shutdown. Starting a new conversation clears the browser view, but does not necessarily cancel an active provider request or immediately erase a temporary server result.

### Temporary sign-in handoff

When you open email sign-in, the page may place the visible conversation, source cards, and unsent draft in that browser tab's session storage for up to ten minutes. This recovery copy does not contain your email address, sign-in code, or provider token. It is cleared after recovery, cancellation, a new conversation, or sign-out. Closing the tab may clear it sooner, depending on your browser.

### Guest, account, authentication, and acceptance information

You may use limited guest access without an email account. Meforash assigns the browser a random guest identifier in a necessary cookie and stores a keyed digest of that identifier to enforce limits and preserve the guest allowance across server restarts.

If you request an email sign-in code, Supabase receives your email address and may create or update an authentication account. Resend delivers the authentication email through Supabase's configured mail service. Meforash's local ledger stores a verified Supabase user identifier, hashed session tokens, keyed email digests used for rate limiting, authentication-challenge records, and expiration times. The local ledger does not store your plain email address. Invitation access, when available, uses an invitation identifier, a salted secret hash, and a hashed session token.

When you accept the Terms of Service, we record the applicable Terms version, the acceptance date and time, the guest or account identifier associated with the acceptance, and your representation that you are at least 18 years old. The corresponding Privacy Policy version is identified by its effective date.

### Cookies and similar identifiers

Meforash uses necessary, host-only cookies for guest, account, authentication-challenge, and invitation sessions. On the hosted service, these cookies are `Secure`, `HttpOnly`, and `SameSite=Strict`. Guest cookies may last up to 400 days, account sessions up to 30 days, and authentication challenges up to ten minutes. Expired local records are removed during later application cleanup rather than by a guaranteed real-time deletion job.

Meforash does not use advertising cookies. We use Cloudflare Web Analytics for aggregate page visits and website performance. It does not use analytics cookies or session replay. Cloudflare receives technical connection information and collects page, referral, browser/device, approximate country, and performance information. We do not send conversation text, drafts, email addresses, or account identifiers to this analytics service. Browser privacy tools may block it.

### Usage, security, and connection information

Our local ledger stores request identifiers, an account, guest, or invitation identifier, timestamps, quota day and request status, and reserved or estimated inference cost. It also stores keyed digests derived from email addresses and network addresses, with timestamps, to enforce limits and prevent abuse. We use aggregate reports from these existing records to understand active account and guest identifiers, question counts, outcomes, and estimated costs; the reports contain no individual identifiers or conversation text. Raw network addresses are not stored in that ledger. Hosting and network providers may process IP addresses, connection information, and operational logs under their own settings and terms.

### Support communications

If you email us, we receive your email address, message, attachments, and other information you choose to provide. Cloudflare routes the support-address message and Google provides the receiving Gmail mailbox. Do not send sensitive personal information that is unnecessary for your request.

## How we use information

We use information to:

- provide requested answers and source displays;
- authenticate users and maintain guest, account, and invitation sessions;
- preserve the short sign-in handoff described above;
- enforce question, cost, and security limits;
- diagnose failures and maintain the service;
- respond to support, access, correction, and deletion requests;
- protect Meforash, its users, and others; and
- comply with applicable law and resolve disputes.

Rowant Labs does **not** use conversations submitted through the application to train its models. [Thinking Machines' current service terms](https://thinkingmachines.ai/legal/terms/) also state that it does not use customer content to develop or improve its technology, including to train or fine-tune models. That provider commitment is governed by the applicable provider agreement. We do not extend the same promise to every provider where its terms do not make it.

## Service providers and disclosures

We use these providers to operate Meforash:

- **[Thinking Machines / Tinker](https://thinkingmachines.ai/legal/privacy/)** processes conversation text, supplied source passages, and generated results when you request an answer. Its service terms govern its processing and distinguish customer content from other usage data.
- **[Railway](https://railway.com/legal/privacy)** hosts the application and may process network, device, and operational information.
- **[Supabase](https://supabase.com/privacy)** provides email authentication and stores authentication-account information. Supabase generally acts as a processor for customer data used in its services.
- **[Resend](https://resend.com/legal/privacy-policy)** delivers sign-in emails and processes destination addresses, message content, and delivery metadata for that purpose.
- **[Cloudflare](https://www.cloudflare.com/policies/privacy/)** provides domain and network services, aggregate website analytics, and routes messages sent to the support address.
- **[Google](https://policies.google.com/privacy)** provides the Gmail mailbox that receives support messages.

These providers may use subprocessors and process information in multiple countries. Their retention, security, and independent handling of service and account data are governed by their contracts, settings, and applicable policies.

We may also disclose information when reasonably necessary to comply with law, respond to valid legal process, investigate abuse, protect rights or safety, or complete a financing, merger, acquisition, reorganization, or sale of assets subject to applicable safeguards and notice.

Meforash does not currently sell personal information, share it for cross-context behavioral advertising, or use it for targeted advertising.

Links to GitHub and other external sites are governed by those sites' privacy practices when you follow them.

## Retention and deletion

The technical periods described above apply to browser handoffs, guest cookies, sessions, and authentication challenges. Rate-limit events are designed around a 24-hour enforcement window and are removed during later cleanup. Server results are temporary, but activity-triggered cleanup means deletion may not occur at an exact minute.

Supabase authentication accounts, durable account identifiers, acceptance records, and security, usage, and accounting records are kept as needed to operate the service, enforce limits, document acceptance, prevent abuse, address disputes, and meet legal obligations. Provider logs, backups, messages, and account records follow the applicable provider settings and retention practices. We do not promise a fixed deletion schedule where one is not currently implemented.

Saved conversation history is currently off, so there is no account conversation archive in Meforash to view or delete.

Meforash does not currently provide automated account deletion. You may request access, correction, or deletion by emailing **support@meforash.com**. We may need to verify your identity. We will identify responsive records under our control, coordinate with relevant providers where applicable, and explain what we delete or must retain for security, accounting, disputes, or legal obligations. Deleting a Supabase authentication account alone may not remove Meforash sessions or usage records, so deletion steps are coordinated manually.

## Your choices and privacy rights

You can use limited guest access without creating an email account. You can start a new conversation, close the tab, sign out, or clear Meforash site data in your browser. These actions do not necessarily erase an active provider request, a temporary server result, provider records, or durable security and usage records.

Depending on where you live, you may have rights to request access, correction, deletion, restriction, objection, portability, or withdrawal of consent, and to appeal or complain to a privacy authority. These rights may be subject to exceptions under applicable law. Contact **support@meforash.com** to make a request. We will not discriminate against you for exercising a right protected by law.

## Security and international processing

Meforash uses access controls, hashed or keyed identifiers, restricted cookies, request limits, and a limited server ledger. No system is completely secure. Please protect your browser, email account, sign-in codes, and active sessions.

Rowant Labs and its providers may process information in the United States and other countries. Those countries may have data-protection rules different from those where you live. Where required, applicable provider agreements and legal transfer mechanisms govern those transfers.

## Adults only

Meforash is intended only for people age 18 or older. We do not knowingly offer the service to or collect personal information through the service from anyone under 18. If you believe a minor has provided information, contact **support@meforash.com** so we can review the situation and take appropriate deletion steps.

## Changes to this policy

We may update this policy prospectively as the service changes. We will post the new version and effective date and provide clear advance notice of material changes when reasonably practical or required by law. We will obtain any additional consent required by law.

A revised policy does not create blanket or retroactive consent to use previously collected conversations for AI training or another materially different purpose. Any future proposal by Rowant Labs to use conversations or identifiable user content for training will be clearly disclosed in advance and will require a separate, prospective opt-in where appropriate.

## Contact

Rowant Labs LLC  
Nebraska, United States  
**support@meforash.com**
