-- Backfill up to 500 missing QR tokens (run repeatedly until 0 rows updated)
update public.members m
set qr_token = public.gen_token_urlsafe(18), updated_at = now()
where m.id in (
  select id from public.members where qr_token is null order by id asc limit 500
);

-- Check remaining
-- select count(*) from public.members where qr_token is null;
