import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

app = FastAPI(title="The Great No Chase", docs_url=None, redoc_url=None, openapi_url=None)
COOKIE = "bro_session"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
POSTGRES_SCHEMA = """
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
CREATE INDEX IF NOT EXISTS guests_email_unique ON guests(email);
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

        raw = psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10)
        conn = DatabaseConnection(raw, postgres=True)
        try:
            conn.executescript(POSTGRES_SCHEMA)
            raw.execute("ALTER TABLE guests ADD COLUMN IF NOT EXISTS email TEXT")
            raw.execute("ALTER TABLE date_bookings ADD COLUMN IF NOT EXISTS delivery_mode TEXT NOT NULL DEFAULT 'local'")
            raw.execute("ALTER TABLE plans ADD COLUMN IF NOT EXISTS delivery_mode TEXT NOT NULL DEFAULT 'local'")
            conn.commit()
            yield conn
            conn.commit()
        except Exception:
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
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


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
               body: str, key: str) -> str:
    mode = os.getenv("MAIL_MODE", "local").lower()
    if mode == "local":
        conn.execute(
            "INSERT OR IGNORE INTO outbox VALUES (?,?,?,?,?)",
            (key, json.dumps(recipients), subject, body, time.time()),
        )
        return key
    if mode != "resend":
        raise RuntimeError("MAIL_MODE must be local or resend")
    api_key = os.getenv("RESEND_API_KEY")
    sender = os.getenv("MAIL_FROM")
    if not api_key or not sender:
        raise RuntimeError("RESEND_API_KEY and MAIL_FROM are required")
    result = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Idempotency-Key": key},
        json={"from": sender, "to": recipients, "subject": subject, "text": body},
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


@app.get("/health/plan")
def plan_health():
    try:
        if os.getenv("RENDER"):
            if not os.getenv("DATABASE_URL", "").strip():
                raise RuntimeError("DATABASE_URL is required for plan delivery")
            if os.getenv("MAIL_MODE", "").lower() != "resend":
                raise RuntimeError("MAIL_MODE must be resend in production")
            if not os.getenv("RESEND_API_KEY") or not os.getenv("MAIL_FROM"):
                raise RuntimeError("Email provider is not configured")
            normalize_email(os.getenv("OWNER_EMAIL", ""))
        with db():
            pass
    except Exception:
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
    when: str = Field(min_length=1, max_length=100)
    area: str = Field(min_length=1, max_length=100)
    outing: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)

    @field_validator("when", "area", "outing", "note")
    @classmethod
    def clean(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        if info.field_name != "note" and not value:
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


@app.post("/api/plan")
def send_plan(body: PlanRequest, request: Request):
    check_origin(request)
    if os.getenv("RENDER") and not os.getenv("DATABASE_URL", "").strip():
        raise HTTPException(503, "Plan storage is not configured")
    owner_email = os.getenv("OWNER_EMAIL", "").strip()
    try:
        owner_email = normalize_email(owner_email)
    except ValueError:
        raise HTTPException(503, "Plan email is not configured") from None
    now = time.time()
    requester_key = token_hash(request.client.host if request.client else "local")
    content = {"when": body.when, "area": body.area,
               "outing": body.outing, "note": body.note}
    digest = token_hash(json.dumps(content, sort_keys=True))
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT * FROM date_bookings WHERE id=?", (body.id,)).fetchone()
        if existing:
            if existing["requester_key"] != requester_key or existing["payload_digest"] != digest:
                raise HTTPException(409, "This submission ID belongs to another draft")
            return {"sent": True, "delivery": existing["delivery_mode"]}
        conn.execute("DELETE FROM booking_rate_limits WHERE expires < ?", (now,))
        attempt = conn.execute("SELECT count FROM booking_rate_limits WHERE key=?", (requester_key,)).fetchone()
        if attempt and attempt["count"] >= 3:
            raise HTTPException(429, "Plan limit reached for today")
        message = (
            "THE GREAT NO CHASE — DATE PLAN\n\n"
            "From: Thanisha\n"
            f"Preferred day or time: {body.when}\n"
            f"Area or location: {body.area}\n"
            f"Type of outing: {body.outing}\n"
            f"Note: {body.note or 'None'}\n\n"
            "Sent after the guest reviewed and submitted this plan."
        )
        try:
            provider_id = send_email(conn, [owner_email], "A date plan from Thanisha",
                                     message, f"plan/{body.id}")
        except Exception as exc:
            print(f"Plan email was not accepted: {type(exc).__name__}", flush=True)
            raise HTTPException(503, "Could not send the plan. Please retry.") from None
        delivery_mode = os.getenv("MAIL_MODE", "local").lower()
        conn.execute("INSERT INTO date_bookings VALUES (?,?,?,?,?,?)",
                     (body.id, digest, provider_id, delivery_mode, requester_key, now))
        conn.execute(
            "INSERT INTO booking_rate_limits(key,count,expires) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET count=booking_rate_limits.count+1",
            (requester_key, 1, now + 86400),
        )
    return {"sent": True, "delivery": delivery_mode}




static_root = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parents[1] / "frontend" / "out"))
if static_root.is_dir():
    app.mount("/", StaticFiles(directory=static_root, html=True), name="frontend")
