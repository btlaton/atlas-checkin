-- Upsert members from a temp table populated from CSV
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
-- 2) Run this script to upsert into members (and set membership_tier).

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

-- Normalize tier names and store directly on members
update public.members m
set membership_tier = case lower(coalesce(t.tier,''))
         when 'the essential' then 'essential'
         when 'essential'     then 'essential'
         when 'the elevated'  then 'elevated'
         when 'elevated'      then 'elevated'
         when 'the elite'     then 'elite'
         when 'elite'         then 'elite'
         else null end
from members_tmp t
where t.external_id = m.external_id;

-- Ensure qr_token for any missing
update public.members m
   set qr_token = public.gen_token_urlsafe(18)
 where m.qr_token is null;

-- Verify
-- select count(*) from public.members;
