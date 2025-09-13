-- Upsert members + memberships from a temp table populated from CSV
-- Steps:
-- 1) Create and load a temp table (via Table Editor → Import to this temp table):
--    create temp table members_tmp (
--      external_id text,
--      name        text,
--      email       text,
--      phone       text,
--      birthday    text,
--      address     text,
--      tier        text
--    ) on commit drop;
--
-- 2) Run this script to upsert into members and memberships.

-- Normalize & upsert members
insert into public.members (external_id, name, email_lower, phone_e164, status)
select
  t.external_id,
  t.name,
  lower(nullif(t.email,'')) as email_lower,
  public.e164_us(t.phone)   as phone_e164,
  'active'
from members_tmp t
on conflict (external_id) do update
  set name        = excluded.name,
      email_lower = excluded.email_lower,
      phone_e164  = excluded.phone_e164,
      status      = 'active',
      updated_at  = now();

-- Ensure qr_token for any missing
update public.members m
   set qr_token = public.gen_token_urlsafe(18)
 where m.qr_token is null;

-- Refresh memberships from this CSV (Mindbody provider)
-- Mark old as inactive for those in this batch (optional safety)
update public.memberships ms
   set status='inactive', end_date = coalesce(ms.end_date, current_date), last_seen_at = now()
 where ms.provider='mindbody'
   and ms.member_id in (select m.id from public.members m join members_tmp t on t.external_id = m.external_id);

-- Upsert active memberships
insert into public.memberships (member_id, provider, tier, status, start_date, last_seen_at)
select m.id, 'mindbody',
       case lower(coalesce(t.tier,''))
         when 'the essential' then 'essential'
         when 'essential'     then 'essential'
         when 'the elevated'  then 'elevated'
         when 'elevated'      then 'elevated'
         when 'the elite'     then 'elite'
         when 'elite'         then 'elite'
         else 'essential' end as tier,
       'active', current_date, now()
from public.members m
join members_tmp t on t.external_id = m.external_id
on conflict (member_id, provider) do update
  set tier         = excluded.tier,
      status       = 'active',
      start_date   = coalesce(public.memberships.start_date, excluded.start_date),
      last_seen_at = now();

-- Verify
-- select count(*) from public.active_gym_members;
