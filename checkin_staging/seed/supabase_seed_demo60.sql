-- Demo seed: 60 members with realistic data for signup/billing QA
-- Run after supabase_schema_bootstrap.sql and supabase_schema_only.sql
-- Safe to re-run; uses upsert on external_id

with seed as (
  select * from (
    values
      ('DEMO0001','Amelia Chen','amelia.chen','4155550101','essential','cus_demo0001'),
      ('DEMO0002','Marcus Rivera','marcus.rivera','4155550102','essential','cus_demo0002'),
      ('DEMO0003','Priya Patel','priya.patel','4155550103','essential','cus_demo0003'),
      ('DEMO0004','Daniel Brooks','daniel.brooks','4155550104','essential','cus_demo0004'),
      ('DEMO0005','Sofia Alvarez','sofia.alvarez','4155550105','essential','cus_demo0005'),
      ('DEMO0006','Oliver Bennett','oliver.bennett','4155550106','essential','cus_demo0006'),
      ('DEMO0007','Hannah Kim','hannah.kim','4155550107','essential','cus_demo0007'),
      ('DEMO0008','Malik Thompson','malik.thompson','4155550108','essential','cus_demo0008'),
      ('DEMO0009','Grace Li','grace.li','4155550109','essential','cus_demo0009'),
      ('DEMO0010','Ethan Walker','ethan.walker','4155550110','essential','cus_demo0010'),
      ('DEMO0011','Isabella Flores','isabella.flores','4155550111','essential','cus_demo0011'),
      ('DEMO0012','Carter Jenkins','carter.jenkins','4155550112','essential','cus_demo0012'),
      ('DEMO0013','Naomi Scott','naomi.scott','4155550113','essential','cus_demo0013'),
      ('DEMO0014','Devin Clark','devin.clark','4155550114','essential','cus_demo0014'),
      ('DEMO0015','Lucia Martinez','lucia.martinez','4155550115','essential','cus_demo0015'),
      ('DEMO0016','Aaron Green','aaron.green','4155550116','essential','cus_demo0016'),
      ('DEMO0017','Chloe Parker','chloe.parker','4155550117','essential','cus_demo0017'),
      ('DEMO0018','Diego Ramirez','diego.ramirez','4155550118','essential','cus_demo0018'),
      ('DEMO0019','Maya Singh','maya.singh','4155550119','essential','cus_demo0019'),
      ('DEMO0020','Jordan Price','jordan.price','4155550120','essential','cus_demo0020'),
      ('DEMO0021','Emily Turner','emily.turner','4155550121','essential','cus_demo0021'),
      ('DEMO0022','Victor Morales','victor.morales','4155550122','essential','cus_demo0022'),
      ('DEMO0023','Lila Sanders','lila.sanders','4155550123','essential','cus_demo0023'),
      ('DEMO0024','Gabriel Hughes','gabriel.hughes','4155550124','essential','cus_demo0024'),
      ('DEMO0025','Avery Coleman','avery.coleman','4155550125','essential','cus_demo0025'),
      ('DEMO0026','Nora Watson','nora.watson','4155550126','essential','cus_demo0026'),
      ('DEMO0027','Samuel Perry','samuel.perry','4155550127','essential','cus_demo0027'),
      ('DEMO0028','Leah Bryant','leah.bryant','4155550128','essential','cus_demo0028'),
      ('DEMO0029','Xavier Cooper','xavier.cooper','4155550129','essential','cus_demo0029'),
      ('DEMO0030','Tessa Reynolds','tessa.reynolds','4155550130','essential','cus_demo0030'),
      ('DEMO0031','Julian Ortiz','julian.ortiz','4155550131','essential','cus_demo0031'),
      ('DEMO0032','Paige Sullivan','paige.sullivan','4155550132','essential','cus_demo0032'),
      ('DEMO0033','Isaiah Howard','isaiah.howard','4155550133','essential','cus_demo0033'),
      ('DEMO0034','Stella Gordon','stella.gordon','4155550134','essential','cus_demo0034'),
      ('DEMO0035','Elias Foster','elias.foster','4155550135','essential','cus_demo0035'),
      ('DEMO0036','Harper Watts','harper.watts','4155550136','essential','cus_demo0036'),
      ('DEMO0037','Rowan Bailey','rowan.bailey','4155550137','essential','cus_demo0037'),
      ('DEMO0038','Camille Rogers','camille.rogers','4155550138','essential','cus_demo0038'),
      ('DEMO0039','Miles Barrett','miles.barrett','4155550139','essential','cus_demo0039'),
      ('DEMO0040','Ivy Carlson','ivy.carlson','4155550140','essential','cus_demo0040'),
      ('DEMO0041','Kieran Douglas','kieran.douglas','4155550141','elevated','cus_demo0041'),
      ('DEMO0042','Serena Walsh','serena.walsh','4155550142','elevated','cus_demo0042'),
      ('DEMO0043','Damon Pierce','damon.pierce','4155550143','elevated','cus_demo0043'),
      ('DEMO0044','Alana Shepherd','alana.shepherd','4155550144','elevated','cus_demo0044'),
      ('DEMO0045','Zeke Harrison','zeke.harrison','4155550145','elevated','cus_demo0045'),
      ('DEMO0046','Jocelyn Burke','jocelyn.burke','4155550146','elevated','cus_demo0046'),
      ('DEMO0047','Mateo Delgado','mateo.delgado','4155550147','elevated','cus_demo0047'),
      ('DEMO0048','Simone Patel','simone.patel','4155550148','elevated','cus_demo0048'),
      ('DEMO0049','Colin Fraser','colin.fraser','4155550149','elevated','cus_demo0049'),
      ('DEMO0050','Bianca Russo','bianca.russo','4155550150','elevated','cus_demo0050'),
      ('DEMO0051','Quentin Hayes','quentin.hayes','4155550151','elite','cus_demo0051'),
      ('DEMO0052','Sabrina Lowell','sabrina.lowell','4155550152','elite','cus_demo0052'),
      ('DEMO0053','Andre Wallace','andre.wallace','4155550153','elite','cus_demo0053'),
      ('DEMO0054','Penelope Vaughn','penelope.vaughn','4155550154','elite','cus_demo0054'),
      ('DEMO0055','Sterling Drake','sterling.drake','4155550155','elite','cus_demo0055'),
      ('DEMO0056','Vivian Cortez','vivian.cortez','4155550156','elite','cus_demo0056'),
      ('DEMO0057','Malikah Grant','malikah.grant','4155550157','elite','cus_demo0057'),
      ('DEMO0058','Cedric Monroe','cedric.monroe','4155550158','elite','cus_demo0058'),
      ('DEMO0059','Helena Winters','helena.winters','4155550159','elite','cus_demo0059'),
      ('DEMO0060','Jasper Bell','jasper.bell','4155550160','elite','cus_demo0060')
  ) as t(external_id, name_full, email_slug, phone_raw, tier, stripe_cust)
),
normalized as (
  select
    external_id,
    name_full,
    lower('btlaton+' || email_slug || '@gmail.com') as email_lower,
    public.e164_us(phone_raw) as phone_e164,
    tier,
    stripe_cust
  from seed
),
upsert_members as (
  insert into public.members (external_id, name, email_lower, phone_e164, membership_tier, status, stripe_customer_id)
  select
    n.external_id,
    n.name_full,
    n.email_lower,
    n.phone_e164,
    n.tier,
    'active',
    n.stripe_cust
  from normalized n
  on conflict (external_id) do update
    set name              = excluded.name,
        email_lower       = excluded.email_lower,
        phone_e164        = excluded.phone_e164,
        membership_tier   = excluded.membership_tier,
        status            = 'active',
        stripe_customer_id = excluded.stripe_customer_id,
        updated_at        = now()
  returning external_id
),
ensure_tokens as (
  update public.members m
  set qr_token = public.gen_token_urlsafe(18),
      updated_at = now()
  where m.qr_token is null
    and exists (select 1 from normalized n where n.external_id = m.external_id)
)
select count(*) as inserted_or_updated_rows from upsert_members;

-- Verification helpers
-- select membership_tier, count(*) from public.members group by 1;
-- select external_id, name, email_lower, phone_e164, membership_tier, stripe_customer_id from public.members order by external_id limit 10;
