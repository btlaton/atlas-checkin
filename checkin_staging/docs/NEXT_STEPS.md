# Next Steps — Member Sign-Up & Billing Feature

## Current State (Sep 2025)
- Check-in kiosk, staff dashboard, admin directory, and wallet passes are production-ready.
- Staging test cycle complete; production launch blocking task is importing the live member roster into Supabase (run `supabase_upsert_from_temp.sql` against the prod project and confirm `membership_tier` + `qr_token`).
- Custom domain `atlas.gymsense.io` and SendGrid domain auth are live.
- Kiosk/staff metrics auto-refresh after each check-in; member comms drafted.

## Outstanding Pre-GA Tasks
1. **Production roster import**
   - Mindbody CSV → `members_stage` → `supabase_upsert_from_temp.sql`
   - Run `supabase_token_backfill_batch.sql` until `qr_token` null count = 0.
   - Spot-check `/admin/members` for tier/status and `/staff` for updated counts.
2. **Operational polish (optional now, can defer)**
   - Logging / rate limiting / CSRF plan
   - Finalize hardware purchases + physical layout checklist
   - Establish Mindbody export cadence

## Kick-Off Notes for Sign-Up/Billing Thread
- Feature flag remains `ENABLE_STAFF_SIGNUP=0` in production; staging has scaffolded endpoints (`/staff/signup`, `POST /api/signup/checkout_session`, `POST /webhooks/stripe`).
- Schema now stores `membership_tier` directly on `members`; no separate `memberships` table. Update migrations accordingly when we build billing.
- Stripe artifacts needed:
  - Test Prices (Essential/Elevated/Elite) already configured; confirm live counterparts before GA.
  - Webhook secret: `STRIPE_WEBHOOK_SECRET`
  - Success/cancel URLs point to `/join/success` and `/join/cancel`.
- Decisions pending for the new thread:
  - Staff authentication upgrade (Supabase Auth) for signup.
  - Cancellation/refund flows and comms.
  - Terminal/ACH roadmap.

Use this document as the hand-off context when we spin up the dedicated signup/billing discussion.
