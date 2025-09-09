# Atlas Check-In — Staging Bundle

Upload this folder to a new GitHub repository and deploy on Render.

## Contents
- `Dockerfile` — container build for the service
- `.dockerignore` — keeps the image lean
- `src/checkin_app.py` — Flask app exposing `app`
- `src/templates/checkin/*.html` — kiosk/admin/member pages
- `src/static/checkin/*` — CSS/JS assets (uses CDN fallback for QR scanning/render)

## Render Deployment
1) Create a new Web Service from this repo (Render detects `Dockerfile`).
2) Add a Persistent Disk:
   - Name: `data`, Mount: `/data`, Size: 1–2 GB
3) Environment Variables:
   - `CHECKIN_DB_PATH=/data/checkin.sqlite3`
   - `CHECKIN_SESSION_SECRET=<random-long-string>`
   - `CHECKIN_DUP_WINDOW_MINUTES=5`
   - First run only: `ENABLE_INIT_PIN=1`
   - (Optional) SMTP: `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`
4) Deploy → Initialize PIN:
   - Visit: `https://<service>/admin/init_pin?pin=1234&name=Admin`
   - Remove `ENABLE_INIT_PIN` and redeploy
5) Verify:
   - `https://<service>/healthz` → ok
   - `https://<service>/admin/login` → login with PIN
   - `https://<service>/kiosk` → kiosk page

## Notes
- iPad scanning uses native API if available, falls back to jsQR via CDN.
- Member QR page renders locally if `/static/checkin/qrcode.min.js` is present, otherwise uses an external QR image.

