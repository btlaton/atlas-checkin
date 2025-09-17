# GymSense Landing Page — Concept Draft (Premium Minimal)

This document captures the planned structure and copy for https://gymsense.io before implementation. The page will live separately from the check-in bundle and share the premium minimalist aesthetic.

## Design Principles
- High contrast black/white palette with a single charcoal accent; generous whitespace.
- Bold sans-serif typography with Oleo Script used for the “GymSense” logotype.
- Rounded 24px cards, mild shadows, and smooth fades to echo the kiosk/staff UI.
- Minimal JS (scroll-to buttons, fade-in on scroll) to keep the marketing site lightweight.

## Section Outline
1. **Hero**
   - Headline: “Radical Simplicity for Gym Check‑Ins”
   - Subtext: concise value prop referencing QR-first, transparent pricing, and staff console.
   - Primary CTA: “Book a Demo” (mailto or link to Calendly placeholder)
   - Secondary CTA: “View Live Staging” (links to `https://staging.gymsense.io/kiosk`)
   - Visual: device mockup screenshot (placeholder image container).

2. **Value Pillars (3 cards)**
   - Transparent affordability (call out $99/mo vs competitors’ fees)
   - Delightfully streamlined (QR check-in under 2 seconds)
   - Built for operators (Supabase foundation, open data)

3. **Feature Highlights**
   - Two-column layout mixing copy and imagery: “Front Desk Flow” and “Staff Console & Insights”.
   - Bullet list referencing live busyness banner, instant resend, multi-device support.

4. **Comparison Strip**
   - Table comparing GymSense vs PushPress vs Mindbody (pricing, QR-first, hidden fees).

5. **Testimonials**
   - Quote from Atlas Gym staff (placeholder copy) emphasizing ease + member delight.

6. **Pricing**
   - Single price card: “$99/month flat. Stripe processing only.”
   - Include CTA button “Talk to Sales”.

7. **Call to Action / Waitlist**
   - Email capture form (name + email). Submit hits a placeholder `/` handler (to be wired later).
   - Social proof tag (“Launching with The Atlas Gym this month”).

8. **Footer**
   - GymSense logotype (Oleo Script) + tagline on one line.
   - Secondary links: Product, Pricing, Docs, Contact, Privacy.

## Implementation Plan
- Create `landing/index.html` and `landing/styles.css` in a new `landing/` directory with static markup/styles.
- Reference Google Fonts for Oleo Script (same as kiosk/staff usage).
- Add `landing/script.js` for small interactions (scroll to sections, simple form validation placeholder).
- Provide instructions for hosting (e.g., GitHub Pages or static hosting) without touching Flask app.

