-- Seed Atlas catalog (retail, training, memberships, passes)
-- Run after supabase_schema_commerce.sql

with category_seed as (
  select * from (
    values
      ('beverages','Beverages','Drinks and hydration',10),
      ('apparel','Apparel','Atlas branded apparel',20),
      ('services','Services','Front-desk services and add-ons',30),
      ('personal-training','Personal Training','1:1 training packages',40),
      ('open-gym','Open Gym Passes','Day and week access products',50),
      ('memberships','Membership Plans','Recurring Atlas tiers',60),
      ('consultations','Consultations','Assessments and testing',70),
      ('trainer-program','Trainer Program','Independent trainer agreements',80)
  ) as t(slug, name, description, sort_order)
),
upsert_categories as (
  insert into public.product_categories (slug, name, description, sort_order)
  select slug, name, description, sort_order from category_seed
  on conflict (slug) do update
    set name        = excluded.name,
        description = excluded.description,
        sort_order  = excluded.sort_order,
        updated_at  = now()
  returning id, slug
),
product_seed as (
  select * from (
    values
      ('electrolyte-drink','Electrolyte Drink','atlas-electrolyte-drink','2190196806','retail','beverages',null,null,'Hydrating electrolyte beverage.',true,false,false,'retail',0),
      ('energy-drink','Energy Drinks','atlas-energy-drink','4536157453','retail','beverages',null,null,'Assorted energy drinks (single can).',true,false,false,'retail',0),
      ('atlas-essential-baby-tee-black','The Atlas Essential Baby Tee (Black)','atlas-tee-baby-black','5498718467','retail','apparel',null,null,'Fitted crop tee in black.',true,false,false,'retail',0),
      ('atlas-essential-shirt-black','The Atlas Essential Shirt (Black)','atlas-tee-classic-black','6772674978','retail','apparel',null,null,'Classic Atlas tee in black.',true,false,false,'retail',0),
      ('towel-service','Towel Service','atlas-towel-service','4244464562','service','services','Arrivals','Towel Service','Single visit towel service.',true,false,false,'retail',0),
      ('water','Water','atlas-water','9307286744','retail','beverages',null,null,'Bottled water.',true,false,false,'retail',0),
      ('personal-training-1-session','1 Session Personal Training','pt-01-session',null,'service','personal-training','Appointments','Personal Training','Single 60-minute personal training session.',true,false,false,'package',0),
      ('personal-training-4-sessions-month','4 Sessions / Month Training','pt-04-month',null,'service','personal-training','Appointments','Personal Training','Monthly plan with four personal training sessions.',true,false,false,'recurring',0),
      ('personal-training-8-sessions-month','8 Sessions / Month Training','pt-08-month',null,'service','personal-training','Appointments','Personal Training','Monthly plan with eight personal training sessions.',true,false,false,'recurring',0),
      ('personal-training-12-sessions-month','12 Sessions / Month Training','pt-12-month',null,'service','personal-training','Appointments','Personal Training','Monthly plan with twelve personal training sessions.',true,false,false,'recurring',0),
      ('inbody-consultation','InBody Consultation','inbody-consult',null,'service','consultations','Appointments','InBody Scan','Body composition assessment using InBody.',true,false,false,'complimentary',0),
      ('open-gym-day-pass','Open Gym Day Pass','open-gym-day',null,'guest_pass','open-gym','Arrivals','Open Gym','One-day access to Atlas open gym.',true,false,false,'package',0),
      ('open-gym-week-pass','Open Gym Week Pass','open-gym-week',null,'guest_pass','open-gym','Arrivals','Open Gym','Seven-day access to Atlas open gym.',true,false,false,'package',0),
      ('recovery-room-elevated-elite','Recovery Room – Elevated/Elite','recovery-room-elevated',null,'service','services','Appointments','Recovery Room','Recovery room sessions included with Elevated/Elite memberships.',true,false,false,'complimentary',0),
      ('membership-essential','Membership – Essential','membership-essential',null,'membership_plan','memberships','Arrivals','Open Gym','Essential membership tier.',true,false,false,'recurring',0),
      ('membership-elevated','Membership – Elevated','membership-elevated',null,'membership_plan','memberships','Arrivals','Open Gym','Elevated membership tier.',true,false,false,'recurring',0),
      ('membership-elite','Membership – Elite','membership-elite',null,'membership_plan','memberships','Arrivals','Open Gym','Elite membership tier.',true,false,false,'recurring',0),
      ('trainer-agreement','Trainer Agreement','trainer-agreement',null,'service','trainer-program','Arrivals','Trainer Agreement','Monthly access agreement for independent trainers.',true,false,false,'recurring',0)
  ) as t(slug, name, sku, barcode, product_kind, category_slug, service_type, service_category, description, is_active, sell_online, inventory_tracking, default_price_type, cost_cents)
),
resolved_products as (
  select
    ps.slug,
    ps.name,
    ps.sku,
    ps.barcode,
    ps.product_kind,
    ps.category_slug,
    ps.service_type,
    ps.service_category,
    ps.description,
    ps.is_active,
    ps.sell_online,
    ps.inventory_tracking,
    ps.default_price_type,
    ps.cost_cents,
    uc.id as category_id
  from product_seed ps
  left join upsert_categories uc on uc.slug = ps.category_slug
),
upsert_products as (
  insert into public.products (
    category_id,
    name,
    slug,
    barcode,
    product_sku,
    product_kind,
    service_type,
    service_category,
    description,
    is_active,
    sell_online,
    inventory_tracking,
    default_price_type,
    our_cost_cents,
    created_by,
    updated_by
  )
  select
    category_id,
    name,
    slug,
    barcode,
    sku,
    product_kind,
    service_type,
    service_category,
    description,
    is_active,
    sell_online,
    inventory_tracking,
    default_price_type,
    nullif(cost_cents, 0),
    'seed',
    'seed'
  from resolved_products
  on conflict (slug) do update
    set category_id        = excluded.category_id,
        name               = excluded.name,
        barcode            = excluded.barcode,
        product_sku        = excluded.product_sku,
        product_kind       = excluded.product_kind,
        service_type       = excluded.service_type,
        service_category   = excluded.service_category,
        description        = excluded.description,
        is_active          = excluded.is_active,
        sell_online        = excluded.sell_online,
        inventory_tracking = excluded.inventory_tracking,
        default_price_type = excluded.default_price_type,
        our_cost_cents     = excluded.our_cost_cents,
        updated_at         = now(),
        updated_by         = excluded.updated_by
  returning id, slug
),
price_seed as (
  select * from (
    values
      ('electrolyte-drink','retail',300,'USD',true,null,null,null,null,null,null,false),
      ('electrolyte-drink','online',300,'USD',false,null,null,null,null,null,null,false),
      ('energy-drink','retail',400,'USD',true,null,null,null,null,null,null,false),
      ('energy-drink','online',400,'USD',false,null,null,null,null,null,null,false),
      ('atlas-essential-baby-tee-black','retail',2500,'USD',true,null,null,null,null,null,null,false),
      ('atlas-essential-baby-tee-black','online',2500,'USD',false,null,null,null,null,null,null,false),
      ('atlas-essential-shirt-black','retail',2790,'USD',true,null,null,null,null,null,null,false),
      ('atlas-essential-shirt-black','online',2790,'USD',false,null,null,null,null,null,null,false),
      ('towel-service','retail',500,'USD',true,null,null,null,'service',null,null,false),
      ('towel-service','online',500,'USD',false,null,null,null,'service',null,null,false),
      ('water','retail',150,'USD',true,null,null,null,null,null,null,false),
      ('water','online',150,'USD',false,null,null,null,null,null,null,false),
      ('personal-training-1-session','package',15000,'USD',true,null,null,1,'session',null,null,false),
      ('personal-training-4-sessions-month','recurring',60000,'USD',true,'month',1,4,'session',1,'month',false),
      ('personal-training-8-sessions-month','recurring',104000,'USD',true,'month',1,8,'session',1,'month',false),
      ('personal-training-12-sessions-month','recurring',132000,'USD',true,'month',1,12,'session',1,'month',false),
      ('inbody-consultation','complimentary',0,'USD',true,null,null,1,'session',null,null,false),
      ('open-gym-day-pass','package',2500,'USD',true,null,null,1,'day',null,null,false),
      ('open-gym-week-pass','package',10500,'USD',true,null,null,1,'week',1,'week',false),
      ('recovery-room-elevated-elite','complimentary',0,'USD',true,null,null,4,'session',1,'month',false),
      ('membership-essential','recurring',12000,'USD',true,'month',1,null,null,null,null,true),
      ('membership-elevated','recurring',15000,'USD',true,'month',1,null,null,null,null,true),
      ('membership-elite','recurring',18000,'USD',true,'month',1,null,null,null,null,true),
      ('trainer-agreement','recurring',80000,'USD',true,'month',1,null,null,null,null,true)
  ) as t(product_slug, price_type, amount_cents, currency, is_default, billing_period, billing_interval, benefit_quantity, benefit_unit, benefit_window_quantity, benefit_window_unit, is_unlimited)
),
resolved_prices as (
  select
    up.id as product_id,
    ps.price_type,
    ps.amount_cents,
    ps.currency,
    ps.is_default,
    ps.billing_period,
    ps.billing_interval,
    ps.benefit_quantity,
    ps.benefit_unit,
    ps.benefit_window_quantity,
    ps.benefit_window_unit,
    ps.is_unlimited
  from price_seed ps
  join upsert_products up on up.slug = ps.product_slug
),
upsert_prices as (
  insert into public.product_prices (
    product_id,
    price_type,
    amount_cents,
    currency,
    billing_period,
    billing_interval,
    benefit_quantity,
    benefit_unit,
    benefit_window_quantity,
    benefit_window_unit,
    is_unlimited,
    is_default,
    is_active,
    metadata
  )
  select
    product_id,
    price_type,
    amount_cents,
    currency,
    billing_period,
    billing_interval,
    benefit_quantity,
    benefit_unit,
    benefit_window_quantity,
    benefit_window_unit,
    is_unlimited,
    is_default,
    true,
    jsonb_build_object('source','mindbody')
  from resolved_prices
  on conflict (product_id, price_type) do update
    set amount_cents           = excluded.amount_cents,
        currency               = excluded.currency,
        billing_period         = excluded.billing_period,
        billing_interval       = excluded.billing_interval,
        benefit_quantity       = excluded.benefit_quantity,
        benefit_unit           = excluded.benefit_unit,
        benefit_window_quantity= excluded.benefit_window_quantity,
        benefit_window_unit    = excluded.benefit_window_unit,
        is_unlimited           = excluded.is_unlimited,
        is_default             = excluded.is_default,
        is_active              = excluded.is_active,
        metadata               = excluded.metadata,
        updated_at             = now()
  returning product_id
)
select count(distinct product_id) as products_seeded from upsert_prices;

-- Verification helpers
-- select p.name, pp.price_type, pp.amount_cents, pp.benefit_quantity, pp.benefit_unit, pp.benefit_window_quantity, pp.benefit_window_unit
--   from public.products p
--   join public.product_prices pp on pp.product_id = p.id
--  order by p.name, pp.price_type;
