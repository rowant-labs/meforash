# Optional saved conversation history

September 11, 2026. This is an unapplied database design for optional Meforash accounts and saved history. A dedicated Meforash Supabase project was created under Rowant Labs in the US East (Ohio) region on the Micro compute size, independently verified `ACTIVE_HEALTHY`, and linked with the local Supabase CLI. No migration has been deployed, and guest access, accounts and saved conversations are not operational. The current invitation flow and memory-only temporary chats remain unchanged. Project identifiers, organization identifiers, database credentials and local account paths stay out of this public record.

The approved product policy is three guest questions before sign-in, followed by 20 questions per account per day. The account allowance must be operator-adjustable without a code change. Reset timing, guest-abuse controls and authentication methods remain implementation decisions. These limits are requirements for the future account flow, not behavior of the current invitation backend.

## Product and privacy boundary

Temporary chat remains the default no-storage path: if a reader does not explicitly save a conversation, the application must not insert its text into these tables. A saved conversation contains only its title, ordered user and assistant message text, ownership, and timestamps. The schema has no sharing, publication, analytics, moderation-copy, or training fields. Saved conversations are private and are not training data. Any future voluntary data contribution requires a separate explicit consent flow and separate reviewed storage; a saved-history choice is not consent to training.

Saved history persists until the reader deletes a message or conversation, or deletes the account. The application must expose those deletion controls before enabling saved history. Deleting a conversation cascades to its messages. Deleting its `auth.users` row cascades to that reader's conversations and messages. Supabase notes that account deletion invalidates refresh tokens but an already issued access token can remain valid until it expires, so access-token lifetime and sensitive account-deletion handling need review before launch.

The model provider still receives the conversation context needed to answer a requested question whether or not the reader saves it. Database storage and model processing are separate disclosures.

When a guest chooses to sign in after beginning a conversation, the future interface must preserve that conversation through the sign-in transition using temporary storage scoped to the same browser tab. After sign-in, the interface may restore the conversation in memory, but it must not automatically insert the conversation or its messages into Supabase. Persistent history still requires a separate explicit save action. The temporary handoff data must be cleared after successful restoration, cancellation or sign-out, and must not become cross-tab history.

## Schema and access model

The migration at [`../supabase/migrations/20260910000000_conversation_history.sql`](../supabase/migrations/20260910000000_conversation_history.sql) creates two exposed-schema tables:

- `conversations`: UUID, immutable Supabase Auth owner, optional 160-character title, and server timestamps.
- `messages`: UUID, parent conversation, unique zero-based position, `user` or `assistant` role, content from 1 through 48,000 characters, and a server timestamp.

Every message authorization checks ownership of its parent conversation. This prevents a signed-in user from reading, inserting, editing, or deleting messages in another user's conversation. Column privileges also prevent changing `owner_id`, `conversation_id`, message order, role, IDs, or creation timestamps after insertion. Row-level policies separately cover select, insert, update, and delete. Ownership-filter columns are indexed, and both foreign keys use `on delete cascade`.

The migration revokes all table privileges from `anon`, `authenticated`, and `service_role`, then grants `authenticated` only the table and column operations needed by saved history. There is deliberately no anonymous access and no service-role access. Supabase's service role bypasses RLS; future user-scoped history code should send the signed-in user's access token so `auth.uid()` remains the database authority. If a later server architecture truly requires the service role, that is a separate security design and migration, and it must enforce user identity itself rather than assuming these policies apply.

## Requirements for application integration

Before accounts or saving can be described as available:

1. Review the dedicated project's plan, backups, retention, logs and data-processing terms, then apply and verify the migration before enabling application access.
2. Add Supabase Auth and decide which sign-in methods are supported. Do not silently treat current invitation IDs as Supabase accounts or migrate invite secrets. Allow exactly three guest questions before requiring sign-in, with separately reviewed abuse controls.
3. Enforce an initial 20-question daily allowance for each account through restart-safe server-side accounting. Make the allowance operator-adjustable without a code deployment, and define its reset boundary clearly before release.
4. Preserve an active guest conversation through sign-in using temporary same-tab storage, restore it only to in-memory chat state, and clear the handoff data after use or abandonment.
5. Make temporary chat available without writing the history tables. Add an explicit save action and clear saved-state feedback; never turn an existing or restored in-memory conversation into stored history without the reader's action.
6. Use the authenticated user's JWT for all history queries. Keep publishable and service credentials in their correct client/server boundaries, and never ship a service-role key to the browser.
7. Insert a conversation with `owner_id` equal to the authenticated user, then insert messages using monotonically increasing `position` values. Handle the unique-position conflict explicitly. Message edits are limited to `content`; conversation edits are limited to `title` and the internally maintained recency timestamp.
8. Add list, load, delete-message, delete-conversation, and delete-account flows. Confirm destructive actions in the interface and test that deletion results match the cascade behavior.
9. Add an accurate privacy notice covering temporary sign-in handoff storage, saved retention, deletion, Supabase storage, model-provider processing, and the no-training default. Never suggest that open-source code makes private conversations public.
10. Run the database policy suite against the exact project migration and test the application with two real test users before enabling history.

## Verification status

[`../supabase/tests/conversation_history_rls.test.sql`](../supabase/tests/conversation_history_rls.test.sql) is a 31-assertion pgTAP suite covering RLS enablement, grants, anonymous denial, owner access, cross-user insert/update/delete isolation, immutable ownership columns, content constraints, and both cascade paths. It follows Supabase's documented `supabase test db` structure.

The SQL suite has not run locally. This workspace has the Supabase CLI but no local `psql` or PostgreSQL server; `supabase test db` remained at “Connecting to local database” because no local stack is running, and starting the Docker-backed stack is currently unavailable. Static verification checked migration/test structure, policy-operation coverage, explicit roles, `USING` plus `WITH CHECK` on updates, grants, constraints, indexes, cascade declarations, transaction wrapping, and the declared pgTAP plan. A passing `supabase test db` run remains a required gate after a local project is initialized.

## Sources

This design follows current official Supabase guidance:

- [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security): grants and policies as separate controls, explicit operation policies, `auth.uid()`, `WITH CHECK`, policy tests, and indexes.
- [Securing your API](https://supabase.com/docs/guides/api/securing-your-api): default exposed-schema privileges, least-privilege grants, and the service-role RLS bypass.
- [Managing user data](https://supabase.com/docs/guides/auth/managing-user-data): references to the `auth.users` primary key, account deletion, and JWT lifetime limits.
- [Cascade deletes](https://supabase.com/docs/guides/database/postgres/cascade-deletes): parent-child deletion behavior.
