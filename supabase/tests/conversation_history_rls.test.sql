-- Run after local Supabase is initialized and started: supabase test db
begin;

select plan(31);

insert into auth.users (id, email)
values
  ('11111111-1111-1111-1111-111111111111', 'history-owner@example.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'history-other@example.invalid');

insert into public.conversations (id, owner_id, title)
values
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '11111111-1111-1111-1111-111111111111', 'Owner history'),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '22222222-2222-2222-2222-222222222222', 'Other history');

insert into public.messages (id, conversation_id, position, role, content)
values
  ('aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 0, 'user', 'Owner question'),
  ('bbbbbbbb-0000-0000-0000-000000000001', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 0, 'user', 'Other question');

select ok(
  (select relrowsecurity from pg_class where oid = 'public.conversations'::regclass),
  'conversations has RLS enabled'
);
select ok(
  (select relrowsecurity from pg_class where oid = 'public.messages'::regclass),
  'messages has RLS enabled'
);
select ok(
  not has_table_privilege('anon', 'public.conversations', 'select,insert,update,delete'),
  'anon has no conversation privileges'
);
select ok(
  not has_table_privilege('anon', 'public.messages', 'select,insert,update,delete'),
  'anon has no message privileges'
);
select ok(
  not has_table_privilege('service_role', 'public.conversations', 'select,insert,update,delete'),
  'service_role is not an owner-RLS bypass for conversations'
);
select ok(
  not has_table_privilege('service_role', 'public.messages', 'select,insert,update,delete'),
  'service_role is not an owner-RLS bypass for messages'
);
select ok(
  has_table_privilege('authenticated', 'public.conversations', 'select,delete'),
  'authenticated users may read and delete permitted conversations'
);
select ok(
  has_column_privilege('authenticated', 'public.conversations', 'title', 'update')
  and not has_column_privilege('authenticated', 'public.conversations', 'owner_id', 'update'),
  'conversation title is editable but ownership is not'
);
select ok(
  has_column_privilege('authenticated', 'public.messages', 'content', 'update')
  and not has_column_privilege('authenticated', 'public.messages', 'conversation_id', 'update'),
  'message content is editable but conversation ownership is not'
);

set local role anon;
select throws_ok(
  $$select * from public.conversations$$,
  '42501', null, 'anon cannot read conversations'
);
select throws_ok(
  $$insert into public.messages (conversation_id, position, role, content)
    values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 1, 'user', 'anonymous')$$,
  '42501', null, 'anon cannot insert messages'
);

set local role authenticated;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';

select results_eq(
  $$select id from public.conversations order by id$$,
  array['aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid],
  'owner reads only their conversation'
);
select results_eq(
  $$select content from public.messages order by position$$,
  array['Owner question'::text],
  'owner reads only messages in their conversation'
);
select lives_ok(
  $$insert into public.conversations (owner_id, title)
    values ('11111111-1111-1111-1111-111111111111', 'New saved conversation')$$,
  'owner creates their own conversation'
);
select throws_ok(
  $$insert into public.conversations (owner_id, title)
    values ('22222222-2222-2222-2222-222222222222', 'Stolen conversation')$$,
  '42501', null, 'owner cannot create a conversation for another user'
);
select results_eq(
  $$update public.conversations set title = 'Renamed'
     where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
     returning title$$,
  array['Renamed'::text],
  'owner renames their conversation'
);
select is_empty(
  $$update public.conversations set title = 'Taken'
     where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
     returning id$$,
  'owner cannot update another conversation'
);
select throws_ok(
  $$update public.conversations
       set owner_id = '22222222-2222-2222-2222-222222222222'
     where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'$$,
  '42501', null, 'owner_id cannot be reassigned'
);
select lives_ok(
  $$insert into public.messages (conversation_id, position, role, content)
    values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 1, 'assistant', 'Owner answer')$$,
  'owner adds a message to their conversation'
);
select throws_ok(
  $$insert into public.messages (conversation_id, position, role, content)
    values ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 1, 'user', 'Cross-user insert')$$,
  '42501', null, 'owner cannot add a message to another conversation'
);
select results_eq(
  $$update public.messages set content = 'Edited owner question'
     where id = 'aaaaaaaa-0000-0000-0000-000000000001'
     returning content$$,
  array['Edited owner question'::text],
  'owner updates content in their conversation'
);
select is_empty(
  $$update public.messages set content = 'Changed by stranger'
     where id = 'bbbbbbbb-0000-0000-0000-000000000001'
     returning id$$,
  'owner cannot update another conversation message'
);
select throws_ok(
  $$update public.messages
       set conversation_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
     where id = 'aaaaaaaa-0000-0000-0000-000000000001'$$,
  '42501', null, 'message conversation_id cannot be reassigned'
);
select is_empty(
  $$delete from public.messages
     where id = 'bbbbbbbb-0000-0000-0000-000000000001'
     returning id$$,
  'owner cannot delete another conversation message'
);

reset role;

select throws_ok(
  $$insert into public.messages (conversation_id, position, role, content)
    values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 2, 'system', 'Not allowed')$$,
  '23514', null, 'message roles are bounded'
);
select throws_ok(
  $$insert into public.messages (conversation_id, position, role, content)
    values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 2, 'user', '')$$,
  '23514', null, 'empty message content is rejected'
);
select throws_ok(
  $$insert into public.messages (conversation_id, position, role, content)
    values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 2, 'user', repeat('x', 48001))$$,
  '23514', null, 'oversized message content is rejected'
);
select throws_ok(
  $$insert into public.conversations (owner_id, title)
    values ('11111111-1111-1111-1111-111111111111', repeat('x', 161))$$,
  '23514', null, 'oversized titles are rejected'
);

delete from public.conversations where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
select is_empty(
  $$select id from public.messages
     where conversation_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'$$,
  'deleting a conversation cascades to its messages'
);

delete from auth.users where id = '22222222-2222-2222-2222-222222222222';
select is_empty(
  $$select id from public.conversations
     where owner_id = '22222222-2222-2222-2222-222222222222'$$,
  'deleting an auth user cascades to conversations'
);
select is_empty(
  $$select id from public.messages
     where id = 'bbbbbbbb-0000-0000-0000-000000000001'$$,
  'deleting an auth user cascades through conversations to messages'
);

select * from finish();
rollback;
