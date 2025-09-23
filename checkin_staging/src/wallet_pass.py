"""Apple Wallet pass helpers for GymSense check-in."""

from __future__ import annotations

import base64
import io
import json
import os
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from cryptography.hazmat.primitives.serialization.pkcs7 import (
    PKCS7Options,
    PKCS7SignatureBuilder,
)

PASS_CERT_ENV = "APPLE_PASS_CERT_BASE64"  # PKCS12 bundle
PASS_KEY_PASSPHRASE_ENV = "APPLE_PASS_KEY_PASSPHRASE"
PASS_TEAM_ID_ENV = "APPLE_TEAM_ID"
PASS_TYPE_ID_ENV = "APPLE_PASS_TYPE_ID"
PASS_WWDR_ENV = "APPLE_WWDR_CERT_BASE64"
ORG_NAME_ENV = "APPLE_PASS_ORG_NAME"

def _env_truth(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class WalletPassResult:
    filename: str
    data: bytes
    content_type: str = "application/vnd.apple.pkpass"


_ASSETS = None


def wallet_pass_configured() -> bool:
    required = [PASS_CERT_ENV, PASS_KEY_PASSPHRASE_ENV, PASS_TEAM_ID_ENV, PASS_TYPE_ID_ENV, PASS_WWDR_ENV]
    return all(os.environ.get(name) for name in required)


def _load_certificates() -> tuple:
    cert_b64 = os.environ.get(PASS_CERT_ENV)
    wwdr_b64 = os.environ.get(PASS_WWDR_ENV)
    if not cert_b64 or not wwdr_b64:
        raise RuntimeError("Wallet pass signing certificates not configured")
    try:
        p12_bytes = base64.b64decode(cert_b64)
        wwdr_bytes = base64.b64decode(wwdr_b64)
    except Exception as exc:
        raise RuntimeError("Unable to decode wallet pass certificates") from exc
    passphrase = os.environ.get(PASS_KEY_PASSPHRASE_ENV, "").encode()
    key, cert, additional = pkcs12.load_key_and_certificates(p12_bytes, passphrase)
    if key is None or cert is None:
        raise RuntimeError("Pass certificate bundle missing key or certificate")
    wwdr_cert = x509.load_der_x509_certificate(wwdr_bytes)
    chain = [wwdr_cert]
    if additional:
        chain.extend(additional)
    return key, cert, chain


def _asset_bytes(asset_name: str) -> bytes:
    global _ASSETS
    if _ASSETS is None:
        asset_dir = Path(__file__).resolve().parent / "static" / "wallet"
        _ASSETS = {p.name: p.read_bytes() for p in asset_dir.glob("*.png")}
    if asset_name not in _ASSETS:
        raise FileNotFoundError(f"Wallet pass asset missing: {asset_name}")
    return _ASSETS[asset_name]


def _member_serial(member: dict, token: str) -> str:
    member_id = member.get("id") or member.get("member_id") or uuid.uuid4().hex
    prefix = str(member_id)
    suffix = token[:8] if token else uuid.uuid4().hex[:8]
    return f"{prefix}-{suffix}"


def build_member_wallet_pass(member, token: str, base_url: str) -> WalletPassResult:
    if not wallet_pass_configured():
        raise RuntimeError("Wallet pass feature is not configured")
    key, cert, chain = _load_certificates()

    org_name = os.environ.get(ORG_NAME_ENV, "GymSense")
    team_id = os.environ[PASS_TEAM_ID_ENV]
    pass_type_id = os.environ[PASS_TYPE_ID_ENV]

    def _get(field: str, default: str = ""):
        if isinstance(member, dict):
            return member.get(field, default)
        try:
            return member[field]
        except Exception:
            return default

    member_name = (_get("name") or "Member").strip()
    member_tier = (_get("membership_tier") or _get("membership_tier_normalized") or "Member").strip().title()
    email = _get("email") or _get("email_lower") or ""
    serial = _member_serial(member, token)
    qr_link = f"{base_url}/member/qr?token={token}"

    pass_json = {
        "formatVersion": 1,
        "passTypeIdentifier": pass_type_id,
        "teamIdentifier": team_id,
        "organizationName": org_name,
        "description": "Atlas Gym QR Check-In",
        "serialNumber": serial,
        "logoText": "",
        "foregroundColor": "rgb(16,23,42)",
        "backgroundColor": "rgb(242,244,247)",
        "labelColor": "rgb(99,112,138)",
        "barcode": {
            "format": "PKBarcodeFormatQR",
            "message": token,
            "messageEncoding": "iso-8859-1",
            "altText": "Show this QR at the Atlas Gym kiosk"
        },
        "locations": [
            {
                "latitude": 33.618973,
                "longitude": -117.719061,
                "relevantText": "You're near The Atlas Gym — tap to check in",
                "maxDistance": 200
            }
        ],
        "eventTicket": {
            "primaryFields": [
                {"key": "member", "label": "Member", "value": member_name}
            ],
            "secondaryFields": [
                {"key": "tier", "label": "Membership", "value": member_tier or "Atlas Member"}
            ],
            "auxiliaryFields": [],
            "backFields": [
                {"key": "email", "label": "Email", "value": email or "—"},
                {"key": "link", "label": "Open QR Page", "value": qr_link}
            ]
        }
    }

    now_iso = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    pass_json["relevantDate"] = now_iso

    files = {
        "pass.json": json.dumps(pass_json, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        "icon.png": _asset_bytes("icon.png"),
        "icon@2x.png": _asset_bytes("icon@2x.png"),
        "logo.png": _asset_bytes("logo.png"),
        "logo@2x.png": _asset_bytes("logo@2x.png"),
        "strip.png": _asset_bytes("strip.png"),
        "strip@2x.png": _asset_bytes("strip@2x.png"),
    }

    manifest = {}
    for name, data in files.items():
        digest = hashes.Hash(hashes.SHA1())
        digest.update(data)
        manifest[name] = digest.finalize().hex()

    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    files["manifest.json"] = manifest_bytes

    builder = PKCS7SignatureBuilder().set_data(manifest_bytes)
    builder = builder.add_signer(cert, key, hashes.SHA256())
    for extra_cert in chain:
        builder = builder.add_certificate(extra_cert)
    signature = builder.sign(Encoding.DER, [PKCS7Options.DetachedSignature])

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
        zf.writestr("signature", signature)

    filename = f"atlas-gym-checkin-{serial}.pkpass"
    return WalletPassResult(filename=filename, data=buffer.getvalue())


__all__ = [
    "WalletPassResult",
    "wallet_pass_configured",
    "build_member_wallet_pass",
]
