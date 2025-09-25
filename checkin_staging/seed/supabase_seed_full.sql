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
)
update public.members m
set membership_tier = s.tier
from upsert_members um
join seed s on s.external_id = um.external_id
where m.id = um.id;

-- Verify
-- select count(*) from public.members;
-- select membership_tier, count(*) from public.members group by 1 order by 1;
-- select id, name, membership_tier from public.members order by name limit 10;
