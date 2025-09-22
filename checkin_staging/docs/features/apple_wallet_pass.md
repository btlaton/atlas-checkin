# Apple Wallet Pass (Atlas Gym)

## Status
- Feature branch: `feature/wallet-pass`
- Flag: `ENABLE_WALLET_PASS` (default `false`)
- API placeholder: `POST /api/pass/apple` (returns 404/503/501 until implemented)

## Secrets / Env Vars
Set the following when enabling the feature (base64 values are raw file contents encoded via `base64`):

- `ENABLE_WALLET_PASS=1`
- `APPLE_PASS_CERT_BASE64` – Pass Type certificate bundle (`.p12`) contents
- `APPLE_PASS_KEY_PASSPHRASE` – Passphrase used when exporting the `.p12`
- `APPLE_TEAM_ID` – Apple Developer Team ID (10 characters)
- `APPLE_PASS_TYPE_ID` – Identifier (e.g. `pass.gymsense.atlas`)
- `APPLE_WWDR_CERT_BASE64` – Apple WWDR intermediate certificate (.cer)
- `APPLE_PASS_ORG_NAME` *(optional)* – overrides organization label (defaults to GymSense)

## Implementation Notes
- Wallet pass generation lives in `src/wallet_pass.py`.
- Static branding assets reside under `src/static/wallet/` (icon/logo/strip @1x/@2x).
- Public download endpoint: `GET /member/pass.apple?token=<qr_token>` (feature-flagged).
- `POST /api/pass/apple` currently returns informative errors for API clients until extended.
- Keep staging/prod disabled until manual QA with real devices is complete.

### Encoding certificates for env vars

```bash
# Pass Type certificate (.p12)
base64 -i atlas-pass.p12 | tr -d '\n' > pass_cert.b64

# Apple WWDR certificate (.cer)
base64 -i AppleWWDRCAG3.cer | tr -d '\n' > wwdr.b64
```

Paste the resulting single-line strings into the corresponding Render environment variables.

## Outstanding Work
- Assemble pass.json schema + branding assets ✅
- Sign pass using Pass Type certificate & WWDR ✅
- Update email/staff UI with Add to Wallet CTA (guarded by flag) ✅
- Document rollout plan + certificate rotation sequence
- Hook Google Wallet parity *(future)*
