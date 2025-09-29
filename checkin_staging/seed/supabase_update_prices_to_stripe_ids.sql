-- Map Atlas product prices to Stripe Price IDs (replace placeholders before running)
-- Example usage:
--   replace {{PRICE_ELECTROLYTE_RETAIL}} with actual Stripe price id (e.g. price_123)
--   run in Supabase SQL editor once per environment.

-- Retail beverages & goods
update public.product_prices set stripe_price_id = 'price_1SC5NODJJF9sHVx3Qhrs70xx'
where product_id = (select id from public.products where slug = 'electrolyte-drink')
  and price_type = 'retail';

update public.product_prices set stripe_price_id = 'price_1SC5NdDJJF9sHVx37LqgFZRS'
where product_id = (select id from public.products where slug = 'energy-drink')
  and price_type = 'retail';

update public.product_prices set stripe_price_id = 'price_1SC5NmDJJF9sHVx3Ea8MWX2n'
where product_id = (select id from public.products where slug = 'water')
  and price_type = 'retail';

update public.product_prices set stripe_price_id = 'price_1SC5NzDJJF9sHVx3MmttJfUd'
where product_id = (select id from public.products where slug = 'atlas-essential-baby-tee-black')
  and price_type = 'retail';
update public.product_prices set stripe_price_id = 'price_1SC6ScDJJF9sHVx3nvNOcHol'
where product_id = (select id from public.products where slug = 'atlas-essential-shirt-black')
  and price_type = 'retail';
update public.product_prices set stripe_price_id = 'price_1SC5OCDJJF9sHVx358CZi1UZ'
where product_id = (select id from public.products where slug = 'towel-service')
  and price_type = 'retail';

-- Personal training packages (one-time)
update public.product_prices set stripe_price_id = 'price_1SC5Q6DJJF9sHVx3cEJf05Tu'
where product_id = (select id from public.products where slug = 'personal-training-1-session')
  and price_type = 'package';

update public.product_prices set stripe_price_id = 'price_1SC5QUDJJF9sHVx3tosiXcS1'
where product_id = (select id from public.products where slug = 'personal-training-4-sessions-month')
  and price_type = 'recurring';

update public.product_prices set stripe_price_id = 'price_1SC5R1DJJF9sHVx3xyeqzWu6'
where product_id = (select id from public.products where slug = 'personal-training-8-sessions-month')
  and price_type = 'recurring';

update public.product_prices set stripe_price_id = 'price_1SC5RNDJJF9sHVx3lLVqJZbr'
where product_id = (select id from public.products where slug = 'personal-training-12-sessions-month')
  and price_type = 'recurring';

-- Consultations / recovery (if billable)
update public.product_prices set stripe_price_id = 'price_1SC5SyDJJF9sHVx3hCNqJmiX'
where product_id = (select id from public.products where slug = 'inbody-consultation')
  and price_type = 'complimentary';

update public.product_prices set stripe_price_id = 'price_1SC5SkDJJF9sHVx3E6ojYEWP'
where product_id = (select id from public.products where slug = 'recovery-room-elevated-elite')
  and price_type = 'complimentary';

-- Open gym passes
update public.product_prices set stripe_price_id = 'price_1SC5P3DJJF9sHVx3gufSPbiJ'
where product_id = (select id from public.products where slug = 'open-gym-day-pass')
  and price_type = 'package';

update public.product_prices set stripe_price_id = 'price_1SC5PGDJJF9sHVx3IyY5gKe0'
where product_id = (select id from public.products where slug = 'open-gym-week-pass')
  and price_type = 'package';

-- Membership tiers (recurring)
update public.product_prices set stripe_price_id = 'price_1S7GBaDJJF9sHVx39kPhq8W6'
where product_id = (select id from public.products where slug = 'membership-essential')
  and price_type = 'recurring';

update public.product_prices set stripe_price_id = 'price_1S7GC4DJJF9sHVx3ptgXqid2'
where product_id = (select id from public.products where slug = 'membership-elevated')
  and price_type = 'recurring';

update public.product_prices set stripe_price_id = 'price_1S7GCKDJJF9sHVx3AlTawAJJ'
where product_id = (select id from public.products where slug = 'membership-elite')
  and price_type = 'recurring';

-- Trainer program subscription
update public.product_prices set stripe_price_id = 'price_1SC5SFDJJF9sHVx3fnvE1nRH'
where product_id = (select id from public.products where slug = 'trainer-agreement')
  and price_type = 'recurring';

-- Remove these NULL-setters or replace with actual price ids if you are NOT charging for consultation/recovery.
-- If those should stay complimentary, you can instead leave them unchanged or comment the updates out.
