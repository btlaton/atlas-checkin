import os
import csv
import sqlite3
import hashlib
import hmac
import secrets
import smtplib
import io
import json
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, unquote
import socket

# Optional Postgres (Supabase) support via psycopg
DATABASE_URL = os.environ.get("DATABASE_URL")
ALLOW_SQLITE_FALLBACK = os.environ.get("CHECKIN_ALLOW_SQLITE", "0").strip().lower() in {"1", "true", "yes", "on"}
_PG_AVAILABLE = False
try:
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row as _pg_dict_row
        _PG_AVAILABLE = True
except Exception:
    _PG_AVAILABLE = False

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    session,
    abort,
    send_file,
)

from wallet_pass import wallet_pass_configured, build_member_wallet_pass


def get_db_path() -> str:
    base = os.environ.get("CHECKIN_DB_PATH")
    if base:
        return base
    here = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(os.path.dirname(here), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "checkin.sqlite3")


DB_PATH = get_db_path()
DUP_WINDOW_MINUTES = int(os.environ.get("CHECKIN_DUP_WINDOW_MINUTES", "5"))
SESSION_SECRET = os.environ.get("CHECKIN_SESSION_SECRET", "dev-secret-change-me")
STAFF_SIGNUP_PASSWORD = os.environ.get("STAFF_SIGNUP_PASSWORD")
STAFF_SIGNUP_ENABLED = os.environ.get("ENABLE_STAFF_SIGNUP", "0").strip().lower() in {"1", "true", "yes", "on"}
WALLET_PASS_ENABLED = os.environ.get("ENABLE_WALLET_PASS", "0").strip().lower() in {"1", "true", "yes", "on"}
COMMERCE_ENABLED = os.environ.get("ENABLE_COMMERCE", "0").strip().lower() in {"1", "true", "yes", "on"}
COMMERCE_DEFAULT_CURRENCY = os.environ.get("COMMERCE_CURRENCY", "USD").upper()
COMMERCE_ORDER_TYPES = {"retail", "membership", "guest_pass", "service", "mixed"}


def using_postgres() -> bool:
    if DATABASE_URL:
        return True
    if ALLOW_SQLITE_FALLBACK:
        return False
    raise RuntimeError(
        "DATABASE_URL is not configured. Set CHECKIN_ALLOW_SQLITE=1 to allow the SQLite fallback in local development."
    )


def _connect_sqlite() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _connect_postgres():
    if not _PG_AVAILABLE:
        raise RuntimeError(
            "DATABASE_URL is set but psycopg is not installed. Add psycopg[binary] to Dockerfile."
        )
    dsn = DATABASE_URL.strip()
    try:
        # Try to build an IPv4-preferring conninfo preserving hostname for TLS/SNI
        if dsn.startswith("postgres://") or dsn.startswith("postgresql://"):
            u = urlparse(dsn)
            host = u.hostname or ""
            port = u.port or 5432
            dbname = (u.path or "/postgres").lstrip("/") or "postgres"
            user = unquote(u.username) if u.username else None
            password = unquote(u.password) if u.password else None
            # Resolve IPv4 address for host (avoid IPv6 unreachable in some containers)
            ipv4 = None
            try:
                infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
                if infos:
                    ipv4 = infos[0][4][0]
            except Exception:
                ipv4 = None
            # Extract sslmode if present; default to require
            sslmode = "require"
            try:
                q = u.query or ""
                for kv in q.split("&"):
                    if not kv:
                        continue
                    k, _, v = kv.partition("=")
                    if k == "sslmode" and v:
                        sslmode = v
                        break
            except Exception:
                pass
            kwargs = {
                "host": host,
                "port": port,
                "dbname": dbname,
                "sslmode": sslmode,
                "row_factory": _pg_dict_row,
                "connect_timeout": 10,
            }
            if ipv4:
                kwargs["hostaddr"] = ipv4
            if user:
                kwargs["user"] = user
            if password:
                kwargs["password"] = password
            return psycopg.connect(**kwargs)
        # Fallback: let psycopg parse conninfo/DSN itself
        return psycopg.connect(dsn, row_factory=_pg_dict_row, connect_timeout=10)
    except Exception:
        # As a last resort, try the raw DSN without extra params
        return psycopg.connect(dsn, row_factory=_pg_dict_row)


def connect_db():
    return _connect_postgres() if using_postgres() else _connect_sqlite()


def init_db():
    # Postgres schema is managed via migrations. For Postgres, only ensure a default location exists.
    if using_postgres():
        try:
            con = connect_db(); cur = con.cursor()
            # Ensure a default location with id=1 exists (FK target for check_ins)
            cur.execute("SELECT 1 FROM locations WHERE id = %s" if using_postgres() else "SELECT 1 FROM locations WHERE id = ?", (1,))
            row = cur.fetchone()
            if not row:
                if using_postgres():
                    cur.execute(
                        "INSERT INTO locations (id, name, timezone) VALUES (1, %s, %s) ON CONFLICT (id) DO NOTHING",
                        ("Atlas Gym", "America/Los_Angeles"),
                    )
                else:
                    cur.execute("INSERT INTO locations(id, name, timezone) VALUES (1, ?, ?)", ("Atlas Gym", "America/Los_Angeles"))
                con.commit()
            if using_postgres():
                try:
                    cur.execute("ALTER TABLE public.members ADD COLUMN IF NOT EXISTS membership_tier TEXT")
                    con.commit()
                except Exception:
                    con.rollback()
        except Exception:
            # If schema/tables aren't there yet, ignore; migrations will create them.
            pass
        finally:
            try:
                con.close()
            except Exception:
                pass
        return
    con = connect_db()
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            timezone TEXT DEFAULT 'UTC'
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT,
            name TEXT NOT NULL,
            email_lower TEXT,
            phone_e164 TEXT,
            membership_tier TEXT,
            status TEXT CHECK (status IN ('active','inactive')) DEFAULT 'active',
            qr_token TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_members_email ON members(email_lower)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_members_phone ON members(phone_e164)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_members_external ON members(external_id)")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS check_ins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            location_id INTEGER DEFAULT 1,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            method TEXT CHECK (method IN ('QR','manual')) NOT NULL,
            source_device_id TEXT,
            status TEXT DEFAULT 'ok',
            FOREIGN KEY(member_id) REFERENCES members(id),
            FOREIGN KEY(location_id) REFERENCES locations(id)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_checkins_member_time ON check_ins(member_id, timestamp)")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            pin_salt TEXT NOT NULL,
            pin_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin'
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS product_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE,
            description TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_product_categories_name_lower
        ON product_categories(LOWER(name))
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER REFERENCES product_categories(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            slug TEXT UNIQUE,
            barcode TEXT,
            product_sku TEXT,
            product_kind TEXT NOT NULL DEFAULT 'retail',
            service_type TEXT,
            service_category TEXT,
            description TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            sell_online INTEGER NOT NULL DEFAULT 0,
            inventory_tracking INTEGER NOT NULL DEFAULT 0,
            default_price_type TEXT NOT NULL DEFAULT 'retail',
            our_cost_cents INTEGER,
            created_by TEXT,
            updated_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_products_active_kind
        ON products(product_kind, is_active)
        WHERE is_active = 1
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_products_sku
        ON products(product_sku)
        WHERE product_sku IS NOT NULL
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS product_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            price_type TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            billing_period TEXT,
            billing_interval INTEGER,
            benefit_quantity INTEGER,
            benefit_unit TEXT,
            benefit_window_quantity INTEGER,
            benefit_window_unit TEXT,
            is_unlimited INTEGER NOT NULL DEFAULT 0,
            stripe_price_id TEXT,
            is_default INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_product_price_unique
        ON product_prices(product_id, price_type)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_product_prices_active
        ON product_prices(product_id)
        WHERE is_active = 1
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT,
            member_id INTEGER REFERENCES members(id) ON DELETE SET NULL,
            guest_name TEXT,
            guest_email TEXT,
            guest_phone TEXT,
            staff_id INTEGER REFERENCES staff(id) ON DELETE SET NULL,
            order_type TEXT NOT NULL DEFAULT 'retail',
            status TEXT NOT NULL DEFAULT 'draft',
            currency TEXT NOT NULL DEFAULT 'USD',
            subtotal_cents INTEGER NOT NULL DEFAULT 0,
            tax_cents INTEGER NOT NULL DEFAULT 0,
            discount_cents INTEGER NOT NULL DEFAULT 0,
            tip_cents INTEGER NOT NULL DEFAULT 0,
            total_cents INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            checkout_session_id TEXT,
            payment_intent_id TEXT,
            payment_link_url TEXT,
            expires_at TIMESTAMP,
            paid_at TIMESTAMP,
            canceled_at TIMESTAMP,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_orders_number
        ON orders(order_number)
        WHERE order_number IS NOT NULL
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
            price_id INTEGER REFERENCES product_prices(id) ON DELETE SET NULL,
            description TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_amount_cents INTEGER NOT NULL,
            tax_cents INTEGER NOT NULL DEFAULT 0,
            discount_cents INTEGER NOT NULL DEFAULT 0,
            total_cents INTEGER NOT NULL,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_order_items_order
        ON order_items(order_id)
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS order_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            status TEXT NOT NULL,
            payment_method_type TEXT,
            stripe_payment_intent_id TEXT,
            stripe_checkout_session_id TEXT,
            stripe_charge_id TEXT,
            receipt_url TEXT,
            error_code TEXT,
            error_message TEXT,
            raw_payload TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_order_payments_intent
        ON order_payments(stripe_payment_intent_id)
        WHERE stripe_payment_intent_id IS NOT NULL
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_order_payments_order_status
        ON order_payments(order_id, status)
        """
    )

    cur.execute("SELECT COUNT(*) AS c FROM locations")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO locations(name, timezone) VALUES (?, ?)", ("Atlas Gym", "America/Los_Angeles"))

    con.commit()
    con.close()


def _pbkdf2_hash(pin: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 120_000)
    return dk.hex()


def create_or_rotate_staff_pin(name: str, pin: str):
    salt = secrets.token_bytes(16)
    pin_hash = _pbkdf2_hash(pin, salt)
    con = connect_db()
    cur = con.cursor()
    if using_postgres():
        cur.execute("INSERT INTO staff(name, pin_salt, pin_hash) VALUES (%s, %s, %s)", (name, salt.hex(), pin_hash))
    else:
        cur.execute("INSERT INTO staff(name, pin_salt, pin_hash) VALUES (?, ?, ?)", (name, salt.hex(), pin_hash))
    con.commit()
    con.close()


def verify_pin(pin: str) -> bool:
    con = connect_db()
    cur = con.cursor()
    cur.execute("SELECT pin_salt, pin_hash FROM staff ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    con.close()
    if not row:
        return False
    salt = bytes.fromhex(row["pin_salt"]) if isinstance(row["pin_salt"], str) else row["pin_salt"]
    expected = row["pin_hash"]
    computed = _pbkdf2_hash(pin, salt)
    return hmac.compare_digest(computed, expected)


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    return email.strip().lower()


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        return "+1" + digits
    if digits.startswith("1") and len(digits) == 11:
        return "+" + digits
    if phone.startswith("+"):
        return phone
    return "+" + digits if digits else None


def _coerce_json(value):
    if value is None or value == "":
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


def generate_order_number() -> str:
    now = datetime.now(timezone.utc)
    return f"ORD{now.strftime('%Y%m%d%H%M%S')}{secrets.token_hex(2).upper()}"


def _append_session_placeholder(base_url: str, order_number: str) -> str:
    if not base_url:
        return base_url
    url = base_url.strip()
    if "{ORDER_NUMBER}" in url:
        url = url.replace("{ORDER_NUMBER}", order_number)
    sep = '&' if '?' in url else '?'
    if "{CHECKOUT_SESSION_ID}" not in url:
        url = f"{url}{sep}session_id={{CHECKOUT_SESSION_ID}}"
        sep = '&'
    if "order=" not in url:
        url = f"{url}{sep}order={order_number}"
    return url


def _coalesce_row_value(row, key, index=0):
    if row is None:
        return None
    if using_postgres():
        return row.get(key)
    if hasattr(row, "keys") and key in row.keys():
        return row[key]
    if isinstance(row, (list, tuple)):
        try:
            return row[index]
        except Exception:
            return None
    return None


def _update_order_status(cur, order_id: int, new_status: str, *, paid_at: datetime | None = None,
                         checkout_session_id: str | None = None, payment_intent_id: str | None = None,
                         payment_link_url: str | None = None, canceled_at: datetime | None = None):
    if using_postgres():
        cur.execute(
            """
            UPDATE orders
               SET status = %s,
                   paid_at = COALESCE(%s, paid_at),
                   checkout_session_id = COALESCE(%s, checkout_session_id),
                   payment_intent_id = COALESCE(%s, payment_intent_id),
                   payment_link_url = COALESCE(%s, payment_link_url),
                   canceled_at = COALESCE(%s, canceled_at),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = %s
            """,
            (
                new_status,
                paid_at,
                checkout_session_id,
                payment_intent_id,
                payment_link_url,
                canceled_at,
                order_id,
            ),
        )
    else:
        cur.execute(
            """
            UPDATE orders
               SET status = ?,
                   paid_at = COALESCE(?, paid_at),
                   checkout_session_id = COALESCE(?, checkout_session_id),
                   payment_intent_id = COALESCE(?, payment_intent_id),
                   payment_link_url = COALESCE(?, payment_link_url),
                   canceled_at = COALESCE(?, canceled_at),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (
                new_status,
                paid_at.isoformat() if paid_at else None,
                checkout_session_id,
                payment_intent_id,
                payment_link_url,
                canceled_at.isoformat() if canceled_at else None,
                order_id,
            ),
        )


def _upsert_order_payment(cur, order_id: int, *, amount_cents: int | None, currency: str | None,
                          status: str, payment_method_type: str | None, payment_intent_id: str | None,
                          checkout_session_id: str | None, charge_id: str | None, receipt_url: str | None,
                          error_code: str | None, error_message: str | None, raw_payload: str | None):
    if not payment_intent_id:
        return
    if using_postgres():
        cur.execute("SELECT id FROM order_payments WHERE stripe_payment_intent_id = %s", (payment_intent_id,))
    else:
        cur.execute("SELECT id FROM order_payments WHERE stripe_payment_intent_id = ?", (payment_intent_id,))
    row = cur.fetchone()
    amount_cents = int(amount_cents or 0)
    currency = (currency or COMMERCE_DEFAULT_CURRENCY).upper()
    if row:
        payment_id = _coalesce_row_value(row, "id")
        if using_postgres():
            cur.execute(
                """
                UPDATE order_payments
                   SET amount_cents = %s,
                       currency = %s,
                       status = %s,
                       payment_method_type = %s,
                       stripe_checkout_session_id = COALESCE(%s, stripe_checkout_session_id),
                       stripe_charge_id = COALESCE(%s, stripe_charge_id),
                       receipt_url = COALESCE(%s, receipt_url),
                       error_code = %s,
                       error_message = %s,
                       raw_payload = %s,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = %s
                """,
                (
                    amount_cents,
                    currency,
                    status,
                    payment_method_type,
                    checkout_session_id,
                    charge_id,
                    receipt_url,
                    error_code,
                    error_message,
                    raw_payload,
                    payment_id,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE order_payments
                   SET amount_cents = ?,
                       currency = ?,
                       status = ?,
                       payment_method_type = ?,
                       stripe_checkout_session_id = COALESCE(?, stripe_checkout_session_id),
                       stripe_charge_id = COALESCE(?, stripe_charge_id),
                       receipt_url = COALESCE(?, receipt_url),
                       error_code = ?,
                       error_message = ?,
                       raw_payload = ?,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ?
                """,
                (
                    amount_cents,
                    currency,
                    status,
                    payment_method_type,
                    checkout_session_id,
                    charge_id,
                    receipt_url,
                    error_code,
                    error_message,
                    raw_payload,
                    payment_id,
                ),
            )
    else:
        if using_postgres():
            cur.execute(
                """
                INSERT INTO order_payments (
                    order_id, amount_cents, currency, status, payment_method_type,
                    stripe_payment_intent_id, stripe_checkout_session_id, stripe_charge_id, receipt_url,
                    error_code, error_message, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    order_id,
                    amount_cents,
                    currency,
                    status,
                    payment_method_type,
                    payment_intent_id,
                    checkout_session_id,
                    charge_id,
                    receipt_url,
                    error_code,
                    error_message,
                    raw_payload,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO order_payments (
                    order_id, amount_cents, currency, status, payment_method_type,
                    stripe_payment_intent_id, stripe_checkout_session_id, stripe_charge_id, receipt_url,
                    error_code, error_message, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    amount_cents,
                    currency,
                    status,
                    payment_method_type,
                    payment_intent_id,
                    checkout_session_id,
                    charge_id,
                    receipt_url,
                    error_code,
                    error_message,
                    raw_payload,
                ),
            )


def _handle_commerce_checkout_completed(session_obj: dict, raw_payload: str) -> bool:
    metadata = session_obj.get("metadata") or {}
    order_id_raw = metadata.get("order_id")
    order_number = metadata.get("order_number")
    session_id = session_obj.get("id")
    if not order_id_raw and not session_id and not order_number:
        return False
    order_id = None
    if order_id_raw:
        try:
            order_id = int(order_id_raw)
        except Exception:
            order_id = None
    con = connect_db(); cur = con.cursor()
    try:
        row = None
        if order_id is not None:
            if using_postgres():
                cur.execute("SELECT id, status FROM orders WHERE id = %s", (order_id,))
            else:
                cur.execute("SELECT id, status FROM orders WHERE id = ?", (order_id,))
            row = cur.fetchone()
        if row is None and session_id:
            if using_postgres():
                cur.execute("SELECT id, status FROM orders WHERE checkout_session_id = %s", (session_id,))
            else:
                cur.execute("SELECT id, status FROM orders WHERE checkout_session_id = ?", (session_id,))
            row = cur.fetchone()
        if row is None and order_number:
            if using_postgres():
                cur.execute("SELECT id, status FROM orders WHERE order_number = %s", (order_number,))
            else:
                cur.execute("SELECT id, status FROM orders WHERE order_number = ?", (order_number,))
            row = cur.fetchone()
        if row is None:
            return False
        resolved_order_id = _coalesce_row_value(row, "id")
        current_status = (_coalesce_row_value(row, "status") or "").lower()
        payment_status = (session_obj.get("payment_status") or "").lower()
        if payment_status in {"paid", "no_payment_required"}:
            new_status = "paid"
        elif payment_status == "unpaid":
            new_status = "awaiting_payment"
        else:
            new_status = current_status if current_status in {"paid", "refunded"} else "awaiting_payment"
        payment_intent_id = session_obj.get("payment_intent")
        checkout_url = session_obj.get("url")
        now_utc = datetime.now(timezone.utc)

        if new_status == "paid" and current_status != "paid":
            _update_order_status(
                cur,
                resolved_order_id,
                "paid",
                paid_at=now_utc,
                checkout_session_id=session_id,
                payment_intent_id=payment_intent_id,
                payment_link_url=checkout_url,
            )
        elif new_status == "awaiting_payment" and current_status in {"pending", "draft", "awaiting_payment"}:
            _update_order_status(
                cur,
                resolved_order_id,
                "awaiting_payment",
                checkout_session_id=session_id,
                payment_intent_id=payment_intent_id,
                payment_link_url=checkout_url,
            )

        if new_status == "paid" and payment_intent_id:
            amount_total = session_obj.get("amount_total") or 0
            currency = (session_obj.get("currency") or COMMERCE_DEFAULT_CURRENCY).upper()
            _upsert_order_payment(
                cur,
                resolved_order_id,
                amount_cents=amount_total,
                currency=currency,
                status="succeeded",
                payment_method_type=None,
                payment_intent_id=payment_intent_id,
                checkout_session_id=session_id,
                charge_id=None,
                receipt_url=None,
                error_code=None,
                error_message=None,
                raw_payload=raw_payload,
            )

        con.commit()
        return True
    finally:
        try:
            con.close()
        except Exception:
            pass


def _handle_commerce_checkout_expired(session_obj: dict) -> bool:
    metadata = session_obj.get("metadata") or {}
    order_id_raw = metadata.get("order_id")
    session_id = session_obj.get("id")
    if not order_id_raw and not session_id:
        return False
    order_id = None
    if order_id_raw:
        try:
            order_id = int(order_id_raw)
        except Exception:
            order_id = None
    con = connect_db(); cur = con.cursor()
    try:
        row = None
        if order_id is not None:
            if using_postgres():
                cur.execute("SELECT id FROM orders WHERE id = %s", (order_id,))
            else:
                cur.execute("SELECT id FROM orders WHERE id = ?", (order_id,))
            row = cur.fetchone()
        if row is None and session_id:
            if using_postgres():
                cur.execute("SELECT id FROM orders WHERE checkout_session_id = %s", (session_id,))
            else:
                cur.execute("SELECT id FROM orders WHERE checkout_session_id = ?", (session_id,))
            row = cur.fetchone()
        if row is None:
            return False
        resolved_order_id = _coalesce_row_value(row, "id")
        now_utc = datetime.now(timezone.utc)
        _update_order_status(
            cur,
            resolved_order_id,
            "expired",
            checkout_session_id=session_id,
            canceled_at=now_utc,
        )
        con.commit()
        return True
    finally:
        try:
            con.close()
        except Exception:
            pass


def _handle_commerce_payment_intent(intent_obj: dict, outcome: str, raw_payload: str) -> bool:
    payment_intent_id = intent_obj.get("id")
    if not payment_intent_id:
        return False
    metadata = intent_obj.get("metadata") or {}
    order_id_raw = metadata.get("order_id")
    order_id = None
    if order_id_raw:
        try:
            order_id = int(order_id_raw)
        except Exception:
            order_id = None
    con = connect_db(); cur = con.cursor()
    try:
        row = None
        if order_id is not None:
            if using_postgres():
                cur.execute("SELECT id, status FROM orders WHERE id = %s", (order_id,))
            else:
                cur.execute("SELECT id, status FROM orders WHERE id = ?", (order_id,))
            row = cur.fetchone()
        if row is None:
            if using_postgres():
                cur.execute("SELECT id, status FROM orders WHERE payment_intent_id = %s", (payment_intent_id,))
            else:
                cur.execute("SELECT id, status FROM orders WHERE payment_intent_id = ?", (payment_intent_id,))
            row = cur.fetchone()
        if row is None:
            return False
        resolved_order_id = _coalesce_row_value(row, "id")
        current_status = (_coalesce_row_value(row, "status") or "").lower()

        amount = intent_obj.get("amount_received") or intent_obj.get("amount") or 0
        currency = (intent_obj.get("currency") or COMMERCE_DEFAULT_CURRENCY).upper()
        payment_method_type = None
        pm_types = intent_obj.get("payment_method_types") or []
        if pm_types:
            payment_method_type = pm_types[0]
        charges = intent_obj.get("charges") or {}
        charge_id = None
        receipt_url = None
        if charges.get("data"):
            charge = charges["data"][0]
            charge_id = charge.get("id")
            receipt_url = charge.get("receipt_url")
            pmd = charge.get("payment_method_details") or {}
            if not payment_method_type:
                for key, val in pmd.items():
                    if isinstance(val, dict):
                        payment_method_type = key
                        break
        error_code = None
        error_message = None
        if outcome == "failed":
            last_error = intent_obj.get("last_payment_error") or {}
            error_code = last_error.get("code")
            error_message = last_error.get("message")

        now_utc = datetime.now(timezone.utc)
        if outcome == "succeeded" and current_status != "paid":
            _update_order_status(
                cur,
                resolved_order_id,
                "paid",
                paid_at=now_utc,
                payment_intent_id=payment_intent_id,
            )
        elif outcome == "failed" and current_status not in {"paid", "refunded"}:
            _update_order_status(
                cur,
                resolved_order_id,
                "failed",
                payment_intent_id=payment_intent_id,
                canceled_at=now_utc,
            )

        status_value = "succeeded" if outcome == "succeeded" else "failed"
        _upsert_order_payment(
            cur,
            resolved_order_id,
            amount_cents=amount,
            currency=currency,
            status=status_value,
            payment_method_type=payment_method_type,
            payment_intent_id=payment_intent_id,
            checkout_session_id=None,
            charge_id=charge_id,
            receipt_url=receipt_url,
            error_code=error_code,
            error_message=error_message,
            raw_payload=raw_payload,
        )

        con.commit()
        return True
    finally:
        try:
            con.close()
        except Exception:
            pass


def _handle_signup_checkout_session(session_obj: dict, stripe_module) -> bool:
    metadata = session_obj.get("metadata") or {}
    if metadata.get("order_id"):
        return False
    try:
        session_id = session_obj.get("id")
        stripe_api_key = os.environ.get("STRIPE_API_KEY")
        sess_full = session_obj
        if stripe_api_key:
            stripe_module.api_key = stripe_api_key
        if session_id and stripe_api_key:
            try:
                sess_full = stripe_module.checkout.Session.retrieve(
                    session_id,
                    expand=["line_items", "customer", "subscription"],
                )
            except Exception:
                sess_full = session_obj

        cust = sess_full.get("customer") if isinstance(sess_full.get("customer"), dict) else None
        customer_id = (cust.get("id") if cust else sess_full.get("customer"))
        customer_email = None
        if sess_full.get("customer_details"):
            customer_email = sess_full["customer_details"].get("email")
        if not customer_email:
            customer_email = sess_full.get("customer_email") or metadata.get("app_member_email")
        customer_name = metadata.get("app_member_name") or (cust.get("name") if cust else None)

        if not customer_email:
            return True

        con = connect_db(); cur = con.cursor()
        try:
            email_n = normalize_email(customer_email)
            name = customer_name or "Member"
            phone = (cust.get("phone") if cust else None)
            if using_postgres():
                cur.execute("SELECT id FROM members WHERE email_lower = %s LIMIT 1", (email_n,))
            else:
                cur.execute("SELECT id FROM members WHERE email_lower = ? LIMIT 1", (email_n,))
            row = cur.fetchone()
            if row:
                member_id = _coalesce_row_value(row, "id")
                if using_postgres():
                    cur.execute(
                        "UPDATE members SET name=%s, phone_e164=%s, stripe_customer_id=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                        (name, normalize_phone(phone), customer_id, member_id),
                    )
                else:
                    cur.execute(
                        "UPDATE members SET name=?, phone_e164=?, stripe_customer_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (name, normalize_phone(phone), customer_id, member_id),
                    )
            else:
                if using_postgres():
                    cur.execute(
                        "INSERT INTO members(name, email_lower, phone_e164, status, stripe_customer_id) VALUES (%s,%s,%s,'active',%s) RETURNING id",
                        (name, email_n, normalize_phone(phone), customer_id),
                    )
                    member_id = cur.fetchone()[0]
                else:
                    cur.execute(
                        "INSERT INTO members(name, email_lower, phone_e164, status, stripe_customer_id) VALUES (?,?,?,?,?)",
                        (name, email_n, normalize_phone(phone), 'active', customer_id),
                    )
                    member_id = cur.lastrowid

            if using_postgres():
                cur.execute("SELECT qr_token FROM members WHERE id=%s", (member_id,))
            else:
                cur.execute("SELECT qr_token FROM members WHERE id=?", (member_id,))
            tokrow = cur.fetchone()
            token = _coalesce_row_value(tokrow, "qr_token") if tokrow else None
            if not token:
                token = secrets.token_urlsafe(24)
                if using_postgres():
                    cur.execute("UPDATE members SET qr_token=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s", (token, member_id))
                else:
                    cur.execute("UPDATE members SET qr_token=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (token, member_id))

            con.commit()
        finally:
            try:
                con.close()
            except Exception:
                pass

        send_email(
            customer_email,
            "Your Atlas Gym Check-In Code",
            (
                f"Hi {name},\n\nYour membership is active. Open your QR code here:\n"
                f"{request.url_root.rstrip('/')}/member/qr?token={token}\n\nSee you at Atlas!\n\nGymSense — Your gym operations, simplified."
            ),
        )
        return True
    except Exception:
        return True

def _row_to_product(row) -> dict:
    if using_postgres():
        getter = row.get
    else:
        getter = row.__getitem__
    return {
        "id": getter("id"),
        "category_id": getter("category_id"),
        "name": getter("name"),
        "slug": getter("slug"),
        "barcode": getter("barcode"),
        "product_sku": getter("product_sku"),
        "product_kind": getter("product_kind"),
        "service_type": getter("service_type"),
        "service_category": getter("service_category"),
        "description": getter("description"),
        "default_price_type": getter("default_price_type"),
    }


def _row_to_price(row) -> dict:
    if using_postgres():
        getter = row.get
    else:
        getter = row.__getitem__
    return {
        "id": getter("id"),
        "product_id": getter("product_id"),
        "price_type": getter("price_type"),
        "amount_cents": getter("amount_cents"),
        "currency": getter("currency"),
        "billing_period": getter("billing_period"),
        "billing_interval": getter("billing_interval"),
        "benefit_quantity": getter("benefit_quantity"),
        "benefit_unit": getter("benefit_unit"),
        "benefit_window_quantity": getter("benefit_window_quantity"),
        "benefit_window_unit": getter("benefit_window_unit"),
        "is_unlimited": bool(getter("is_unlimited")),
        "stripe_price_id": getter("stripe_price_id"),
        "is_default": bool(getter("is_default")),
        "is_active": bool(getter("is_active")),
        "metadata": _coerce_json(getter("metadata")),
    }


def load_product_and_price(cur, product_id: int, price_type: str | None) -> tuple[dict, dict]:
    if using_postgres():
        cur.execute(
            """
            SELECT id, category_id, name, slug, barcode, product_sku, product_kind,
                   service_type, service_category, description, default_price_type
            FROM products
            WHERE id = %s
            """,
            (product_id,),
        )
    else:
        cur.execute(
            """
            SELECT id, category_id, name, slug, barcode, product_sku, product_kind,
                   service_type, service_category, description, default_price_type
            FROM products
            WHERE id = ?
            """,
            (product_id,),
        )
    product_row = cur.fetchone()
    if not product_row:
        return None, None
    product = _row_to_product(product_row)
    resolved_price_type = price_type or product.get("default_price_type")

    if using_postgres():
        cur.execute(
            """
            SELECT id, product_id, price_type, amount_cents, currency, billing_period,
                   billing_interval, benefit_quantity, benefit_unit, benefit_window_quantity,
                   benefit_window_unit, is_unlimited, stripe_price_id, is_default,
                   is_active, metadata
            FROM product_prices
            WHERE product_id = %s AND price_type = %s AND is_active = TRUE
            """,
            (product_id, resolved_price_type),
        )
    else:
        cur.execute(
            """
            SELECT id, product_id, price_type, amount_cents, currency, billing_period,
                   billing_interval, benefit_quantity, benefit_unit, benefit_window_quantity,
                   benefit_window_unit, is_unlimited, stripe_price_id, is_default,
                   is_active, metadata
            FROM product_prices
            WHERE product_id = ? AND price_type = ? AND is_active = 1
            """,
            (product_id, resolved_price_type),
        )
    price_row = cur.fetchone()
    if not price_row:
        return product, None
    price = _row_to_price(price_row)
    return product, price


def fetch_product_catalog(include_inactive: bool = False) -> dict:
    con = connect_db()
    cur = con.cursor()
    try:
        categories: list[dict] = []
        category_map: dict[int, dict] = {}
        if using_postgres():
            cur.execute(
                """
                SELECT id, name, slug, description, sort_order
                FROM product_categories
                ORDER BY sort_order ASC, name ASC
                """
            )
            rows = cur.fetchall()
            for row in rows:
                cat = {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "slug": row.get("slug"),
                    "description": row.get("description"),
                    "sort_order": row.get("sort_order") or 0,
                    "products": [],
                }
                categories.append(cat)
                category_map[cat["id"]] = cat
        else:
            cur.execute(
                """
                SELECT id, name, slug, description, sort_order
                FROM product_categories
                ORDER BY sort_order ASC, name ASC
                """
            )
            for row in cur.fetchall():
                cat = {
                    "id": row["id"],
                    "name": row["name"],
                    "slug": row["slug"],
                    "description": row["description"],
                    "sort_order": row["sort_order"] or 0,
                    "products": [],
                }
                categories.append(cat)
                category_map[cat["id"]] = cat

        products: list[dict] = []
        product_query = (
            """
            SELECT id, category_id, name, slug, barcode, product_sku, product_kind,
                   service_type, service_category, description, is_active,
                   sell_online, inventory_tracking, default_price_type, our_cost_cents,
                   created_at, updated_at
            FROM products
            """
        )
        product_params: list = []
        if using_postgres():
            if not include_inactive:
                product_query += " WHERE is_active = %s"
                product_params.append(True)
            product_query += " ORDER BY name ASC"
            cur.execute(product_query, tuple(product_params))
        else:
            if not include_inactive:
                product_query += " WHERE is_active = 1"
            product_query += " ORDER BY name ASC"
            cur.execute(product_query)
        product_rows = cur.fetchall()
        product_map: dict[int, dict] = {}
        for row in product_rows:
            if using_postgres():
                pid = row.get("id")
                item = {
                    "id": pid,
                    "category_id": row.get("category_id"),
                    "name": row.get("name"),
                    "slug": row.get("slug"),
                    "barcode": row.get("barcode"),
                    "product_sku": row.get("product_sku"),
                    "product_kind": row.get("product_kind"),
                    "service_type": row.get("service_type"),
                    "service_category": row.get("service_category"),
                    "description": row.get("description"),
                    "is_active": bool(row.get("is_active")),
                    "sell_online": bool(row.get("sell_online")),
                    "inventory_tracking": bool(row.get("inventory_tracking")),
                    "default_price_type": row.get("default_price_type"),
                    "our_cost_cents": row.get("our_cost_cents"),
                    "prices": [],
                }
            else:
                pid = row["id"]
                item = {
                    "id": pid,
                    "category_id": row["category_id"],
                    "name": row["name"],
                    "slug": row["slug"],
                    "barcode": row["barcode"],
                    "product_sku": row["product_sku"],
                    "product_kind": row["product_kind"],
                    "service_type": row["service_type"],
                    "service_category": row["service_category"],
                    "description": row["description"],
                    "is_active": bool(row["is_active"]),
                    "sell_online": bool(row["sell_online"]),
                    "inventory_tracking": bool(row["inventory_tracking"]),
                    "default_price_type": row["default_price_type"],
                    "our_cost_cents": row["our_cost_cents"],
                    "prices": [],
                }
            products.append(item)
            product_map[pid] = item

        if product_map:
            price_query = (
                """
                SELECT id, product_id, price_type, amount_cents, currency, billing_period,
                       billing_interval, benefit_quantity, benefit_unit,
                       benefit_window_quantity, benefit_window_unit, is_unlimited,
                       stripe_price_id, is_default, is_active, metadata
                FROM product_prices
                WHERE product_id = ANY(%s)
                ORDER BY product_id, price_type
                """
                if using_postgres()
                else
                """
                SELECT id, product_id, price_type, amount_cents, currency, billing_period,
                       billing_interval, benefit_quantity, benefit_unit,
                       benefit_window_quantity, benefit_window_unit, is_unlimited,
                       stripe_price_id, is_default, is_active, metadata
                FROM product_prices
                WHERE product_id IN (
                """
            )
            if using_postgres():
                cur.execute(price_query, (list(product_map.keys()),))
            else:
                placeholders = ",".join("?" for _ in product_map)
                cur.execute(price_query + placeholders + ") ORDER BY product_id, price_type", tuple(product_map.keys()))
            for row in cur.fetchall():
                if using_postgres():
                    pid = row.get("product_id")
                    target = product_map.get(pid)
                    if not target:
                        continue
                    price = {
                        "id": row.get("id"),
                        "price_type": row.get("price_type"),
                        "amount_cents": row.get("amount_cents"),
                        "currency": row.get("currency"),
                        "billing_period": row.get("billing_period"),
                        "billing_interval": row.get("billing_interval"),
                        "benefit_quantity": row.get("benefit_quantity"),
                        "benefit_unit": row.get("benefit_unit"),
                        "benefit_window_quantity": row.get("benefit_window_quantity"),
                        "benefit_window_unit": row.get("benefit_window_unit"),
                        "is_unlimited": bool(row.get("is_unlimited")),
                        "stripe_price_id": row.get("stripe_price_id"),
                        "is_default": bool(row.get("is_default")),
                        "is_active": bool(row.get("is_active")),
                        "metadata": _coerce_json(row.get("metadata")),
                    }
                else:
                    pid = row["product_id"]
                    target = product_map.get(pid)
                    if not target:
                        continue
                    price = {
                        "id": row["id"],
                        "price_type": row["price_type"],
                        "amount_cents": row["amount_cents"],
                        "currency": row["currency"],
                        "billing_period": row["billing_period"],
                        "billing_interval": row["billing_interval"],
                        "benefit_quantity": row["benefit_quantity"],
                        "benefit_unit": row["benefit_unit"],
                        "benefit_window_quantity": row["benefit_window_quantity"],
                        "benefit_window_unit": row["benefit_window_unit"],
                        "is_unlimited": bool(row["is_unlimited"]),
                        "stripe_price_id": row["stripe_price_id"],
                        "is_default": bool(row["is_default"]),
                        "is_active": bool(row["is_active"]),
                        "metadata": _coerce_json(row["metadata"]),
                    }
                target.setdefault("prices", []).append(price)

        uncategorized: list[dict] = []
        for item in products:
            cat_id = item.get("category_id")
            if cat_id and cat_id in category_map:
                category_map[cat_id]["products"].append(item)
            else:
                uncategorized.append(item)

        ordered_categories = [c for c in categories if c.get("products")]
        if uncategorized:
            ordered_categories.append({
                "id": None,
                "name": "Uncategorized",
                "slug": None,
                "description": None,
                "sort_order": 999,
                "products": uncategorized,
            })

        return {"categories": ordered_categories, "products": products}
    finally:
        con.close()
def ensure_qr_token(member) -> str:
    token = member["qr_token"]
    if token:
        return token
    new_token = secrets.token_urlsafe(24)
    con = connect_db()
    cur = con.cursor()
    if using_postgres():
        cur.execute("UPDATE members SET qr_token = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (new_token, member["id"]))
    else:
        cur.execute("UPDATE members SET qr_token = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_token, member["id"]))
    con.commit()
    con.close()
    return new_token


def generate_qr_png(data: str, box_size: int = 8, border: int = 2) -> bytes:
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        return b''


def upsert_member(cur, external_id: str | None, name: str, email: str | None, phone: str | None, membership_tier: str | None, status: str):
    email_n = normalize_email(email)
    phone_n = normalize_phone(phone)
    if using_postgres():
        cur.execute(
            """
            SELECT id FROM members
            WHERE (
                (external_id IS NOT NULL AND external_id = %s)
                OR (email_lower IS NOT NULL AND email_lower = %s)
                OR (phone_e164 IS NOT NULL AND phone_e164 = %s)
            )
            ORDER BY
                CASE WHEN external_id = %s THEN 0 ELSE 1 END,
                CASE WHEN email_lower = %s THEN 0 ELSE 1 END,
                CASE WHEN phone_e164 = %s THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (external_id, email_n, phone_n, external_id, email_n, phone_n),
        )
    else:
        cur.execute(
            """
            SELECT id FROM members
            WHERE (
                (external_id IS NOT NULL AND external_id = ?)
                OR (email_lower IS NOT NULL AND email_lower = ?)
                OR (phone_e164 IS NOT NULL AND phone_e164 = ?)
            )
            ORDER BY
                CASE WHEN external_id = ? THEN 0 ELSE 1 END,
                CASE WHEN email_lower = ? THEN 0 ELSE 1 END,
                CASE WHEN phone_e164 = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (external_id, email_n, phone_n, external_id, email_n, phone_n),
        )
    existing = cur.fetchone()
    if existing:
        # Resolve existing id across backends
        existing_id = existing["id"] if using_postgres() else existing[0]
        if using_postgres():
            cur.execute(
                """
                UPDATE members
                SET name = %s, email_lower = %s, phone_e164 = %s, membership_tier = %s, status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (name, email_n, phone_n, membership_tier, status, existing_id),
            )
        else:
            cur.execute(
                """
                UPDATE members
                SET name = ?, email_lower = ?, phone_e164 = ?, membership_tier = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (name, email_n, phone_n, membership_tier, status, existing_id),
            )
        return existing_id
    else:
        if using_postgres():
            cur.execute(
                """
                INSERT INTO members(external_id, name, email_lower, phone_e164, membership_tier, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (external_id, name, email_n, phone_n, membership_tier, status),
            )
            rid = cur.fetchone()[0]
            return rid
        else:
            cur.execute(
                """
                INSERT INTO members(external_id, name, email_lower, phone_e164, membership_tier, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (external_id, name, email_n, phone_n, membership_tier, status),
            )
            return cur.lastrowid


def send_email(to_email: str, subject: str, body: str, body_html: str | None = None, inline_images: list | None = None) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    from_raw = os.environ.get("SMTP_FROM", user or "noreply@example.com")
    from_name = os.environ.get("SMTP_FROM_NAME")
    if not from_name and isinstance(from_raw, str) and from_raw.lower().endswith("@gymsense.io"):
        from_name = "GymSense"
    from_email = formataddr((from_name, from_raw)) if from_name else from_raw
    if not host or not user or not password:
        print(f"[DEV] Would send email to {to_email}: {subject}\n{body}")
        return True
    try:
        if body_html:
            # Build a related container so we can embed images by CID
            root = MIMEMultipart('related')
            root['Subject'] = subject
            root['From'] = from_email
            root['To'] = to_email
            alt = MIMEMultipart('alternative')
            root.attach(alt)
            alt.attach(MIMEText(body, 'plain'))
            alt.attach(MIMEText(body_html, 'html'))
            if inline_images:
                for (filename, content, mimetype, cid) in inline_images:
                    try:
                        img = MIMEImage(content, _subtype=mimetype.split('/')[-1])
                        img.add_header('Content-ID', cid)
                        img.add_header('Content-Disposition', 'inline', filename=filename)
                        root.attach(img)
                    except Exception:
                        pass
            msg = root
        else:
            msg = MIMEText(body, "plain")
            msg["Subject"] = subject
            msg["From"] = from_email
            msg["To"] = to_email
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True
    except Exception as e:
        print("Email send failed:", e)
        return False


def _map_csv_row(row: dict) -> dict | None:
    external_id = (row.get("Id") or row.get("Member ID") or row.get("ClientId") or row.get("Client ID") or "").strip() or None
    name = (row.get("Name") or row.get("Client Name") or (row.get("First Name", "").strip() + " " + row.get("Last Name", "").strip())).strip()
    email = (row.get("Email") or row.get("Email Address") or row.get("E-mail") or "").strip() or None
    phone = (row.get("Phone") or row.get("Mobile Phone") or row.get("Home Phone") or "").strip() or None
    tier = (row.get("Membership Tier") or row.get("Contract Name") or row.get("Client Type") or "").strip() or None
    status_raw = (row.get("Status") or row.get("Active") or row.get("Client Status") or "active").strip().lower()
    status = "active" if status_raw in ("active", "true", "1", "yes") else "inactive"
    if not name:
        return None
    return {"external_id": external_id, "name": name, "email": email, "phone": phone, "tier": tier, "status": status}


def create_app():
    init_db()
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.secret_key = SESSION_SECRET

    @app.get("/")
    def root():
        return redirect(url_for("kiosk"))

    @app.get("/healthz")
    def healthz():
        return "ok", 200

    @app.get("/kiosk")
    def kiosk():
        return render_template("checkin/kiosk.html", location_id=1)

    @app.get("/admin/login")
    def admin_login():
        return render_template("checkin/admin_login.html")

    @app.post("/admin/login")
    def admin_login_post():
        pin = request.form.get("pin", "")
        if verify_pin(pin):
            session["admin"] = True
            nxt = request.args.get("next") or ""
            if isinstance(nxt, str) and nxt.startswith("/"):
                return redirect(nxt)
            return redirect(url_for("admin_dashboard"))
        return render_template("checkin/admin_login.html", error="Invalid PIN")

    def require_admin():
        if not session.get("admin"):
            abort(401)

    @app.get("/admin/logout")
    def admin_logout():
        session.pop("admin", None)
        return redirect(url_for("admin_login"))

    # Staff portal login shortcut (reuses /admin/login template/handler)
    @app.get("/staff/login")
    def staff_login():
        return redirect(url_for("admin_login", next="/staff"))

    @app.get("/admin")
    def admin_dashboard():
        if not session.get("admin"):
            return redirect(url_for("admin_login", next="/admin"))
        return redirect(url_for("staff_dashboard"))

    @app.get("/staff")
    def staff_dashboard():
        if not session.get("admin"):
            return redirect(url_for("admin_login", next="/staff"))
        return render_template("checkin/staff_dashboard.html", datetime=datetime)

    @app.get("/api/commerce/catalog")
    def api_commerce_catalog():
        if not COMMERCE_ENABLED:
            return jsonify({"ok": False, "error": "Commerce disabled"}), 404
        if not session.get("admin"):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        include_inactive = request.args.get("include_inactive", "0").strip().lower() in {"1", "true", "yes", "on"}
        catalog = fetch_product_catalog(include_inactive=include_inactive)
        catalog.update({"ok": True, "currency": COMMERCE_DEFAULT_CURRENCY})
        return jsonify(catalog)

    @app.post("/api/commerce/orders")
    def api_commerce_create_order():
        if not COMMERCE_ENABLED:
            return jsonify({"ok": False, "error": "Commerce disabled"}), 404
        if not session.get("admin"):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

        payload = request.get_json(silent=True) or {}
        items_payload = payload.get("items") or []
        if not items_payload:
            return jsonify({"ok": False, "error": "No items provided"}), 400

        order_type = (payload.get("order_type") or "retail").strip()
        if order_type not in COMMERCE_ORDER_TYPES:
            return jsonify({"ok": False, "error": f"Unsupported order_type '{order_type}'"}), 400

        currency = (payload.get("currency") or COMMERCE_DEFAULT_CURRENCY).upper()
        if currency != COMMERCE_DEFAULT_CURRENCY:
            return jsonify({"ok": False, "error": f"Unsupported currency '{currency}'"}), 400

        member_id = payload.get("member_id")
        guest_name = (payload.get("guest_name") or "").strip() or None
        guest_email = normalize_email(payload.get("guest_email"))
        guest_phone = normalize_phone(payload.get("guest_phone"))
        notes = (payload.get("notes") or "").strip() or None
        metadata_value = payload.get("metadata")

        try:
            expires_minutes = int(payload.get("expires_in_minutes") or 30)
        except Exception:
            return jsonify({"ok": False, "error": "Invalid expires_in_minutes"}), 400
        if expires_minutes <= 0:
            expires_minutes = 30
        expires_at_dt = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)

        con = connect_db()
        cur = con.cursor()
        try:
            if member_id:
                if using_postgres():
                    cur.execute("SELECT id FROM members WHERE id = %s", (member_id,))
                else:
                    cur.execute("SELECT id FROM members WHERE id = ?", (member_id,))
                if not cur.fetchone():
                    return jsonify({"ok": False, "error": "Member not found"}), 404

            stripe_api_key = os.environ.get("STRIPE_API_KEY")
            if not stripe_api_key:
                return jsonify({"ok": False, "error": "Stripe not configured"}), 501
            try:
                import stripe
            except Exception as exc:
                return jsonify({"ok": False, "error": f"Stripe SDK not available: {exc}"}), 500

            stripe.api_key = stripe_api_key

            prepared_items = []
            subtotal_cents = 0
            stripe_line_items: list[dict] = []
            has_subscription = False
            has_one_time = False
            for idx, raw_item in enumerate(items_payload):
                product_id = raw_item.get("product_id")
                if not product_id:
                    return jsonify({"ok": False, "error": f"Item {idx + 1}: missing product_id"}), 400
                price_type = raw_item.get("price_type")
                quantity_raw = raw_item.get("quantity", 1)
                try:
                    quantity = int(quantity_raw)
                except Exception:
                    return jsonify({"ok": False, "error": f"Item {idx + 1}: invalid quantity"}), 400
                if quantity <= 0:
                    return jsonify({"ok": False, "error": f"Item {idx + 1}: quantity must be > 0"}), 400

                product, price = load_product_and_price(cur, product_id, price_type)
                if not product:
                    return jsonify({"ok": False, "error": f"Item {idx + 1}: product not found"}), 404
                if not price:
                    return jsonify({"ok": False, "error": f"Item {idx + 1}: price not available"}), 400

                line_total = int(price["amount_cents"] or 0) * quantity
                subtotal_cents += line_total
                stripe_price_id = price.get("stripe_price_id")
                if not stripe_price_id:
                    return jsonify({"ok": False, "error": f"Item {idx + 1}: Stripe price not configured"}), 400

                stripe_line_items.append({"price": stripe_price_id, "quantity": quantity})

                if price.get("billing_period"):
                    has_subscription = True
                else:
                    has_one_time = True

                prepared_items.append(
                    {
                        "product": product,
                        "price": price,
                        "quantity": quantity,
                        "line_total": line_total,
                    }
                )

            if has_subscription and has_one_time:
                return jsonify({"ok": False, "error": "Cannot mix subscription and one-time items in a single order"}), 400

            total_cents = subtotal_cents  # taxes/discounts applied later
            order_number = payload.get("order_number") or generate_order_number()
            status = "pending"

            metadata_pg = metadata_value if metadata_value is not None else None
            metadata_sqlite = json.dumps(metadata_value) if metadata_value is not None else None
            expires_at_value = expires_at_dt if using_postgres() else expires_at_dt.isoformat()

            if using_postgres():
                cur.execute(
                    """
                    INSERT INTO orders
                        (order_number, member_id, guest_name, guest_email, guest_phone, staff_id,
                         order_type, status, currency, subtotal_cents, tax_cents, discount_cents,
                         tip_cents, total_cents, notes, checkout_session_id, payment_intent_id,
                         payment_link_url, expires_at, metadata)
                    VALUES
                        (%s, %s, %s, %s, %s, %s,
                         %s, %s, %s, %s, %s, %s,
                         %s, %s, %s, NULL, NULL,
                         NULL, %s, %s)
                    RETURNING id
                    """,
                    (
                        order_number,
                        member_id,
                        guest_name,
                        guest_email,
                        guest_phone,
                        None,
                        order_type,
                        status,
                        currency,
                        subtotal_cents,
                        0,
                        0,
                        0,
                        total_cents,
                        notes,
                        expires_at_value,
                        metadata_pg,
                    ),
                )
                order_id = cur.fetchone()[0]
            else:
                cur.execute(
                    """
                    INSERT INTO orders
                        (order_number, member_id, guest_name, guest_email, guest_phone, staff_id,
                         order_type, status, currency, subtotal_cents, tax_cents, discount_cents,
                         tip_cents, total_cents, notes, checkout_session_id, payment_intent_id,
                         payment_link_url, expires_at, metadata)
                    VALUES
                        (?, ?, ?, ?, ?, ?,
                         ?, ?, ?, ?, ?, ?,
                         ?, ?, ?, NULL, NULL,
                         NULL, ?, ?)
                    """,
                    (
                        order_number,
                        member_id,
                        guest_name,
                        guest_email,
                        guest_phone,
                        None,
                        order_type,
                        status,
                        currency,
                        subtotal_cents,
                        0,
                        0,
                        0,
                        total_cents,
                        notes,
                        expires_at_value,
                        metadata_sqlite,
                    ),
                )
                order_id = cur.lastrowid

            for item in prepared_items:
                product = item["product"]
                price = item["price"]
                quantity = item["quantity"]
                line_total = item["line_total"]
                metadata_line_pg = {"price_type": price["price_type"]}
                metadata_line_sqlite = json.dumps(metadata_line_pg)

                if using_postgres():
                    cur.execute(
                        """
                        INSERT INTO order_items
                            (order_id, product_id, price_id, description, quantity,
                             unit_amount_cents, tax_cents, discount_cents, total_cents, metadata)
                        VALUES
                            (%s, %s, %s, %s, %s,
                             %s, %s, %s, %s, %s)
                        """,
                        (
                            order_id,
                            product["id"],
                            price["id"],
                            product["name"],
                            quantity,
                            price["amount_cents"],
                            0,
                            0,
                            line_total,
                            metadata_line_pg,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO order_items
                            (order_id, product_id, price_id, description, quantity,
                             unit_amount_cents, tax_cents, discount_cents, total_cents, metadata)
                        VALUES
                            (?, ?, ?, ?, ?,
                             ?, ?, ?, ?, ?)
                        """,
                        (
                            order_id,
                            product["id"],
                            price["id"],
                            product["name"],
                            quantity,
                            price["amount_cents"],
                            0,
                            0,
                            line_total,
                            metadata_line_sqlite,
                        ),
                    )

            # Build Stripe Checkout Session
            mode = "subscription" if has_subscription else "payment"

            success_url_env = os.environ.get("COMMERCE_CHECKOUT_SUCCESS_URL") or os.environ.get("STRIPE_CHECKOUT_SUCCESS_URL")
            cancel_url_env = os.environ.get("COMMERCE_CHECKOUT_CANCEL_URL") or os.environ.get("STRIPE_CHECKOUT_CANCEL_URL")
            default_success = request.url_root.rstrip('/') + "/staff/checkout/success"
            default_cancel = request.url_root.rstrip('/') + "/staff/checkout/cancel"
            success_url = _append_session_placeholder(success_url_env or default_success, order_number)
            cancel_url = (cancel_url_env or default_cancel).strip()
            if "{ORDER_NUMBER}" in cancel_url:
                cancel_url = cancel_url.replace("{ORDER_NUMBER}", order_number)
            if cancel_url:
                sep_cancel = '&' if '?' in cancel_url else '?'
                if "order=" not in cancel_url:
                    cancel_url = f"{cancel_url}{sep_cancel}order={order_number}"

            customer_email = guest_email
            if not customer_email and member_id:
                email_query = (
                    "SELECT email_lower FROM members WHERE id = %s"
                    if using_postgres()
                    else "SELECT email_lower FROM members WHERE id = ?"
                )
                cur.execute(email_query, (member_id,))
                member_row = cur.fetchone()
                if member_row:
                    customer_email = member_row[0] if not using_postgres() else member_row.get("email_lower")

            session_kwargs = {
                "mode": mode,
                "line_items": stripe_line_items,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "metadata": {
                    "order_id": str(order_id),
                    "order_number": order_number,
                    "order_type": order_type,
                },
            }

            if customer_email:
                session_kwargs["customer_email"] = customer_email

            metadata_payload = {
                "order_id": str(order_id),
                "order_number": order_number,
                "order_type": order_type,
            }

            if mode == "payment":
                session_kwargs["payment_intent_data"] = {"metadata": metadata_payload}
            else:
                session_kwargs["subscription_data"] = {"metadata": metadata_payload}

            try:
                checkout_session = stripe.checkout.Session.create(**session_kwargs)
            except Exception as err:
                con.rollback()
                return jsonify({"ok": False, "error": f"Stripe checkout creation failed: {err}"}), 502

            payment_intent_id = checkout_session.payment_intent if mode == "payment" else None
            checkout_session_id = checkout_session.id
            checkout_url = checkout_session.url

            if using_postgres():
                cur.execute(
                    """
                    UPDATE orders
                    SET status = %s,
                        checkout_session_id = %s,
                        payment_intent_id = %s,
                        payment_link_url = %s
                    WHERE id = %s
                    """,
                    (
                        "awaiting_payment",
                        checkout_session_id,
                        payment_intent_id,
                        checkout_url,
                        order_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE orders
                    SET status = ?,
                        checkout_session_id = ?,
                        payment_intent_id = ?,
                        payment_link_url = ?
                    WHERE id = ?
                    """,
                    (
                        "awaiting_payment",
                        checkout_session_id,
                        payment_intent_id,
                        checkout_url,
                        order_id,
                    ),
                )

            con.commit()

            return jsonify(
                {
                    "ok": True,
                    "order": {
                        "id": order_id,
                        "order_number": order_number,
                        "status": "awaiting_payment",
                        "currency": currency,
                        "subtotal_cents": subtotal_cents,
                        "tax_cents": 0,
                        "discount_cents": 0,
                        "tip_cents": 0,
                        "total_cents": total_cents,
                        "expires_at": expires_at_dt.isoformat(),
                        "checkout_url": checkout_url,
                        "checkout_session_id": checkout_session_id,
                        "items": [
                            {
                                "product_id": item["product"]["id"],
                                "product_name": item["product"]["name"],
                                "price_type": item["price"]["price_type"],
                                "quantity": item["quantity"],
                                "unit_amount_cents": item["price"]["amount_cents"],
                                "total_cents": item["line_total"],
                            }
                            for item in prepared_items
                        ],
                    },
                }
            )
        except Exception as e:
            try:
                import traceback
                print("[commerce] order creation failed:", e)
                traceback.print_exc()
            except Exception:
                print("[commerce] order creation failed (no traceback):", e)
            try:
                con.rollback()
            except Exception:
                pass
            return jsonify({"ok": False, "error": str(e)}), 500
        finally:
            try:
                con.close()
            except Exception:
                pass

    # --- Staff-assisted Signup (MVP scaffold) ---
    def require_staff_signup_auth():
        if not STAFF_SIGNUP_ENABLED:
            abort(404)
        if not session.get("staff_signup_auth"):
            return redirect(url_for("staff_signup_login"))
        return None

    @app.get("/staff/signup/login")
    def staff_signup_login():
        if not STAFF_SIGNUP_ENABLED:
            abort(404)
        return render_template("checkin/staff_signup_login.html")

    @app.post("/staff/signup/login")
    def staff_signup_login_post():
        if not STAFF_SIGNUP_ENABLED:
            abort(404)
        pw = request.form.get("password", "")
        if STAFF_SIGNUP_PASSWORD and pw == STAFF_SIGNUP_PASSWORD:
            session["staff_signup_auth"] = True
            return redirect(url_for("staff_signup"))
        err = "Incorrect password" if STAFF_SIGNUP_PASSWORD else "Not configured (set STAFF_SIGNUP_PASSWORD)"
        return render_template("checkin/staff_signup_login.html", error=err)

    @app.get("/staff/signup")
    def staff_signup():
        # separate from PIN; requires STAFF_SIGNUP_PASSWORD
        redir = require_staff_signup_auth()
        if redir:
            return redir
        tiers = [
            {"id": os.environ.get("STRIPE_PRICE_ESSENTIAL"), "label": "Essential"},
            {"id": os.environ.get("STRIPE_PRICE_ELEVATED"), "label": "Elevated"},
            {"id": os.environ.get("STRIPE_PRICE_ELITE"), "label": "Elite"},
        ]
        return render_template("checkin/staff_signup.html", tiers=tiers)

    @app.post("/api/signup/checkout_session")
    def api_signup_checkout_session():
        # Minimal validation; Stripe integration optional if not configured
        if not STAFF_SIGNUP_ENABLED:
            return jsonify({"ok": False, "error": "Signup disabled"}), 404
        redir = require_staff_signup_auth()
        if redir:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        email = (payload.get("email") or "").strip()
        tier_price = (payload.get("price_id") or "").strip()
        phone = (payload.get("phone") or "").strip()
        birthday = (payload.get("birthday") or "").strip()
        address = (payload.get("address") or "").strip()
        if not name or not email or not tier_price:
            return jsonify({"ok": False, "error": "Missing required fields"}), 400
        api_key = os.environ.get("STRIPE_API_KEY")
        success_url = os.environ.get("JOIN_SUCCESS_URL", request.url_root.rstrip("/") + "/join/success")
        cancel_url = os.environ.get("JOIN_CANCEL_URL", request.url_root.rstrip("/") + "/join/cancel")
        if not api_key:
            return jsonify({"ok": False, "error": "Stripe not configured"}), 501
        try:
            import stripe
            stripe.api_key = api_key
            # Create or reuse Customer
            customer = stripe.Customer.create(
                name=name,
                email=email,
                phone=phone or None,
                address={"line1": address} if address else None,
                metadata={"birthday": birthday} if birthday else None,
            )
            session_obj = stripe.checkout.Session.create(
                mode="subscription",
                customer=customer.id,
                line_items=[{"price": tier_price, "quantity": 1}],
                success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=cancel_url,
                locale="en",
                metadata={"app_member_email": email, "app_member_name": name},
            )
            return jsonify({"ok": True, "url": session_obj.url})
        except Exception as e:
            return jsonify({"ok": False, "error": f"Stripe error: {str(e)}"}), 500

    @app.post("/webhooks/stripe")
    def stripe_webhook():
        if not (STAFF_SIGNUP_ENABLED or COMMERCE_ENABLED):
            return ("OK", 200)

        payload = request.get_data()
        raw_body = payload.decode("utf-8", errors="ignore")
        sig = request.headers.get("Stripe-Signature", "")
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

        try:
            import stripe
            if not secret:
                return ("OK", 200)
            event = stripe.Webhook.construct_event(payload, sig, secret)
        except Exception:
            return ("Bad signature", 400)

        stripe_api_key = os.environ.get("STRIPE_API_KEY")
        if stripe_api_key:
            try:
                import stripe
                stripe.api_key = stripe_api_key
            except Exception:
                pass

        event_type = event.get("type", "")
        obj = (event.get("data") or {}).get("object") or {}
        handled = False

        if COMMERCE_ENABLED:
            if event_type == "checkout.session.completed":
                handled = _handle_commerce_checkout_completed(obj, raw_body)
            elif event_type == "checkout.session.expired":
                handled = _handle_commerce_checkout_expired(obj)
            elif event_type == "payment_intent.succeeded":
                handled = _handle_commerce_payment_intent(obj, "succeeded", raw_body)
            elif event_type == "payment_intent.payment_failed":
                handled = _handle_commerce_payment_intent(obj, "failed", raw_body)

        if not handled and STAFF_SIGNUP_ENABLED and event_type == "checkout.session.completed":
            try:
                import stripe
                _handle_signup_checkout_session(obj, stripe)
            except Exception:
                pass

        return ("OK", 200)

    # --- Signup success/cancel placeholders ---
    @app.get("/join/success")
    def join_success():
        if not STAFF_SIGNUP_ENABLED:
            abort(404)
        return render_template("checkin/join_success.html")

    @app.get("/join/cancel")
    def join_cancel():
        if not STAFF_SIGNUP_ENABLED:
            abort(404)
        return render_template("checkin/join_cancel.html")

    @app.get("/api/staff/metrics")
    def api_staff_metrics():
        require_admin()
        try:
            con = connect_db(); cur = con.cursor()
            # Today totals
            if using_postgres():
                cur.execute("SELECT COUNT(*) AS c FROM check_ins WHERE timestamp >= CURRENT_DATE AND timestamp < CURRENT_DATE + INTERVAL '1 day'")
            else:
                cur.execute("SELECT COUNT(*) AS c FROM check_ins WHERE date(timestamp) = date('now')")
            row = cur.fetchone() or {}
            today_total = (row[0] if isinstance(row, (list, tuple)) else row.get('c', 0))

            # Last hour total
            if using_postgres():
                cur.execute("SELECT COUNT(*) AS c FROM check_ins WHERE timestamp >= NOW() - INTERVAL '1 hour'")
            else:
                cur.execute("SELECT COUNT(*) AS c FROM check_ins WHERE timestamp >= datetime('now','-1 hour')")
            row = cur.fetchone() or {}
            last_hour_total = (row[0] if isinstance(row, (list, tuple)) else row.get('c', 0))

            if using_postgres():
                cur.execute("SELECT COUNT(DISTINCT member_id) AS c FROM check_ins WHERE timestamp >= CURRENT_DATE AND timestamp < CURRENT_DATE + INTERVAL '1 day'")
            else:
                cur.execute("SELECT COUNT(DISTINCT member_id) AS c FROM check_ins WHERE date(timestamp) = date('now')")
            row = cur.fetchone() or {}
            today_unique = (row[0] if isinstance(row, (list, tuple)) else row.get('c', 0))

            # Recent check-ins (last 10)
            cur.execute(
                ("""
                 SELECT ci.timestamp, ci.method, m.name
                 FROM check_ins ci JOIN members m ON m.id = ci.member_id
                 ORDER BY ci.timestamp DESC LIMIT 10
                 """ if using_postgres() else
                 """
                 SELECT ci.timestamp, ci.method, m.name
                 FROM check_ins ci JOIN members m ON m.id = ci.member_id
                 ORDER BY ci.timestamp DESC LIMIT 10
                 """
                )
            )
            recents = []
            for r in cur.fetchall():
                if using_postgres():
                    recents.append({"timestamp": str(r.get("timestamp")), "method": r.get("method"), "name": r.get("name")})
                else:
                    recents.append({"timestamp": r[0], "method": r[1], "name": r[2]})

            # 7-day trend (fill missing days in Python)
            if using_postgres():
                cur.execute("SELECT date(timestamp) AS d, COUNT(*) AS c FROM check_ins WHERE timestamp >= CURRENT_DATE - INTERVAL '6 days' GROUP BY d ORDER BY d ASC")
                rows = cur.fetchall()
                counts = {}
                for r in rows:
                    dval = (r.get('d') if not isinstance(r, (list, tuple)) else r[0])
                    cval = (r.get('c') if not isinstance(r, (list, tuple)) else r[1])
                    counts[str(dval)] = int(cval or 0)
            else:
                cur.execute("SELECT date(timestamp) AS d, COUNT(*) AS c FROM check_ins WHERE date(timestamp) >= date('now','-6 day') GROUP BY d ORDER BY d ASC")
                rows = cur.fetchall()
                counts = {}
                for r in rows:
                    # sqlite row supports key access
                    dval = r['d'] if hasattr(r, '__getitem__') and 'd' in r.keys() else (r[0] if isinstance(r,(list,tuple)) else r[0])
                    cval = r['c'] if hasattr(r, '__getitem__') and 'c' in r.keys() else (r[1] if isinstance(r,(list,tuple)) else r[1])
                    counts[str(dval)] = int(cval or 0)
            from datetime import date, timedelta
            today = date.today()
            trend = []
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                ds = d.isoformat()
                trend.append({"date": ds, "count": int(counts.get(ds, 0) or 0)})

            con.close()
            return jsonify({
                "ok": True,
                "today_total": today_total,
                "last_hour_total": last_hour_total,
                "today_unique": today_unique,
                "trend": trend,
                "recent": recents,
            })
        except Exception as e:
            try:
                con.close()
            except Exception:
                pass
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.get("/api/kiosk/status")
    def api_kiosk_status():
        try:
            con = connect_db(); cur = con.cursor()

            if using_postgres():
                cur.execute("SELECT COUNT(*) AS c FROM check_ins WHERE timestamp >= CURRENT_DATE AND timestamp < CURRENT_DATE + INTERVAL '1 day'")
            else:
                cur.execute("SELECT COUNT(*) AS c FROM check_ins WHERE date(timestamp) = date('now')")
            row = cur.fetchone() or {}
            today_total = (row[0] if isinstance(row, (list, tuple)) else row.get('c', 0))

            if using_postgres():
                cur.execute("SELECT COUNT(*) AS c FROM check_ins WHERE timestamp >= NOW() - INTERVAL '1 hour'")
            else:
                cur.execute("SELECT COUNT(*) AS c FROM check_ins WHERE timestamp >= datetime('now','-1 hour')")
            row = cur.fetchone() or {}
            last_hour_total = (row[0] if isinstance(row, (list, tuple)) else row.get('c', 0))

            count = int(last_hour_total or 0)
            if count >= 25:
                level = "peak"
                headline = "Peak hour right now"
                detail = f"{count} check-ins in the past 60 minutes."
            elif count >= 12:
                level = "steady"
                headline = "Steady floor traffic"
                detail = f"{count} check-ins this hour."
            elif count > 0:
                level = "calm"
                headline = "Calm moment to check in"
                detail = f"Only {count} check-ins this hour."
            else:
                level = "calm"
                headline = "You are first to arrive"
                detail = "No check-ins logged in the past hour yet."

            messages = [
                {"label": headline, "subtext": detail, "level": level},
                {"label": "So far today", "subtext": f"{int(today_total or 0)} check-ins logged."},
            ]

            con.close()
            return jsonify({
                "ok": True,
                "busyness": {
                    "level": level,
                    "label": headline,
                    "detail": detail,
                    "last_hour_total": count,
                    "today_total": int(today_total or 0),
                },
                "messages": messages,
            })
        except Exception as e:
            try:
                con.close()
            except Exception:
                pass
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.get("/admin/members")
    def admin_members_page():
        if not session.get("admin"):
            return redirect(url_for("admin_login", next="/admin/members"))
        return render_template("checkin/admin_members.html", datetime=datetime)

    def _query_members_list(q: str | None, tier: str | None, status: str | None, page: int, per_page: int):
        con = connect_db(); cur = con.cursor()
        where = ["1=1"]
        params = []
        like = None
        if q:
            like = f"%{q}%"
            if using_postgres():
                where.append("(m.name ILIKE %s OR m.email_lower ILIKE %s OR m.phone_e164 ILIKE %s)")
                params += [like, like, like]
            else:
                where.append("(m.name LIKE ? OR m.email_lower LIKE ? OR m.phone_e164 LIKE ?)")
                params += [like, like, like]
        if status in ("active","inactive"):
            where.append("m.status = %s" if using_postgres() else "m.status = ?")
            params.append(status)
        tier_join = ""
        if tier in ("essential","elevated","elite"):
            where.append("(m.membership_tier = %s)" if using_postgres() else "(m.membership_tier = ?)")
            params.append(tier)
        base = f"""
            FROM members m
            {tier_join}
            WHERE {' AND '.join(where)}
        """
        # total
        count_sql = "SELECT COUNT(*) AS total_count " + base
        cur.execute(count_sql, tuple(params))
        total_row = cur.fetchone()
        if isinstance(total_row, (list, tuple)):
            total = total_row[0]
        elif total_row:
            total = total_row.get('total_count') or total_row.get('?column?') or 0
        else:
            total = 0
        # page
        offset = (page-1)*per_page
        if using_postgres():
            order = "ORDER BY lower(regexp_replace(m.name, '^.*\\s+', '')) ASC, lower(m.name) ASC"
        else:
            order = "ORDER BY lower(CASE WHEN instr(trim(m.name), ' ') > 0 THEN substr(trim(m.name), instr(trim(m.name), ' ') + 1) ELSE trim(m.name) END) ASC, lower(m.name) ASC"
        if using_postgres():
            cur.execute(
                f"""
                SELECT m.id, m.name, m.email_lower, m.phone_e164, m.status, to_char(m.updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated_at,
                       m.membership_tier
                {base}
                {order}
                LIMIT %s OFFSET %s
                """,
                tuple(params + [per_page, offset])
            )
        else:
            cur.execute(
                f"""
                SELECT m.id, m.name, m.email_lower, m.phone_e164, m.status, m.updated_at AS updated_at,
                       m.membership_tier
                {base}
                {order}
                LIMIT ? OFFSET ?
                """,
                tuple(params + [per_page, offset])
            )
        items = []
        for r in cur.fetchall():
            if using_postgres():
                items.append({
                    "id": r.get("id"), "name": r.get("name"), "email_lower": r.get("email_lower"),
                    "phone_e164": r.get("phone_e164"), "status": r.get("status"), "updated_at": r.get("updated_at"),
                    "tier": r.get("membership_tier"),
                })
            else:
                items.append({
                    "id": r[0], "name": r[1], "email_lower": r[2], "phone_e164": r[3], "status": r[4],
                    "updated_at": r[5], "tier": r[6],
                })
        con.close()
        return total, items

    @app.get("/api/admin/members")
    def api_admin_members():
        require_admin()
        q = (request.args.get("q") or "").strip()
        tier = (request.args.get("tier") or "").strip().lower() or None
        status = (request.args.get("status") or "").strip().lower() or None
        try:
            page = max(1, int(request.args.get("page", "1")))
            per_page = min(100, max(1, int(request.args.get("per_page", "25"))))
        except Exception:
            page, per_page = 1, 25
        try:
            total, items = _query_members_list(q or None, tier, status, page, per_page)
            return jsonify({"ok": True, "page": page, "per_page": per_page, "total": total, "items": items})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.get("/api/admin/members/<int:member_id>")
    def api_admin_member_detail(member_id: int):
        require_admin()
        con = connect_db(); cur = con.cursor()
        # member row
        try:
            cur.execute(
                ("SELECT id, name, email_lower, phone_e164, status, membership_tier, to_char(updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated_at FROM members WHERE id=%s" if using_postgres() else
                 "SELECT id, name, email_lower, phone_e164, status, membership_tier, updated_at FROM members WHERE id=?"),
                (member_id,)
            )
            r = cur.fetchone()
            if not r:
                con.close(); return jsonify({"ok": False, "error": "Not found"}), 404
            if using_postgres():
                member = {"id": r.get("id"), "name": r.get("name"), "email_lower": r.get("email_lower"),
                          "phone_e164": r.get("phone_e164"), "status": r.get("status"),
                          "tier": r.get("membership_tier"), "updated_at": r.get("updated_at")}
            else:
                member = {"id": r[0], "name": r[1], "email_lower": r[2], "phone_e164": r[3], "status": r[4],
                          "tier": r[5], "updated_at": r[6]}
            # recent check-ins
            cur.execute(
                ("SELECT timestamp, method FROM check_ins WHERE member_id=%s ORDER BY timestamp DESC LIMIT 10" if using_postgres() else
                 "SELECT timestamp, method FROM check_ins WHERE member_id=? ORDER BY timestamp DESC LIMIT 10"),
                (member_id,)
            )
            rows = cur.fetchall()
            recents = []
            for rr in rows:
                if using_postgres():
                    recents.append({"timestamp": str(rr.get("timestamp")), "method": rr.get("method")})
                else:
                    recents.append({"timestamp": rr[0], "method": rr[1]})
            con.close()
            return jsonify({"ok": True, "member": member, "recent_checkins": recents})
        except Exception as e:
            try:
                con.close()
            except Exception:
                pass
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.post("/admin/smtp_test")
    def admin_smtp_test():
        require_admin()
        to = (request.json or {}).get('to')
        if not to:
            return jsonify({"ok": False, "error": "Missing 'to'"}), 400
        ok = send_email(to, "Atlas Check-In Test", "This is a test email from staging.", "<p>This is a <b>test</b> email from staging.</p>")
        return jsonify({"ok": ok})

    @app.post("/api/upload_csv")
    def upload_csv():
        require_admin()
        try:
            f = request.files.get("file")
            if not f:
                return jsonify({"ok": False, "error": "No file uploaded"}), 400
            decoded = f.stream.read().decode("utf-8", errors="ignore")
            reader = csv.DictReader(decoded.splitlines())
            con = connect_db()
            cur = con.cursor()
            commit = request.args.get("commit", "1") in ("1", "true", "yes")
            deactivate_missing = request.args.get("deactivate_missing", "0") in ("1", "true", "yes")

            parsed = []
            for row in reader:
                mapped = _map_csv_row(row)
                if mapped:
                    parsed.append(mapped)

            csv_keys = set()
            for p in parsed:
                key = p["external_id"] or normalize_email(p["email"]) or normalize_phone(p["phone"]) or None
                if key:
                    csv_keys.add(key)

            activated = 0
            for p in parsed:
                mid = upsert_member(cur, p["external_id"], p["name"], p["email"], p["phone"], p["tier"], p["status"])
                if using_postgres():
                    cur.execute("SELECT qr_token FROM members WHERE id=%s", (mid,))
                else:
                    cur.execute("SELECT qr_token FROM members WHERE id=?", (mid,))
                tok_row = cur.fetchone()
                tok = (tok_row["qr_token"] if using_postgres() else tok_row[0]) if tok_row else None
                if not tok:
                    if using_postgres():
                        cur.execute("UPDATE members SET qr_token=%s WHERE id=%s", (secrets.token_urlsafe(24), mid))
                    else:
                        cur.execute("UPDATE members SET qr_token=? WHERE id=?", (secrets.token_urlsafe(24), mid))
                if p["status"] == "active":
                    activated += 1

            deactivated = 0
            if deactivate_missing and csv_keys:
                cur.execute("SELECT id, external_id, email_lower, phone_e164 FROM members WHERE status='active'")
                missing_ids = []
                for r in cur.fetchall():
                    key = r["external_id"] or r["email_lower"] or r["phone_e164"]
                    if key and key not in csv_keys:
                        missing_ids.append(r["id"])
                if missing_ids and commit:
                    if using_postgres():
                        for i in missing_ids:
                            cur.execute("UPDATE members SET status='inactive' WHERE id=%s", (i,))
                    else:
                        cur.executemany("UPDATE members SET status='inactive' WHERE id=?", [(i,) for i in missing_ids])
                deactivated = len(missing_ids)

            if commit:
                con.commit()
            con.close()
            return jsonify({
                "ok": True,
                "imported": len(parsed),
                "activated": activated,
                "deactivated": deactivated,
                "deactivate_missing": deactivate_missing,
                "committed": commit,
            })
        except Exception as e:
            try:
                # Best effort rollback/close
                con.rollback()
                con.close()
            except Exception:
                pass
            return jsonify({"ok": False, "error": f"Import failed: {str(e)}"}), 500

    @app.post("/api/import_preview")
    def import_preview():
        require_admin()
        f = request.files.get("file")
        if not f:
            return jsonify({"ok": False, "error": "No file uploaded"}), 400
        decoded = f.stream.read().decode("utf-8", errors="ignore")
        reader = csv.DictReader(decoded.splitlines())

        parsed = []
        for row in reader:
            mapped = _map_csv_row(row)
            if mapped:
                parsed.append(mapped)

        con = connect_db()
        cur = con.cursor()
        cur.execute("SELECT id, external_id, name, email_lower, phone_e164, membership_tier, status FROM members")
        rows = cur.fetchall()
        con.close()

        by_ext = {r["external_id"]: r for r in rows if r["external_id"]}
        by_email = {r["email_lower"]: r for r in rows if r["email_lower"]}
        by_phone = {r["phone_e164"]: r for r in rows if r["phone_e164"]}

        inserts, updates, reactivations = [], [], []
        matched_keys = set()
        for p in parsed:
            key = p["external_id"] or normalize_email(p["email"]) or normalize_phone(p["phone"]) or None
            matched_keys.add(key)
            existing = None
            if p["external_id"] and p["external_id"] in by_ext:
                existing = by_ext[p["external_id"]]
            elif p["email"] and normalize_email(p["email"]) in by_email:
                existing = by_email[normalize_email(p["email"]) ]
            elif p["phone"] and normalize_phone(p["phone"]) in by_phone:
                existing = by_phone[normalize_phone(p["phone"]) ]
            if not existing:
                inserts.append({"name": p["name"], "email": normalize_email(p["email"]), "phone": normalize_phone(p["phone"])})
            else:
                needs_update = (
                    (p["name"] and p["name"] != existing["name"]) or
                    (normalize_email(p["email"]) != existing["email_lower"]) or
                    (normalize_phone(p["phone"]) != existing["phone_e164"]) or
                    (p["tier"] != existing["membership_tier"]) or
                    (p["status"] != existing["status"]) 
                )
                if existing["status"] == 'inactive' and p["status"] == 'active':
                    reactivations.append({"name": existing["name"], "email": existing["email_lower"]})
                elif needs_update:
                    updates.append({"name": existing["name"], "email": existing["email_lower"]})

        con = connect_db()
        cur = con.cursor()
        cur.execute("SELECT external_id, email_lower, phone_e164, name FROM members WHERE status='active'")
        active_rows = cur.fetchall()
        con.close()
        missing = []
        for r in active_rows:
            key = r["external_id"] or r["email_lower"] or r["phone_e164"]
            if key and key not in matched_keys:
                missing.append({"name": r["name"], "email": r["email_lower"]})

        return jsonify({
            "ok": True,
            "counts": {
                "inserts": len(inserts),
                "updates": len(updates),
                "reactivations": len(reactivations),
                "deactivate_candidates": len(missing),
                "total_rows": len(parsed)
            },
            "samples": {
                "inserts": inserts[:5],
                "updates": updates[:5],
                "reactivations": reactivations[:5],
                "deactivate_candidates": missing[:5]
            }
        })

    @app.get("/api/members/search")
    def member_search():
        require_admin()
        q = (request.args.get("q") or "").strip().lower()
        if not q:
            return jsonify([])
        con = connect_db()
        cur = con.cursor()
        like = f"%{q}%"
        if using_postgres():
            cur.execute(
                """
                SELECT id, name, email_lower, phone_e164, membership_tier, status
                FROM members
                WHERE status='active' AND (
                    name ILIKE %s OR email_lower ILIKE %s OR phone_e164 ILIKE %s
                )
                ORDER BY name ASC
                LIMIT 20
                """,
                (like, like, like),
            )
        else:
            cur.execute(
                """
                SELECT id, name, email_lower, phone_e164, membership_tier, status
                FROM members
                WHERE status='active' AND (
                    name LIKE ? OR email_lower LIKE ? OR phone_e164 LIKE ?
                )
                ORDER BY name ASC
                LIMIT 20
                """,
                (like, like, like),
            )
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return jsonify(rows)

    def _find_member_by_qr_token(token: str) -> sqlite3.Row | None:
        con = connect_db()
        cur = con.cursor()
        cur.execute(
            ("SELECT * FROM members WHERE qr_token = %s AND status='active'" if using_postgres() else "SELECT * FROM members WHERE qr_token = ? AND status='active'"),
            (token,),
        )
        row = cur.fetchone()
        con.close()
        return row

    def _find_member_by_lookup(email: str | None, phone: str | None) -> sqlite3.Row | None:
        email_n = normalize_email(email)
        phone_n = normalize_phone(phone)
        con = connect_db()
        cur = con.cursor()
        if email_n:
            cur.execute(
                ("SELECT * FROM members WHERE email_lower = %s AND status='active'" if using_postgres() else "SELECT * FROM members WHERE email_lower = ? AND status='active'"),
                (email_n,),
            )
            row = cur.fetchone()
            if row:
                con.close()
                return row
        if phone_n:
            cur.execute(
                ("SELECT * FROM members WHERE phone_e164 = %s AND status='active'" if using_postgres() else "SELECT * FROM members WHERE phone_e164 = ? AND status='active'"),
                (phone_n,),
            )
            row = cur.fetchone()
            con.close()
            return row
        con.close()
        return None

    def _recent_checkin_exists(member_id: int, window_minutes: int) -> bool:
        con = connect_db()
        cur = con.cursor()
        cur.execute(
            ("SELECT timestamp FROM check_ins WHERE member_id = %s ORDER BY timestamp DESC LIMIT 1" if using_postgres() else "SELECT timestamp FROM check_ins WHERE member_id = ? ORDER BY timestamp DESC LIMIT 1"),
            (member_id,),
        )
        row = cur.fetchone()
        con.close()
        if not row:
            return False
        ts_val = row[0] if isinstance(row, (list, tuple)) else (row.get("timestamp") if isinstance(row, dict) else row["timestamp"])
        if isinstance(ts_val, datetime):
            last_ts = ts_val
        else:
            try:
                last_ts = datetime.fromisoformat(str(ts_val))
            except Exception:
                last_ts = datetime.strptime(str(ts_val), "%Y-%m-%d %H:%M:%S")
        if last_ts.tzinfo is not None:
            last_ts = last_ts.astimezone(timezone.utc).replace(tzinfo=None)
        return datetime.now() - last_ts < timedelta(minutes=window_minutes)

    @app.post("/api/checkin")
    def api_checkin():
        payload = request.get_json(silent=True) or {}
        member_id_in = (payload.get("member_id") or request.form.get("member_id") or "").strip()
        qr_token = (payload.get("qr_token") or request.form.get("qr_token") or "").strip()
        email = (payload.get("email") or request.form.get("email") or "").strip()
        phone = (payload.get("phone") or request.form.get("phone") or "").strip()
        method = "QR" if qr_token else "manual"
        member = None
        if member_id_in.isdigit():
            con = connect_db(); cur = con.cursor()
            cur.execute(
                ("SELECT * FROM members WHERE id = %s AND status='active'" if using_postgres() else "SELECT * FROM members WHERE id = ? AND status='active'"),
                (int(member_id_in),)
            )
            member = cur.fetchone()
            con.close()
        elif qr_token:
            member = _find_member_by_qr_token(qr_token)
        else:
            member = _find_member_by_lookup(email, phone)
        if not member:
            return jsonify({"ok": False, "error": "Member not found or inactive"}), 404

        if _recent_checkin_exists(member["id"], DUP_WINDOW_MINUTES):
            return jsonify({"ok": True, "message": "Already checked in recently", "member_name": member["name"]})

        con = connect_db()
        cur = con.cursor()
        if using_postgres():
            cur.execute(
                "INSERT INTO check_ins(member_id, location_id, method, source_device_id, status) VALUES (%s, 1, %s, %s, 'ok')",
                (member["id"], method, request.headers.get("X-Device-Id", "kiosk-1")),
            )
        else:
            cur.execute(
                "INSERT INTO check_ins(member_id, location_id, method, source_device_id, status) VALUES (?, 1, ?, ?, 'ok')",
                (member["id"], method, request.headers.get("X-Device-Id", "kiosk-1")),
            )
        con.commit()
        con.close()
        return jsonify({"ok": True, "member_name": member["name"]})

    @app.get("/api/kiosk/suggest")
    def kiosk_suggest():
        # Public minimal suggestion: returns id+name only, requires q length >= 2
        q = (request.args.get("q") or "").strip()
        if len(q) < 2:
            return jsonify([])
        like = f"%{q}%"
        con = connect_db(); cur = con.cursor()
        if using_postgres():
            cur.execute(
                """
                SELECT id, name FROM members
                WHERE status='active' AND name ILIKE %s
                ORDER BY name ASC
                LIMIT 5
                """,
                (like,)
            )
        else:
            cur.execute(
                """
                SELECT id, name FROM members
                WHERE status='active' AND name LIKE ?
                ORDER BY name ASC
                LIMIT 5
                """,
                (like,)
            )
        rows = cur.fetchall(); con.close()
        return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])

    @app.post("/api/qr/resend")
    def api_qr_resend():
        # Email-only kiosk resend to reduce input friction and enforce clean roster data
        payload = request.get_json(silent=True) or {}
        email_in = (payload.get("email") or request.form.get("email") or "").strip()
        email_n = normalize_email(email_in) if email_in else None
        if not email_n:
            return jsonify({"ok": False, "error": "Email required"}), 400

        con = connect_db()
        cur = con.cursor()
        cur.execute(
            ("SELECT * FROM members WHERE email_lower = %s AND status='active'" if using_postgres() else "SELECT * FROM members WHERE email_lower = ? AND status='active'"),
            (email_n,),
        )
        member = cur.fetchone()
        con.close()

        if not member:
            return jsonify({"ok": False, "error": "Member not found or inactive"}), 404

        token = ensure_qr_token(member)
        base_url = request.url_root.rstrip("/")
        link = f"{base_url}/member/qr?token={token}"
        wallet_available = WALLET_PASS_ENABLED and wallet_pass_configured()
        wallet_link = f"{base_url}/member/pass.apple?token={token}" if wallet_available else None
        wallet_text = f"Add to Apple Wallet: {wallet_link}\n\n" if wallet_link else ""
        full_name = (member.get("name") if isinstance(member, dict) else member["name"]) or ""
        full_name = full_name.strip()
        first_name = full_name.split()[0] if full_name else "there"
        preview_text = "Here's your Atlas Gym check-in QR code. Scan it at the kiosk for a breezy arrival."
        # Generate inline QR image
        qr_png = generate_qr_png(token, box_size=10, border=2)
        wallet_button_html = (
            f"<a href=\"{wallet_link}\" style=\"display:inline-flex;align-items:center;justify-content:center;background:#0f172a;color:#ffffff;text-decoration:none;padding:14px 28px;border-radius:14px;font-weight:700;font-size:16px;letter-spacing:0.3px;\">Add to Apple Wallet</a>"
            if wallet_link else ""
        )
        body = (
            f"Hi {first_name},\n\n"
            f"Here is your Atlas Gym check-in QR. Scan it at the kiosk or open it on your phone using the link below.\n\n"
            f"Open link: {link}\n"
            f"{wallet_text}"
            f"- The Atlas Gym Team\n"
            f"GymSense — Your gym operations, simplified."
        )
        body_html = f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Your Atlas Gym check-in code</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Oleo+Script:wght@700&display=swap" rel="stylesheet" />
  </head>
  <body style="margin:0;padding:32px 16px;background:#f5f5f5;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#101418;">
    <div style="display:none;font-size:1px;color:#f5f5f5;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;">{preview_text}</div>
    <div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:20px;padding:32px;">
      <div style="margin-bottom:24px;">
        <div style="font-size:24px;font-weight:700;margin:0;">The Atlas Gym</div>
        <div style="margin-top:6px;color:#6b7280;font-size:14px;">23282 Del Lago Dr, Laguna Hills, CA 92653</div>
      </div>
      <h1 style="font-size:24px;margin:0 0 12px;">Your check-in code</h1>
      <p style="margin:0 0 24px;color:#374151;font-size:16px;">Hi {first_name}, your QR code is ready for your next visit. Show it at the kiosk or tap below to open it on your phone.</p>
      <div style="text-align:center;padding:24px;border:1px solid #e5e7eb;border-radius:16px;background:#f9fafb;margin-bottom:24px;">
        <img src="cid:qrimg" width="240" height="240" alt="Your Atlas Gym QR Code" style="display:block;margin:0 auto 20px;border-radius:12px;border:1px solid #e5e7eb;background:#ffffff;" />
        <div style="display:flex;flex-direction:column;gap:12px;align-items:center;">
          {wallet_button_html}
          <a href="{link}" style="display:inline-flex;align-items:center;justify-content:center;width:auto;background:#ffffff;color:#0f172a;text-decoration:none;padding:13px 26px;border-radius:14px;font-weight:600;font-size:15px;border:1px solid #cbd5f5;">Open my QR code</a>
        </div>
      </div>
      <p style="margin:0;color:#6b7280;font-size:14px;">Save this email or add the link to your wallet for quicker access next time.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:32px 0 0;" />
    </div>
  </body>
</html>
        """
        inline = [("qr.png", qr_png, "image/png", "<qrimg>")] if qr_png else None
        ok = send_email(email_n or "", "Your Atlas Gym Check-In Code", body, body_html, inline_images=inline) if email_n else True
        return jsonify({"ok": ok, "wallet": wallet_available})

    @app.post("/api/pass/apple")
    def api_pass_apple():
        return jsonify({"ok": False, "error": "Use GET /member/pass.apple?token=..."}), 405

    @app.get("/member/pass.apple")
    def member_pass_apple():
        if not WALLET_PASS_ENABLED or not wallet_pass_configured():
            abort(404)
        token = (request.args.get("token") or "").strip()
        if not token:
            return "Missing token", 400
        member = _find_member_by_qr_token(token)
        if not member:
            abort(404)
        try:
            result = build_member_wallet_pass(member, token, request.url_root.rstrip("/"))
        except Exception as exc:
            print("Wallet pass generation failed:", exc)
            return "Unable to generate pass", 500
        bio = io.BytesIO(result.data)
        bio.seek(0)
        response = send_file(
            bio,
            mimetype=result.content_type,
            as_attachment=True,
            download_name=result.filename,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/member/qr")
    def member_qr_page():
        token = (request.args.get("token") or "").strip()
        if not token:
            return "Missing token", 400
        return render_template("checkin/member_qr.html", token=token)

    @app.get("/api/qr.png")
    def api_qr_png():
        token = (request.args.get("token") or "").strip()
        if not token:
            return "Bad request", 400
        png = generate_qr_png(token)
        if not png:
            return "Error", 500
        from flask import Response
        return Response(png, mimetype='image/png')

    # PWA icons (generated server-side for convenience)
    @app.get("/icons/icon-192.png")
    def icon_192():
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new('RGB', (192, 192), color=(0, 0, 0))
            draw = ImageDraw.Draw(img)
            # neon green border
            draw.rectangle([4, 4, 188, 188], outline=(57, 255, 20), width=4)
            # centered A monogram
            text = "A"
            font = ImageFont.load_default()
            w, h = draw.textsize(text, font=font)
            draw.text(((192-w)//2, (192-h)//2), text, fill=(57, 255, 20), font=font)
            buf = io.BytesIO(); img.save(buf, format='PNG')
            buf.seek(0)
            from flask import Response
            return Response(buf.getvalue(), mimetype='image/png')
        except Exception:
            return "", 404

    @app.get("/icons/icon-512.png")
    def icon_512():
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new('RGB', (512, 512), color=(0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rectangle([8, 8, 504, 504], outline=(57, 255, 20), width=6)
            text = "A"
            font = ImageFont.load_default()
            w, h = draw.textsize(text, font=font)
            draw.text(((512-w)//2, (512-h)//2), text, fill=(57, 255, 20), font=font)
            buf = io.BytesIO(); img.save(buf, format='PNG')
            buf.seek(0)
            from flask import Response
            return Response(buf.getvalue(), mimetype='image/png')
        except Exception:
            return "", 404

    @app.get("/admin/init_pin")
    def admin_init_pin():
        if os.environ.get("ENABLE_INIT_PIN") != "1":
            abort(403)
        pin = request.args.get("pin", "1234")
        name = request.args.get("name", "Admin")
        create_or_rotate_staff_pin(name, pin)
        return "OK"

    @app.get("/admin/db_diag")
    def admin_db_diag():
        """Temporary diagnostics endpoint to debug DB connectivity.
        Guarded by ENABLE_INIT_PIN=1 like the init endpoint so it's only available during setup.
        Returns non-sensitive connection details and a SELECT 1 probe result.
        """
        if os.environ.get("ENABLE_INIT_PIN") != "1":
            abort(403)
        details = {
            "using_postgres": using_postgres(),
            "has_database_url": bool(DATABASE_URL),
        }
        # Parse DATABASE_URL shape without secrets
        try:
            dsn = (DATABASE_URL or "").strip()
            if dsn.startswith("postgres://") or dsn.startswith("postgresql://"):
                u = urlparse(dsn)
                details.update({
                    "dsn_kind": "uri",
                    "host": u.hostname,
                    "port": u.port,
                    "dbname": (u.path or "/postgres").lstrip("/") or "postgres",
                    "user": (u.username or ""),
                })
            elif dsn:
                details.update({
                    "dsn_kind": "conninfo",
                })
                # crude parse of key=value tokens
                parts = {}
                for tok in dsn.split():
                    if "=" in tok:
                        k, v = tok.split("=", 1)
                        parts[k] = v
                details.update({
                    "host": parts.get("host"),
                    "port": parts.get("port"),
                    "dbname": parts.get("dbname"),
                    "user": parts.get("user"),
                })
            user = details.get("user") or ""
            host = details.get("host") or ""
            details["pooler_mode"] = bool(host and host.endswith(".pooler.supabase.com"))
            # In pooler mode, user must include ".<project_ref>"
            details["user_has_project_suffix"] = ("." in user) if details["pooler_mode"] else ("." not in user)
        except Exception:
            pass

        probe = {"ok": False, "error": None}
        try:
            con = connect_db(); cur = con.cursor()
            cur.execute("SELECT 1")
            _ = cur.fetchone()
            con.close()
            probe["ok"] = True
        except Exception as e:
            probe["error"] = str(e)
        details["probe"] = probe
        return jsonify(details)

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5055"))
    app.run(host="0.0.0.0", port=port, debug=True)
