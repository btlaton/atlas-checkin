-- Minimal seed: insert 3 test members across tiers (idempotent)
-- Run after supabase_schema_only.sql

with seed as (
  select * from (
    values
      ('TEST0001','Test One','test1@example.com','+1 555 000 0101','essential'),
      ('TEST0002','Test Two','test2@example.com','+1 555 000 0102','elevated'),
      ('TEST0003','Test Three','test3@example.com','+1 555 000 0103','elite')
  ) as t(external_id,name_full,email_raw,phone_raw,tier)
),
upsert_members as (
  insert into public.members (external_id, name, email_lower, phone_e164, status)
  select s.external_id,
         s.name_full,
         lower(s.email_raw),
         public.e164_us(s.phone_raw),
         'active'
  from seed s
  on conflict (external_id) do update
    set name        = excluded.name,
        email_lower = excluded.email_lower,
        phone_e164  = excluded.phone_e164,
        status      = 'active',
        updated_at  = now()
  returning id, external_id
),
ensure_tokens as (
  update public.members m
     set qr_token = public.gen_token_urlsafe(18)
   where m.qr_token is null
  returning m.id
)
insert into public.memberships (member_id, provider, tier, status, start_date, last_seen_at)
select m.id, 'mindbody', s.tier, 'active', current_date, now()
from upsert_members m
join seed s on s.external_id = m.external_id
on conflict (member_id, provider) do update
  set tier         = excluded.tier,
      status       = 'active',
      start_date   = coalesce(public.memberships.start_date, excluded.start_date),
      last_seen_at = now();

-- Verify
-- select * from public.active_gym_members order by name limit 10;
