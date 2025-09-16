# Atlas Check-In — GA Launch Checklist

Use this list to track the final work needed before enabling the Atlas Check-In kiosk for all members. Items are grouped to make owner assignment easier. Mark each item as you complete it.

## 1. Functional Testing (Staging)
- [ ] Camera scan on kiosk (`/kiosk`) with supported iPad (front camera, BarcodeDetector + jsQR fallback)
- [ ] Manual email check-in, including duplicate-window handling
- [ ] Manual name-only check-in flow (single match + fallback messaging)
- [ ] QR resend to email (verify SendGrid message in inbox/spam)
- [ ] Admin PIN login, dashboard load, and recent check-in listing
- [ ] Staff dashboard metrics API (`/api/staff/metrics`) populates 10 recent entries and 7-day trend
- [ ] CSV import preview (`/admin/members/import/preview`) on latest Mindbody export
- [ ] Member detail view with visit history and resend button
- [ ] Health check `/healthz` returning 200 under load
- [ ] Session secret/regression tests after reloading the service

## 2. Infrastructure & Configuration
- [ ] Render staging/prod services running latest container image
- [ ] `ENABLE_STAFF_SIGNUP=0` on staging/prod GA launch builds
- [ ] `CHECKIN_SESSION_SECRET` rotated to long random strings per environment
- [ ] Supabase connection verified (`DATABASE_URL` pooler credentials)
- [ ] Supabase schema up to date via `seed/supabase_schema_only.sql`
- [ ] Real member roster imported with `supabase_upsert_from_temp.sql`
- [ ] `SMTP_*` env vars (host/user/pass/from) configured with domain-authenticated sender
- [ ] SendGrid domain authentication (SPF/DKIM/DMARC) complete for `gymsense.io`
- [ ] Custom domain `atlas.gymsense.io` mapped with TLS on Render
- [ ] CDN or local copy of `jsqr.min.js` verified (no external dependency at runtime)
- [ ] Logging aggregation plan (Render logs, optional Sentry) confirmed
- [ ] Implement light rate limiting (Render service, Cloudflare, or Flask extension) on `/api/qr/resend` and admin APIs
- [ ] CSRF and PIN cooldown/rotation plan documented (even if manual)

## 3. Data Hygiene
- [ ] All active members show `qr_token` populated (run `supabase_token_backfill_batch.sql` if needed)
- [ ] Email formatting normalized (check sample queries)
- [ ] Mindbody export cadence agreed and documented
- [ ] Deactivate/refresh procedure defined for former members (manual or automated)

## 4. Operational Playbooks
- [ ] PIN initialization instructions on file (who can rotate, how to store)
- [ ] SMTP test workflow documented for front desk leads
- [ ] Support escalation path defined (who handles kiosk outages, SendGrid failures, Supabase downtime)
- [ ] On-call or notification plan (Render alerts, email forwarding, etc.)
- [ ] Daily health check routine (staff open `/staff` dashboard at open)

## 5. Hardware & Physical Setup
- [ ] iPad selected and purchased
  - Recommended: **iPad 9th Generation (10.2-inch, 64 GB, Wi-Fi)** — lowest-cost current model that runs iPadOS 17, front camera supports BarcodeDetector, Lightning port works with existing chargers. (~$329 MSRP, frequently <$280 refurbished)
  - Alternative (USB-C): iPad 10th Gen (10.9-inch) if you want the newer design and USB-C cabling; costs ~$449.
- [ ] Protective case / enclosure chosen
  - Budget: **Logi Combo Touch** or **SUPCASE Unicorn Beetle Pro** for edge protection and hand strap
  - Kiosk-style: **CTA Digital Security Enclosure** (lockable, tabletop) or **AboveTEK Heavy Duty Aluminum Stand** with cable routing
- [ ] Stand or mount selected
  - Desk placement: weighted swivel stand (AboveTEK, Lamicall) keeps device at eye level
  - Wall mount (optional): mount near entrance if front desk space is limited
- [ ] Power & cabling plan finalized
  - Use 90-degree Lightning/USB-C cable with braided sheath to reduce strain
  - Secure cable run under counter with adhesive clips; plug into surge-protected power strip
  - Keep spare cable + 20W USB-C power adapter in supply drawer
- [ ] Physical layout confirmed
  - Place stand on left side of main check-in desk so members approach from traffic flow without blocking staff
  - Angle screen slightly toward entrance for faster camera acquisition
  - Ensure 3–4 ft of clearance so small groups can queue without blocking exit
  - Add subtle floor marker or sign “Scan your Atlas QR here” at eye level
- [ ] Guided Access / kiosk mode configured (iPad Settings → Accessibility → Guided Access)
- [ ] Screen auto-lock disabled or set to 15 minutes; enable “Auto-Lock when Idle” inside Guided Access
- [ ] Cleaning & maintenance kit (screen wipes) stocked near kiosk

## 6. Launch Day & Post-Launch
- [ ] Smoke test morning-of launch (QR scan + manual check-in)
- [ ] Staff refresher demo (5-minute huddle)
- [ ] Monitor check-in counts hourly on day 1 via `/staff`
- [ ] Collect member feedback end of week; capture follow-up actions
- [ ] Plan next sprint (wallet passes, admin actions, signup feature) once GA metrics look healthy

Keep this checklist in version control so we can track updates via PRs and reuse it for future locations.
