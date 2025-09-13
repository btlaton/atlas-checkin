-- Supabase schema setup for Atlas Check-In (run first)

-- Enable crypto (for token generation)
create extension if not exists pgcrypto;

-- Maintain updated_at on members
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

-- Normalized memberships table (Mindbody tiers)
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

-- One membership row per (member, provider)
create unique index if not exists ux_memberships_member_provider
  on public.memberships(member_id, provider);

create index if not exists ix_memberships_member_status on public.memberships(member_id, status);

-- Phone normalization helper (US-centric)
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

-- URL-safe token generator for missing qr_token
create or replace function public.gen_token_urlsafe(n_bytes int default 18) returns text
language sql immutable as $$
  select regexp_replace(translate(encode(gen_random_bytes(n_bytes),'base64'), '+/', '-_'), '=+$', '')
$$;

-- View: active gym members (members joined to active Mindbody membership)
create or replace view public.active_gym_members as
select
  m.*,
  ms.tier as membership_tier_normalized
from public.members m
join public.memberships ms
  on ms.member_id = m.id
 where ms.provider = 'mindbody'
   and ms.status = 'active';

-- Helpful indexes for admin/kiosk performance
create index if not exists idx_members_email on public.members(email_lower);
create index if not exists idx_members_phone on public.members(phone_e164);
create index if not exists idx_checkins_member_time on public.check_ins(member_id, timestamp);
create unique index if not exists ux_members_external on public.members(external_id);
create index if not exists idx_members_qr_token_null on public.members(id) where qr_token is null;

-- Done: schema objects created
