-- Optional Meforash saved conversation history.
-- Applying this migration does not enable Supabase Auth or change temporary chats.

create schema if not exists meforash_private;

create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users (id) on delete cascade,
  title text,
  created_at timestamptz not null default statement_timestamp(),
  updated_at timestamptz not null default statement_timestamp(),
  constraint conversations_title_length check (
    title is null or char_length(btrim(title)) between 1 and 160
  )
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  position integer not null,
  role text not null,
  content text not null,
  created_at timestamptz not null default statement_timestamp(),
  constraint messages_position_range check (position between 0 and 9999),
  constraint messages_role_allowed check (role in ('user', 'assistant')),
  constraint messages_content_length check (char_length(content) between 1 and 48000),
  constraint messages_conversation_position_unique unique (conversation_id, position)
);

comment on table public.conversations is
  'Private saved conversations. Temporary chats must not be inserted here.';
comment on column public.conversations.owner_id is
  'Supabase Auth user who alone may access this conversation through the Data API.';
comment on table public.messages is
  'Private user and assistant messages in a saved conversation; not training data.';
comment on column public.messages.position is
  'Zero-based stable display order within one conversation.';

create index conversations_owner_updated_idx
  on public.conversations (owner_id, updated_at desc);

-- Keep timestamps server-controlled while allowing a user to rename their own row.
create function meforash_private.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at := statement_timestamp();
  return new;
end;
$$;

revoke all on function meforash_private.set_updated_at() from public, anon, authenticated, service_role;

create trigger conversations_set_updated_at
before update on public.conversations
for each row execute function meforash_private.set_updated_at();

-- A saved message makes its parent conversation recent. The invoker still needs
-- the parent's UPDATE grant and must pass its owner policy.
create function meforash_private.touch_message_conversation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  update public.conversations
     set updated_at = statement_timestamp()
   where id = new.conversation_id;
  return new;
end;
$$;

revoke all on function meforash_private.touch_message_conversation() from public, anon, authenticated, service_role;

create trigger messages_touch_conversation
after insert or update of content on public.messages
for each row execute function meforash_private.touch_message_conversation();

alter table public.conversations enable row level security;
alter table public.messages enable row level security;

-- Existing Supabase projects may grant exposed tables automatically. Start from
-- no Data API access, including service_role because this design does not need it.
revoke all on table public.conversations from public, anon, authenticated, service_role;
revoke all on table public.messages from public, anon, authenticated, service_role;

grant select, delete on table public.conversations to authenticated;
grant insert (id, owner_id, title) on table public.conversations to authenticated;
grant update (title, updated_at) on table public.conversations to authenticated;

grant select, delete on table public.messages to authenticated;
grant insert (id, conversation_id, position, role, content) on table public.messages to authenticated;
grant update (content) on table public.messages to authenticated;

create policy "conversation owners select"
on public.conversations for select
to authenticated
using (
  (select auth.uid()) is not null
  and (select auth.uid()) = owner_id
);

create policy "conversation owners insert"
on public.conversations for insert
to authenticated
with check (
  (select auth.uid()) is not null
  and (select auth.uid()) = owner_id
);

create policy "conversation owners update"
on public.conversations for update
to authenticated
using (
  (select auth.uid()) is not null
  and (select auth.uid()) = owner_id
)
with check (
  (select auth.uid()) is not null
  and (select auth.uid()) = owner_id
);

create policy "conversation owners delete"
on public.conversations for delete
to authenticated
using (
  (select auth.uid()) is not null
  and (select auth.uid()) = owner_id
);

create policy "conversation owners select messages"
on public.messages for select
to authenticated
using (
  (select auth.uid()) is not null
  and exists (
    select 1
      from public.conversations as conversation
     where conversation.id = messages.conversation_id
       and conversation.owner_id = (select auth.uid())
  )
);

create policy "conversation owners insert messages"
on public.messages for insert
to authenticated
with check (
  (select auth.uid()) is not null
  and exists (
    select 1
      from public.conversations as conversation
     where conversation.id = messages.conversation_id
       and conversation.owner_id = (select auth.uid())
  )
);

create policy "conversation owners update messages"
on public.messages for update
to authenticated
using (
  (select auth.uid()) is not null
  and exists (
    select 1
      from public.conversations as conversation
     where conversation.id = messages.conversation_id
       and conversation.owner_id = (select auth.uid())
  )
)
with check (
  (select auth.uid()) is not null
  and exists (
    select 1
      from public.conversations as conversation
     where conversation.id = messages.conversation_id
       and conversation.owner_id = (select auth.uid())
  )
);

create policy "conversation owners delete messages"
on public.messages for delete
to authenticated
using (
  (select auth.uid()) is not null
  and exists (
    select 1
      from public.conversations as conversation
     where conversation.id = messages.conversation_id
       and conversation.owner_id = (select auth.uid())
  )
);
