# Member Sign‑Up & Billing (Staff‑Assisted MVP)

Scope: Staff‑assisted onboarding in‑gym on the iPad (no self‑service yet). Uses Stripe Checkout for subscriptions; no card data handled by us. On success, create/update the member + active membership in Supabase and send the QR email.

## Goals (MVP)
- Staff flow only: `/staff/signup` (mobile‑friendly) behind staff auth (separate from kiosk PIN).
- Plans: three tiers mapped to Stripe Prices (Essential/Elevated/Elite, monthly).
- Payments: Stripe Checkout Sessions (software‑only). Terminal/Tap‑to‑Pay is Post‑MVP.
- Success: Webhook confirms payment, upserts DB, sends QR email, member can check‑in immediately.

## UX Flows
1) Staff‑assisted (iPad/phone)
   - Staff logs in (staff auth) → opens `/staff/signup` → selects tier → enters name/email/phone → “Start Checkout”.
   - App creates a Stripe Checkout Session and opens Stripe payment page.
   - On success → Stripe webhook → upsert `members` + `memberships` → send QR email → auto‑redirect to success page.

2) Post‑success Communications
   - Email with “Open My QR Code” button and brief kiosk instructions; fallback token included.

## Data Model (deltas)
- `members`
  - `stripe_customer_id text`
- `memberships`
  - `provider text default 'stripe'`
  - `stripe_subscription_id text`
  - `price_id text`
  - `status text` remains (active/inactive)

See migration: `seed/migrations/20250914__signup_billing.sql`.

## API & Routes (planned)
- UI
  - `GET /staff/signup` — form: member info + tier; creates Checkout session.
  - `GET /join/success` / `GET /join/cancel` — landing pages used by Stripe success/cancel.
- Backend
  - `POST /api/signup/checkout_session` — body: name,email,phone,tier → returns Checkout URL.
  - `POST /webhooks/stripe` — verifies signature; on `checkout.session.completed`/`customer.subscription.created/updated` → upsert DB; sends QR email on first success.

## Stripe Configuration (staging first)
- Dashboard → Create 3 Products/Prices (monthly): Essential/Elevated/Elite.
- API keys (test): `STRIPE_API_KEY`.
- Webhook endpoint (staging): `https://staging.gymsense.io/webhooks/stripe` → capture secret as `STRIPE_WEBHOOK_SECRET`.
- Env
  - `STRIPE_API_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `STRIPE_PRICE_ESSENTIAL`, `STRIPE_PRICE_ELEVATED`, `STRIPE_PRICE_ELITE`
  - `JOIN_SUCCESS_URL=https://staging.gymsense.io/join/success`
  - `JOIN_CANCEL_URL=https://staging.gymsense.io/join/cancel`

## Staff Authentication (for payment flows)
- MVP option A (recommended): Supabase Auth (email/pass or magic links) for staff users; roles in a small `staff_users` table. Low lift, good path to multi‑tenant and lower ops.
- MVP option B (interim): Simple password + session within our app restricted to `/staff/signup` only; replace with Supabase Auth soon.

Why Supabase Auth
- Keeps costs low, integrates with our Supabase DB, and scales to multiple tenants by mapping staff accounts to orgs. We are already on Supabase; no extra vendor.

## Multi‑tenant Considerations (later)
- Add `organizations` table and map `host -> org_id` (e.g., `atlas.gymsense.io`).
- Keep a single Supabase project initially; use `org_id` FK on `members`, `memberships`, `check_ins` if/when needed.
- Later options: per‑tenant projects vs. single project + RLS by `org_id`.

## Costs (est.)
- Stripe: standard processing fees (e.g., 2.9% + $0.30 US). No extra monthly fee for Checkout. Terminal later adds hardware + $0.10–$0.15 per transaction.
- Supabase: free/dev tiers initially; small usage. Production plan depends on scale (rows/storage/egress). We’re light.
- Render: current service cost only (we already run it). No extra services needed.
- SendGrid: free tier sufficient at start; upgrade when sending volume grows.

## Rollout Plan (staging → prod)
1) Create Stripe test Prices and webhook; set staging envs; implement endpoints; test end‑to‑end with test cards.
2) Switch to live keys/Prices for prod; set prod webhook secret; test with a $1 test product or coupon.
3) Add staff auth (Supabase Auth) to replace PIN for `/staff/signup`.
4) Terminal (optional) and Wallet passes (next sprint).

## Open Questions
- Stripe: do we want simple monthly only, or annual options? (MVP: monthly only.)
- Refund/Cancel policy text (display during checkout; email template copy).
- Terms/waiver: add a link + checkbox on the signup form? (Log consent later in `consent_logs`.)

## References
- Migrations: `seed/migrations/20250914__signup_billing.sql`
- Current DB helpers/views: `seed/supabase_schema_only.sql`

