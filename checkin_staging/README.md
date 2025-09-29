# Atlas Check‑In — Staging Bundle

This is a self‑contained bundle for deploying the Atlas Check‑In service. It now runs against Supabase Postgres (via `DATABASE_URL`) and uses SendGrid for SMTP.

## Live Environments
- Staging: https://staging.gymsense.io
  - Kiosk: `/kiosk`
  - Admin: `/admin` (PIN‑gated)
  - Staff (mobile): `/staff` (PIN‑gated dashboard)
  - Health: `/healthz`
- Production: https://atlas-checkin-prod.onrender.com (custom domain pending)

## Contents
- `Dockerfile` — container build for the service
- `.dockerignore` — keeps the image lean
- `src/checkin_app.py` — Flask app exposing `app`
- `src/templates/checkin/*.html` — kiosk, admin, members, staff pages
- `src/static/checkin/*` — CSS/JS assets
- `seed/*.sql` — Supabase schema + seed + upsert scripts

## Current Feature Set (Sep 2025)
- Kiosk: Camera QR scanning (BarcodeDetector + jsQR fallback), email QR resend fallback, live busyness banner, success overlay/chime.
- Members: Resend QR (email-only), member QR page with server-generated PNG.
- Admin: PIN login (redirects to staff console) and Members directory (search/filter/paginate, detail with recent visits).
- Staff: Staff console at `/staff` (daily KPIs, last-hour pulse, 7-day bar trend, quick resend, recent check-ins, members directory link).
- DB: Supabase Postgres with `members` and `check_ins`; adapters for Postgres/SQLite.
- Email: SendGrid SMTP (via env). Staging verified end‑to‑end.
- Health: `/healthz` endpoint.
- Signup (staff-assisted scaffold, disabled unless `ENABLE_STAFF_SIGNUP=1`): `/staff/signup/login` (password gate), `/staff/signup` (form), Checkout Session creation, and Stripe webhook that upserts the member (including tier) and sends QR email; success/cancel placeholders.

## Configuration (Render)
Set per environment (staging/prod):

- Core
  - `DATABASE_URL` — Supabase pooled (pgBouncer 6543). Username must include project ref for pooler: `checkin_app.<project_ref>`.
  - `CHECKIN_SESSION_SECRET` — long random (unique per env)
  - `CHECKIN_DUP_WINDOW_MINUTES=5`
  - `ENABLE_INIT_PIN=1` — first run only; then remove and redeploy
  - `ENABLE_STAFF_SIGNUP=0` — keep `0` on staging/production GA build; set to `1` on dedicated signup testing branches/envs

- Core (required)
  - `CHECKIN_SESSION_SECRET` — Flask session secret
  - `DATABASE_URL` — Postgres connection string (Supabase)
  - `CHECKIN_ALLOW_SQLITE=1` — optional for local SQLite testing; leave unset in staging/prod so the app fails fast when `DATABASE_URL` is missing.

- SMTP (SendGrid)
  - `SMTP_HOST=smtp.sendgrid.net`
  - `SMTP_PORT=587`
  - `SMTP_USER=apikey`
  - `SMTP_PASS=<sendgrid_api_key>`
  - `SMTP_FROM=<verified sender>` (Single Sender or domain‑auth address, e.g., `notifications@gymsense.io`)

Custom domains (Render → Custom Domains):
- Staging: `staging.gymsense.io` (CNAME to Render; TLS auto‑provisioned)
- Prod: `atlas.gymsense.io` (pending)

## Supabase Schema & Seed
SQL files are under `seed/`:
- `supabase_schema_only.sql` — helpers (phone/token) and indexes (incl. unique on `members.external_id`).
- `supabase_seed_minimal.sql` — seeds 3 test members (idempotent).
- `supabase_seed_full.sql` — seeds 12 test members (idempotent).
- `supabase_upsert_from_temp.sql` — upsert from a temp table populated from Mindbody CSV; normalizes tier and QR tokens.
- `supabase_token_backfill_batch.sql` — backfills up to 500 missing QR tokens per run.

Run order (staging → prod):
1) `supabase_schema_only.sql`
2) `supabase_seed_minimal.sql` (or `supabase_seed_full.sql`) to verify app flows
3) Use `supabase_upsert_from_temp.sql` to load real members by external_id (tier normalized)

## Operations
- First‑time PIN init: `ENABLE_INIT_PIN=1` then open `/admin/init_pin?pin=1234&name=Admin`; remove the env and redeploy.
- SMTP test: Admin → “SMTP Test”.
- Diagnostics: While `ENABLE_INIT_PIN=1`, `/admin/db_diag` shows backend and a `SELECT 1` probe.

## Decisions & Notes
- App importer is deprecated for now; we’ll import via Supabase scripts (CSV → temp table → upsert).
- Staff portal is read‑only with quick resend; admin directory is read‑only + detail.
- Wallet passes and deeper personalization (quotes, last visit in success) are planned next.
- Kiosk triple‑tap → PIN is kept; `/staff` offers phone‑friendly access.

## Remaining Work to Productionize
- Domains & Email
  - Prod custom domain `atlas.gymsense.io` (CNAME + TLS).
  - SendGrid Domain Authentication for `gymsense.io` (SPF/DKIM/DMARC) and switch `SMTP_FROM` to a domain‑auth sender.
- Security & Abuse Controls
  - Light rate‑limit on `/api/qr/resend` and admin endpoints.
  - CSRF for admin forms; PIN cooldown/rotation.
- Reliability & UX
  - Vendor `jsqr.min.js` locally; keep BarcodeDetector as primary.
  - PWA hints/no‑sleep; document iPad Guided Access.
- Observability & Ops
  - Sentry; structured logs for check‑ins/resends.
  - Render blueprint (`render.yaml`) for one‑click envs.
- Features (near term)
  - Admin actions: resend/activate/inactivate from directory.
  - Member polish: add quotes + “last visit” on kiosk success; add Reply‑To support address.
  - Wallet passes (Apple/Google) — Sprint 2.
- Signup & Stripe (staging)
  - `ENABLE_STAFF_SIGNUP=1` — required to expose `/staff/signup` routes in environments dedicated to signup testing
  - `STAFF_SIGNUP_PASSWORD` — temporary password to unlock `/staff/signup`
  - `STRIPE_API_KEY` — test secret key (sk_test_...)
  - `STRIPE_WEBHOOK_SECRET` — test webhook signing secret (whsec_...)
  - `STRIPE_PRICE_ESSENTIAL` / `STRIPE_PRICE_ELEVATED` / `STRIPE_PRICE_ELITE` — Price IDs (price_...)
  - `JOIN_SUCCESS_URL` / `JOIN_CANCEL_URL` — e.g., `https://staging.gymsense.io/join/success` and `/join/cancel`
  - `COMMERCE_CHECKOUT_SUCCESS_URL` / `COMMERCE_CHECKOUT_CANCEL_URL` — optional overrides for staff-initiated Checkout flows (defaults point to `/staff/checkout/success|cancel`)
  - Signup & Billing: staff auth via Supabase Auth, /staff/billing KPIs, Stripe Terminal/ACH options.
