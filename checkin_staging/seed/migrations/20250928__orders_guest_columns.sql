-- Ensure guest/member fields exist on orders to track Stripe checkouts
ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS guest_name text;
ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS guest_email text;
ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS member_id bigint REFERENCES public.members(id);
