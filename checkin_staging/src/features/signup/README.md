# Features / Signup (Scaffold)

This folder will contain the staff-assisted signup UI and handlers.

Planned components:
- `views.py` (Flask routes):
  - `GET /staff/signup` (form)
  - `POST /api/signup/checkout_session` (creates Stripe Checkout Session)
  - `POST /webhooks/stripe` (event handling)
- `templates/checkin/signup_*` (HTML)
- `static/checkin/signup.js` (form + redirect to Checkout)

Notes:
- No code lives here yet; see `docs/FEATURE_SIGNUP.md` for requirements and envs.
