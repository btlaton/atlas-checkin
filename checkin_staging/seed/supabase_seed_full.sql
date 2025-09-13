-- Full seed: 12 test members across three tiers (idempotent)
-- Run after supabase_schema_only.sql

with seed as (
  select
    gs as i,
    case when gs % 3 = 0 then 'essential'
         when gs % 3 = 1 then 'elevated'
         else 'elite' end               as tier,
    ('Test User '||gs)                  as name_full,
    lower('test'||gs||'@example.com')   as email_raw,
    '+1'||lpad((5550000000 + gs)::text, 10, '0') as phone_raw,
    ('TEST' || lpad(gs::text, 4, '0'))  as external_id
  from generate_series(1,12) as gs
),
upsert_members as (
  insert into public.members (external_id, name, email_lower, phone_e164, status)
  select s.external_id,
         s.name_full,
         s.email_raw,
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
-- select count(*) from public.members;
-- select tier, count(*) from public.memberships where status='active' group by 1 order by 1;
-- select * from public.active_gym_members order by name limit 10;
