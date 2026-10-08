import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import threading
from contextlib import contextmanager
from html import escape
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

app = FastAPI(title="One Question", docs_url=None, redoc_url=None, openapi_url=None)
logger = logging.getLogger("uvicorn.error")
_postgres_ready: set[str] = set()
_postgres_init_lock = threading.Lock()
COOKIE = "bro_session"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
POSTGRES_SCHEMA = """
CREATE SCHEMA IF NOT EXISTS itsdonebro;
SET search_path TO itsdonebro;
CREATE TABLE IF NOT EXISTS guests (
  id BIGSERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL, salt TEXT NOT NULL, digest TEXT NOT NULL,
  email TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS sessions (
  digest TEXT PRIMARY KEY, guest_id BIGINT NOT NULL, expires DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS login_links (
  digest TEXT PRIMARY KEY, guest_id BIGINT NOT NULL, expires DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_requests (
  key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY, guest_id BIGINT NOT NULL,
  payload_digest TEXT NOT NULL, provider_id TEXT NOT NULL,
  created DOUBLE PRECISION NOT NULL, delivery_mode TEXT NOT NULL DEFAULT 'local'
);
CREATE TABLE IF NOT EXISTS date_bookings (
  id TEXT PRIMARY KEY, payload_digest TEXT NOT NULL,
  provider_id TEXT NOT NULL, delivery_mode TEXT NOT NULL,
  requester_key TEXT NOT NULL, created DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS booking_rate_limits (
  key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
  id TEXT PRIMARY KEY, recipients TEXT NOT NULL,
  subject TEXT NOT NULL, body TEXT NOT NULL, created DOUBLE PRECISION NOT NULL
);
"""


class DatabaseConnection:
    """Small qmark-compatible adapter for SQLite and production PostgreSQL."""

    def __init__(self, connection, postgres: bool):
        self.connection = connection
        self.postgres = postgres

    def execute(self, sql: str, params=()):
        if self.postgres:
            sql = sql.replace("BEGIN IMMEDIATE", "BEGIN").replace("?", "%s")
        return self.connection.execute(sql, params)

    def executescript(self, sql: str):
        if self.postgres:
            for statement in sql.split(";"):
                if statement.strip():
                    self.connection.execute(statement)
        else:
            self.connection.executescript(sql)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


def normalize_email(value: str) -> str:
    email = value.strip().casefold()
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        raise ValueError("Enter a valid email address")
    return email


@contextmanager
def db():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        import psycopg
        from psycopg.rows import dict_row

        try:
            raw = psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10)
        except Exception as exc:
            log_failure("database_connect", exc)
            raise
        conn = DatabaseConnection(raw, postgres=True)
        try:
            fingerprint = token_hash(database_url)
            with _postgres_init_lock:
                if fingerprint not in _postgres_ready:
                    conn.executescript(POSTGRES_SCHEMA)
                    raw.execute("ALTER TABLE guests ADD COLUMN IF NOT EXISTS email TEXT")
                    raw.execute("CREATE UNIQUE INDEX IF NOT EXISTS guests_email_unique ON guests(email)")
                    raw.execute("ALTER TABLE date_bookings ADD COLUMN IF NOT EXISTS delivery_mode TEXT NOT NULL DEFAULT 'local'")
                    raw.execute("ALTER TABLE plans ADD COLUMN IF NOT EXISTS delivery_mode TEXT NOT NULL DEFAULT 'local'")
                    migrate_bookings(conn)
                    conn.commit()
                    _postgres_ready.add(fingerprint)
            raw.execute("SET search_path TO itsdonebro")
            conn.commit()
            yield conn
            conn.commit()
        except Exception as exc:
            if not isinstance(exc, HTTPException):
                log_failure("database_transaction", exc)
            conn.rollback()
            raise
        finally:
            conn.close()
        return
    if os.getenv("RENDER"):
        raise RuntimeError("DATABASE_URL must point to durable PostgreSQL on Render")

    raw = sqlite3.connect(os.getenv("DATABASE_PATH", "invites.sqlite3"), timeout=15)
    raw.row_factory = sqlite3.Row
    raw.executescript("""
      CREATE TABLE IF NOT EXISTS guests (
        id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL, salt TEXT NOT NULL, digest TEXT NOT NULL,
        email TEXT
      );
      CREATE TABLE IF NOT EXISTS sessions (
        digest TEXT PRIMARY KEY, guest_id INTEGER NOT NULL, expires REAL NOT NULL
      );
      CREATE TABLE IF NOT EXISTS login_links (
        digest TEXT PRIMARY KEY, guest_id INTEGER NOT NULL, expires REAL NOT NULL
      );
      CREATE TABLE IF NOT EXISTS auth_requests (
        key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires REAL NOT NULL
      );
      CREATE TABLE IF NOT EXISTS plans (
        id TEXT PRIMARY KEY, guest_id INTEGER NOT NULL,
        payload_digest TEXT NOT NULL, provider_id TEXT NOT NULL,
        created REAL NOT NULL, delivery_mode TEXT NOT NULL DEFAULT 'local'
      );
      CREATE TABLE IF NOT EXISTS date_bookings (
        id TEXT PRIMARY KEY, payload_digest TEXT NOT NULL,
        provider_id TEXT NOT NULL, delivery_mode TEXT NOT NULL,
        requester_key TEXT NOT NULL,
        created REAL NOT NULL
      );
      CREATE TABLE IF NOT EXISTS booking_rate_limits (
        key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires REAL NOT NULL
      );
      CREATE TABLE IF NOT EXISTS outbox (
        id TEXT PRIMARY KEY, recipients TEXT NOT NULL,
        subject TEXT NOT NULL, body TEXT NOT NULL, created REAL NOT NULL
      );
      DROP TRIGGER IF EXISTS single_recipient;
    """)
    conn = DatabaseConnection(raw, postgres=False)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(guests)")}
    if "email" not in columns:
        conn.execute("ALTER TABLE guests ADD COLUMN email TEXT")
    booking_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(date_bookings)")
    }
    if "delivery_mode" not in booking_columns:
        conn.execute(
            "ALTER TABLE date_bookings ADD COLUMN delivery_mode TEXT NOT NULL DEFAULT 'local'"
        )
    plan_columns = {row["name"] for row in conn.execute("PRAGMA table_info(plans)")}
    if "delivery_mode" not in plan_columns:
        conn.execute("ALTER TABLE plans ADD COLUMN delivery_mode TEXT NOT NULL DEFAULT 'local'")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS guests_email_unique ON guests(email)")
    migrate_bookings(conn)
    conn.commit()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def log_failure(stage: str, exc: Exception):
    # Never log the exception text/traceback: drivers may include connection
    # strings and providers may echo recipients or authentication information.
    sqlstate = getattr(exc, "sqlstate", None)
    safe_state = sqlstate if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate) else "none"
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else "none"
    logger.error("plan_failure stage=%s type=%s sqlstate=%s http_status=%s",
                 stage, type(exc).__name__, safe_state, status)


def migrate_bookings(conn: DatabaseConnection):
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(date_bookings)")} if not conn.postgres else set()
    for name, definition in {
        "guest_email": "TEXT",
        "payload": "TEXT",
        "mail_payload": "TEXT",
        "status": "TEXT NOT NULL DEFAULT 'accepted'",
    }.items():
        if conn.postgres:
            conn.execute(f"ALTER TABLE date_bookings ADD COLUMN IF NOT EXISTS {name} {definition}")
        elif name not in columns:
            conn.execute(f"ALTER TABLE date_bookings ADD COLUMN {name} {definition}")


def mail_configuration() -> tuple[str, str, str]:
    mode = os.getenv("MAIL_MODE", "local").strip().lower()
    owner = normalize_email(os.getenv("OWNER_EMAIL", ""))
    sender = os.getenv("MAIL_FROM", "").strip()
    if os.getenv("RENDER") and mode != "resend":
        raise RuntimeError("Production requires Resend")
    if mode not in {"local", "resend"}:
        raise RuntimeError("Invalid mail mode")
    if mode == "resend":
        if not os.getenv("RESEND_API_KEY", "").strip():
            raise RuntimeError("Missing Resend key")
        sender_address = normalize_email(parseaddr(sender)[1])
        if sender_address.rsplit("@", 1)[1] in {"gmail.com", "resend.dev"}:
            raise RuntimeError("Use a verified sending domain")
    return mode, owner, sender


def signing_secret() -> bytes:
    secret = os.getenv("SESSION_SIGNING_SECRET", "")
    if len(secret) < 32:
        if os.getenv("RENDER"):
            raise RuntimeError("SESSION_SIGNING_SECRET must contain at least 32 characters")
        secret = "local-development-only-secret-change-before-deploy"
    return secret.encode()


def signed_value(purpose: str, token: str, expires: int) -> str:
    value = f"{purpose}.{expires}.{token}"
    signature = hmac.new(signing_secret(), value.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{token}.{signature}"


def unsign_value(purpose: str, value: str) -> tuple[str, int] | None:
    try:
        expiry_text, token, signature = value.split(".", 2)
        expires = int(expiry_text)
    except (ValueError, AttributeError):
        return None
    signed = f"{purpose}.{expires}.{token}"
    expected = hmac.new(signing_secret(), signed.encode(), hashlib.sha256).hexdigest()
    if expires <= time.time() or not hmac.compare_digest(signature, expected):
        return None
    return token, expires


def session_token(request: Request) -> str:
    value = request.cookies.get(COOKIE, "")
    verified = unsign_value("session", value)
    return verified[0] if verified else ""


def allowed_origins() -> set[str]:
    configured = {
        origin.strip() for origin in os.getenv("APP_ORIGIN", "http://localhost:3000").split(",")
        if origin.strip()
    }
    render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_host:
        configured.add(f"https://{render_host}")
    secure_cookie = os.getenv("COOKIE_SECURE", "").lower() == "true" or bool(os.getenv("RENDER"))
    if not secure_cookie:
        for origin in tuple(configured):
            parsed = urlsplit(origin)
            if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}:
                port = f":{parsed.port}" if parsed.port else ""
                configured.update({f"http://localhost{port}", f"http://127.0.0.1{port}"})
    elif "APP_ORIGIN" not in os.environ:
        configured.update({"http://localhost:3000", "http://127.0.0.1:3000"})
    return configured


def check_origin(request: Request):
    if request.headers.get("origin") not in allowed_origins():
        raise HTTPException(403, "Origin not allowed")


def public_origin() -> str:
    return os.getenv("APP_ORIGIN", "http://localhost:3000").split(",")[0].strip()


def send_email(conn: DatabaseConnection, recipients: list[str], subject: str,
               body: str, key: str, html_body: str | None = None,
               sender_override: str | None = None) -> str:
    mode = os.getenv("MAIL_MODE", "local").lower()
    if mode == "local":
        conn.execute(
            "INSERT INTO outbox VALUES (?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (key, json.dumps(recipients), subject, body, time.time()),
        )
        return key
    if mode != "resend":
        raise RuntimeError("MAIL_MODE must be local or resend")
    api_key = os.getenv("RESEND_API_KEY")
    sender = sender_override or os.getenv("MAIL_FROM")
    if not api_key or not sender:
        raise RuntimeError("RESEND_API_KEY and MAIL_FROM are required")
    result = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Idempotency-Key": key},
        json={"from": sender, "to": recipients, "subject": subject, "text": body,
              **({"html": html_body} if html_body else {})},
        timeout=10,
    )
    result.raise_for_status()
    provider_id = result.json().get("id")
    if not provider_id:
        raise RuntimeError("Email provider did not confirm acceptance")
    return provider_id


@app.get("/health")
def health():
    # Render's liveness probe should reflect whether this server can serve the
    # game. Date-plan delivery has separate, optional configuration.
    return {"status": "ok"}


@app.get("/health/db")
def database_health():
    try:
        with db() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        log_failure("database_health", exc)
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ok"}


@app.get("/api/plan/status")
@app.get("/health/plan")
def plan_health():
    try:
        with db():
            pass
        mail_configuration()
    except Exception as exc:
        log_failure("plan_health", exc)
        raise HTTPException(503, "Plan delivery unavailable") from None
    return {"status": "ok"}


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        return normalize_email(value)


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    name: str = Field(default="", max_length=80)
    email: str = Field(min_length=3, max_length=254)
    when: str = Field(min_length=1, max_length=100)
    area: str = Field(min_length=1, max_length=100)
    outing: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("name", "when", "area", "outing", "note")
    @classmethod
    def clean(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        if info.field_name not in {"note", "name"} and not value:
            raise ValueError("This field is required")
        if info.field_name != "note" and ("\n" in value or "\t" in value):
            raise ValueError("Use a single line")
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("Control characters are not allowed")
        return value


@app.middleware("http")
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    commit = os.getenv("RENDER_GIT_COMMIT", "")
    if re.fullmatch(r"[a-f0-9]{40}", commit):
        response.headers["X-App-Commit"] = commit
    return response


@app.post("/api/login", status_code=202)
def login(body: LoginRequest, request: Request):
    check_origin(request)
    now = time.time()
    key = token_hash(request.client.host if request.client else "local")
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM auth_requests WHERE expires < ?", (now,))
        attempt = conn.execute("SELECT count FROM auth_requests WHERE key=?", (key,)).fetchone()
        if attempt and attempt["count"] >= 8:
            raise HTTPException(429, "Try again later", headers={"Retry-After": "300"})
        conn.execute(
            "INSERT INTO auth_requests VALUES (?,1,?) "
            "ON CONFLICT(key) DO UPDATE SET count=count+1",
            (key, now + 300),
        )
        guest = conn.execute(
            "SELECT id,email FROM guests WHERE name=? AND email=?",
            (body.name.strip().casefold(), body.email),
        ).fetchone()
        if guest:
            token = secrets.token_urlsafe(32)
            expiry = int(now + 900)
            conn.execute("INSERT INTO login_links VALUES (?,?,?)",
                         (token_hash(token), guest["id"], expiry))
            signed_link = signed_value("login", token, expiry)
            link = f"{public_origin()}/api/verify?token={quote(signed_link)}"
            try:
                send_email(conn, [guest["email"]], "Your Great No Chase sign-in link",
                           f"Open this link within 15 minutes to sign in:\n\n{link}\n\nIf you did not request it, ignore this email.",
                           f"login/{token_hash(token)}")
            except Exception as exc:
                conn.execute("DELETE FROM login_links WHERE digest=?", (token_hash(token),))
                print(f"Sign-in email could not be queued: {type(exc).__name__}", flush=True)
    return {"message": "If this invitation matches, a sign-in link is on its way."}


@app.get("/api/verify")
def verify(token: str, request: Request):
    now = time.time()
    verified_token = unsign_value("login", token)
    if not verified_token:
        return RedirectResponse(f"{public_origin()}/?link=invalid", status_code=303)
    raw_token, signed_expiry = verified_token
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        link = conn.execute(
            "SELECT guest_id FROM login_links WHERE digest=? AND expires>?",
            (token_hash(raw_token), now),
        ).fetchone()
        if not link:
            return RedirectResponse(f"{public_origin()}/?link=invalid", status_code=303)
        conn.execute("DELETE FROM login_links WHERE digest=?", (token_hash(raw_token),))
        old = request.cookies.get(COOKIE)
        if old:
            conn.execute("DELETE FROM sessions WHERE digest=?", (token_hash(old),))
        session_token = secrets.token_urlsafe(32)
        seconds = int(os.getenv("SESSION_HOURS", "168")) * 3600
        session_expiry = int(now + seconds)
        conn.execute("INSERT INTO sessions VALUES (?,?,?)",
                     (token_hash(session_token), link["guest_id"], session_expiry))
    response = RedirectResponse(f"{public_origin()}/?link=verified", status_code=303)
    response.set_cookie(COOKIE, signed_value("session", session_token, session_expiry), max_age=seconds, httponly=True,
                        secure=os.getenv("COOKIE_SECURE", "").lower() == "true" or bool(os.getenv("RENDER")),
                        samesite="lax", path="/")
    return response


def session_guest(conn: sqlite3.Connection, request: Request):
    token = session_token(request)
    if not token:
        raise HTTPException(401, "Sign in required")
    guest = conn.execute(
        "SELECT guests.id,guests.display_name,guests.email FROM guests "
        "JOIN sessions ON guests.id=sessions.guest_id "
        "WHERE sessions.digest=? AND sessions.expires>?",
        (token_hash(token), time.time()),
    ).fetchone()
    if not guest or not guest["email"]:
        raise HTTPException(401, "Sign in required")
    return guest


@app.get("/api/session")
def session(request: Request):
    with db() as conn:
        guest = session_guest(conn, request)
        return {"display_name": guest["display_name"]}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    check_origin(request)
    token = session_token(request)
    with db() as conn:
        if token:
            conn.execute("DELETE FROM sessions WHERE digest=?", (token_hash(token),))
    response.delete_cookie(COOKIE, path="/",
                           secure=os.getenv("COOKIE_SECURE", "").lower() == "true" or bool(os.getenv("RENDER")),
                           httponly=True, samesite="lax")
    return {"ok": True}


def plan_message(body: PlanRequest) -> dict:
    fields = [("Preferred day or time", body.when), ("Area or location", body.area),
              ("Type of outing", body.outing), ("Note", body.note or "None")]
    if body.name:
        fields.insert(0, ("Proposed by", body.name))
    intro = "Here is your proposed date plan, shared with you and Spandan."
    closing = ("This is a proposal, not a confirmed date, time, or venue. "
               "You can decide the details together. Spandan now gets to plan something "
               "worthwhile around his ten-hour workday. It's done bro — the planning begins!")
    text = intro + "\n\n" + "\n".join(f"{label}: {value}" for label, value in fields) + "\n\n" + closing
    rows = "".join(f"<dt><strong>{escape(label)}</strong></dt><dd>{escape(value).replace(chr(10), '<br>')}</dd>" for label, value in fields)
    html = f"<h1>Your proposed date plan</h1><p>{escape(intro)}</p><dl>{rows}</dl><p>{escape(closing)}</p>"
    return {"subject": "Your proposed date plan · It's Done Bro", "text": text, "html": html}


@app.post("/api/plan")
def send_plan(body: PlanRequest, request: Request):
    check_origin(request)
    try:
        mode, owner, sender = mail_configuration()
    except Exception as exc:
        log_failure("mail_configuration", exc)
        raise HTTPException(503, "Plan email is not configured") from None
    try:
        return save_and_deliver_plan(body, request, mode, owner, sender)
    except HTTPException:
        raise
    except Exception as exc:
        log_failure("plan_storage", exc)
        raise HTTPException(503, "Plan delivery was not confirmed. Keep this draft and retry.") from None


def save_and_deliver_plan(body: PlanRequest, request: Request, mode: str, owner: str, sender: str):
    now = time.time()
    requester_key = token_hash(request.client.host if request.client else "local")
    content = body.model_dump(exclude={"id"})
    payload = json.dumps(content, sort_keys=True)
    digest = token_hash(payload)
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.postgres:
            # Serialize quota checks and draft creation for the same requester.
            conn.execute("SELECT pg_advisory_xact_lock(?)", (int(requester_key[:15], 16),))
        existing = conn.execute("SELECT * FROM date_bookings WHERE id=?", (body.id,)).fetchone()
        if existing:
            if existing["payload_digest"] != digest:
                raise HTTPException(409, "This submission ID belongs to another draft")
            if existing["status"] == "accepted":
                return {"sent": True, "delivery": existing["delivery_mode"]}
        else:
            conn.execute("DELETE FROM booking_rate_limits WHERE expires < ?", (now,))
            attempt = conn.execute("SELECT count FROM booking_rate_limits WHERE key=?", (requester_key,)).fetchone()
            if attempt and attempt["count"] >= 3:
                raise HTTPException(429, "Plan limit reached for today")
            mail = {**plan_message(body), "recipients": list(dict.fromkeys([body.email, owner])), "sender": sender}
            conn.execute(
                "INSERT INTO date_bookings(id,payload_digest,provider_id,delivery_mode,requester_key,created,guest_email,payload,mail_payload,status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (body.id, digest, "", mode, requester_key, now, body.email, payload, json.dumps(mail), "pending"),
            )
            conn.execute(
                "INSERT INTO booking_rate_limits(key,count,expires) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET count=booking_rate_limits.count+1",
                (requester_key, 1, now + 86400),
            )
        # The complete plan is durable BEFORE contacting the email provider.
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        suffix = " FOR UPDATE" if conn.postgres else ""
        saved = conn.execute("SELECT * FROM date_bookings WHERE id=?" + suffix, (body.id,)).fetchone()
        if saved["status"] == "accepted":
            return {"sent": True, "delivery": saved["delivery_mode"]}
        if saved["delivery_mode"] != mode:
            raise HTTPException(409, "This draft belongs to a different delivery environment")
        # Resend retains idempotency keys for 24h. Fail closed before expiry if
        # acceptance remains uncertain; an operator must reconcile older drafts.
        if mode == "resend" and now - saved["created"] >= 23 * 3600:
            raise HTTPException(409, "Delivery needs manual review; do not submit a new copy")
        mail = json.loads(saved["mail_payload"])
        try:
            provider_id = send_email(conn, mail["recipients"], mail["subject"], mail["text"],
                                     f"plan/{body.id}", mail["html"], mail["sender"])
        except Exception as exc:
            log_failure("resend_send", exc)
            raise HTTPException(503, "Plan saved, but email acceptance was not confirmed. Retry this draft.") from None
        conn.execute("UPDATE date_bookings SET provider_id=?,status='accepted' WHERE id=?", (provider_id, body.id))
        conn.commit()
        logger.info("plan_delivery_accepted plan_id=%s mode=%s recipients=%s", body.id, mode, len(mail["recipients"]))
    return {"sent": True, "delivery": mode}


static_root = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parents[1] / "frontend" / "out"))
if static_root.is_dir():
    app.mount("/", StaticFiles(directory=static_root, html=True), name="frontend")
