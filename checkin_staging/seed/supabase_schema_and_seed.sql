-- Supabase schema setup for Atlas Check-In (memberships, helpers, view)
-- Plus a small test seed to validate the app end-to-end
--
-- Run this in Supabase SQL Editor (staging first, then prod).

-- 0) Enable crypto extension (for token generation)
create extension if not exists pgcrypto;

-- 1) Ensure updated_at auto-maintains on members
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists trg_members_updated_at on public.members;
create trigger trg_members_updated_at
before update on public.members
for each row execute procedure public.set_updated_at();

-- 2) Normalized memberships table (Mindbody tiers)
create table if not exists public.memberships (
  id           serial primary key,
  member_id    integer not null references public.members(id) on delete cascade,
  provider     text    not null default 'mindbody',
  tier         text    not null check (tier in ('essential','elevated','elite')),
  status       text    not null default 'active' check (status in ('active','inactive')),
  start_date   date,
  end_date     date,
  last_seen_at timestamptz default now(),
  created_at   timestamptz default now()
);

-- One membership row per (member, provider). Status field indicates active vs inactive.
create unique index if not exists ux_memberships_member_provider
  on public.memberships(member_id, provider);

-- Helpful lookup
create index if not exists ix_memberships_member_status on public.memberships(member_id, status);

-- 3) Phone normalization helper (US-centric)
create or replace function public.e164_us(phone text) returns text
language plpgsql immutable as $$
declare d text;
begin
  d := regexp_replace(coalesce(phone,''), '[^0-9]', '', 'g');
  if length(d)=10 then return '+1'||d;
  elsif length(d)=11 and left(d,1)='1' then return '+'||d;
  elsif phone like '+%' then return phone;
  else return nullif('+'||d, '+'); end if;
end $$;

-- 4) URL-safe token generator for missing qr_token
create or replace function public.gen_token_urlsafe(n_bytes int default 18) returns text
language sql immutable as $$
  select regexp_replace(translate(encode(gen_random_bytes(n_bytes),'base64'), '+/', '-_'), '=+$', '')
$$;

-- 5) View: gym members (members joined to active Mindbody membership)
create or replace view public.active_gym_members as
select
  m.*,
  ms.tier as membership_tier_normalized
from public.members m
join public.memberships ms
  on ms.member_id = m.id
 where ms.provider = 'mindbody'
   and ms.status = 'active';

-- 6) Helpful indexes for admin/kiosk
create index if not exists idx_members_email on public.members(email_lower);
create index if not exists idx_members_phone on public.members(phone_e164);
create index if not exists idx_checkins_member_time on public.check_ins(member_id, timestamp);
-- Unique key for upserts by external_id
create unique index if not exists ux_members_external on public.members(external_id);

-- 7) Seed test members across three tiers (idempotent)
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

-- Verification samples (optional)
-- select count(*) from public.members;
-- select tier, count(*) from public.memberships where status='active' group by 1 order by 1;
-- select * from public.active_gym_members order by name limit 10;
