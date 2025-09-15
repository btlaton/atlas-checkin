-- Signup & Billing MVP: add Stripe fields

-- Members: Stripe customer id
alter table public.members
  add column if not exists stripe_customer_id text;

-- Memberships: provider + Stripe subscription + price
alter table public.memberships
  add column if not exists provider text default 'stripe';

alter table public.memberships
  add column if not exists stripe_subscription_id text;

alter table public.memberships
  add column if not exists price_id text;

-- Optional helpers (indexes)
create index if not exists ix_members_stripe_customer
  on public.members(stripe_customer_id);

create index if not exists ix_memberships_stripe_sub
  on public.memberships(stripe_subscription_id);

create index if not exists ix_memberships_price
  on public.memberships(price_id);

