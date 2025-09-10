import os
import csv
import sqlite3
import hashlib
import hmac
import secrets
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    redirect,
    url_for,
    session,
    abort,
)


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


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
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


def ensure_qr_token(member: sqlite3.Row) -> str:
    token = member["qr_token"]
    if token:
        return token
    new_token = secrets.token_urlsafe(24)
    con = connect_db()
    cur = con.cursor()
    cur.execute("UPDATE members SET qr_token = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_token, member["id"]))
    con.commit()
    con.close()
    return new_token


def upsert_member(cur: sqlite3.Cursor, external_id: str | None, name: str, email: str | None, phone: str | None, membership_tier: str | None, status: str):
    email_n = normalize_email(email)
    phone_n = normalize_phone(phone)
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
        cur.execute(
            """
            UPDATE members
            SET name = ?, email_lower = ?, phone_e164 = ?, membership_tier = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, email_n, phone_n, membership_tier, status, existing[0]),
        )
        return existing[0]
    else:
        cur.execute(
            """
            INSERT INTO members(external_id, name, email_lower, phone_e164, membership_tier, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (external_id, name, email_n, phone_n, membership_tier, status),
        )
        return cur.lastrowid


def send_email(to_email: str, subject: str, body: str, body_html: str | None = None) -> bool:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    from_email = os.environ.get("SMTP_FROM", user or "noreply@example.com")
    if not host or not user or not password:
        print(f"[DEV] Would send email to {to_email}: {subject}\n{body}")
        return True
    try:
        if body_html:
            from email.mime.multipart import MIMEMultipart
            alt = MIMEMultipart('alternative')
            alt['Subject'] = subject
            alt['From'] = from_email
            alt['To'] = to_email
            alt.attach(MIMEText(body, 'plain'))
            alt.attach(MIMEText(body_html, 'html'))
            msg = alt
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
            return redirect(url_for("admin_dashboard"))
        return render_template("checkin/admin_login.html", error="Invalid PIN")

    def require_admin():
        if not session.get("admin"):
            abort(401)

    @app.get("/admin/logout")
    def admin_logout():
        session.pop("admin", None)
        return redirect(url_for("admin_login"))

    @app.get("/admin")
    def admin_dashboard():
        require_admin()
        con = connect_db()
        cur = con.cursor()
        cur.execute(
            """
            SELECT ci.id, ci.timestamp, ci.method, m.name AS member_name
            FROM check_ins ci
            JOIN members m ON m.id = ci.member_id
            ORDER BY ci.timestamp DESC
            LIMIT 25
            """
        )
        rows = cur.fetchall()
        con.close()
        return render_template("checkin/admin_dashboard.html", checkins=rows)

    @app.post("/api/upload_csv")
    def upload_csv():
        require_admin()
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
            cur.execute("SELECT qr_token FROM members WHERE id=?", (mid,))
            tok = cur.fetchone()[0]
            if not tok:
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
        cur.execute("SELECT * FROM members WHERE qr_token = ? AND status='active'", (token,))
        row = cur.fetchone()
        con.close()
        return row

    def _find_member_by_lookup(email: str | None, phone: str | None) -> sqlite3.Row | None:
        email_n = normalize_email(email)
        phone_n = normalize_phone(phone)
        con = connect_db()
        cur = con.cursor()
        if email_n:
            cur.execute("SELECT * FROM members WHERE email_lower = ? AND status='active'", (email_n,))
            row = cur.fetchone()
            if row:
                con.close()
                return row
        if phone_n:
            cur.execute("SELECT * FROM members WHERE phone_e164 = ? AND status='active'", (phone_n,))
            row = cur.fetchone()
            con.close()
            return row
        con.close()
        return None

    def _recent_checkin_exists(member_id: int, window_minutes: int) -> bool:
        con = connect_db()
        cur = con.cursor()
        cur.execute(
            "SELECT timestamp FROM check_ins WHERE member_id = ? ORDER BY timestamp DESC LIMIT 1",
            (member_id,),
        )
        row = cur.fetchone()
        con.close()
        if not row:
            return False
        try:
            last_ts = datetime.fromisoformat(row[0])
        except Exception:
            last_ts = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
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
            cur.execute("SELECT * FROM members WHERE id = ? AND status='active'", (int(member_id_in),))
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
        # Accept email and/or phone; use whichever is provided
        payload = request.get_json(silent=True) or {}
        email_in = (payload.get("email") or request.form.get("email") or "").strip()
        phone_in = (payload.get("phone") or request.form.get("phone") or "").strip()
        email_n = normalize_email(email_in) if email_in else None
        phone_n = normalize_phone(phone_in) if phone_in else None
        if not email_n and not phone_n:
            return jsonify({"ok": False, "error": "Email or phone required"}), 400

        con = connect_db()
        cur = con.cursor()
        member = None
        if email_n:
            cur.execute("SELECT * FROM members WHERE email_lower = ? AND status='active'", (email_n,))
            member = cur.fetchone()
        if not member and phone_n:
            cur.execute("SELECT * FROM members WHERE phone_e164 = ? AND status='active'", (phone_n,))
            member = cur.fetchone()
        con.close()

        if not member:
            return jsonify({"ok": False, "error": "Member not found or inactive"}), 404

        token = ensure_qr_token(member)
        base_url = request.url_root.rstrip("/")
        link = f"{base_url}/member/qr?token={token}"
        body = (
            f"Hi {member['name']},\n\n"
            f"Here is your Atlas Gym check-in code. Keep this email or bookmark the link.\n\n"
            f"Check-in link: {link}\n"
            f"QR token (for manual entry if needed): {token}\n\n"
            f"– Atlas Gym"
        )
        body_html = f"""
        <div style='font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.45;color:#111'>
          <p>Hi {member['name']},</p>
          <p>Here is your Atlas Gym check-in code. Keep this email or bookmark the link.</p>
          <p><a href='{link}' style='background:#111;color:#fff;padding:10px 14px;border-radius:8px;text-decoration:none'>Open My QR Code</a></p>
          <p style='color:#666'>Token (fallback): <code>{token}</code></p>
          <p>– Atlas Gym</p>
        </div>
        """
        ok = send_email(email_n or "", "Your Atlas Gym Check-In Code", body, body_html) if email_n else True
        return jsonify({"ok": ok})

    @app.get("/member/qr")
    def member_qr_page():
        token = (request.args.get("token") or "").strip()
        if not token:
            return "Missing token", 400
        return render_template("checkin/member_qr.html", token=token)

    @app.get("/admin/init_pin")
    def admin_init_pin():
        if os.environ.get("ENABLE_INIT_PIN") != "1":
            abort(403)
        pin = request.args.get("pin", "1234")
        name = request.args.get("name", "Admin")
        create_or_rotate_staff_pin(name, pin)
        return "OK"

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5055"))
    app.run(host="0.0.0.0", port=port, debug=True)
