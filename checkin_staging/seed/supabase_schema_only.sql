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

alter table public.members
  add column if not exists membership_tier text;

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
language sql volatile as $$
  select regexp_replace(translate(encode(gen_random_bytes(n_bytes),'base64'), '+/', '-_'), '=+$', '')
$$;

-- Helpful indexes for admin/kiosk performance
create index if not exists idx_members_email on public.members(email_lower);
create index if not exists idx_members_phone on public.members(phone_e164);
create index if not exists idx_checkins_member_time on public.check_ins(member_id, timestamp);
create unique index if not exists ux_members_external on public.members(external_id);
create index if not exists idx_members_qr_token_null on public.members(id) where qr_token is null;

-- Done: schema objects created
