import json
import re
import sqlite3
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app, db

ORIGIN = {"Origin": "http://localhost:3000"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("MAIL_MODE", "local")
    monkeypatch.setenv("OWNER_EMAIL", "spandan@example.test")
    monkeypatch.setenv("SESSION_SIGNING_SECRET", "test-only-signing-secret-should-be-over-32-chars")
    with db() as conn:
        conn.execute(
            "INSERT INTO guests(name,display_name,salt,digest,email) VALUES (?,?,?,?,?)",
            ("test guest", "Test Guest", "unused", "unused", "guest@example.test"),
        )
    with TestClient(app, follow_redirects=False) as session:
        yield session


def request_link(client, name="Test Guest", email="guest@example.test"):
    return client.post("/api/login", headers=ORIGIN, json={"name": name, "email": email})


def latest_link():
    with db() as conn:
        body = conn.execute(
            "SELECT body FROM outbox WHERE subject LIKE '%sign-in%' ORDER BY created DESC LIMIT 1"
        ).fetchone()["body"]
    return re.search(r"http://localhost:3000/api/verify\?token=[^\s]+", body).group()


def verify_link(client):
    assert request_link(client).status_code == 202
    link = latest_link()
    response = client.get(link.replace("http://localhost:3000", ""))
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:3000/?link=verified"
    return link


def test_email_link_is_private_short_lived_and_one_use(client):
    assert client.get("/api/session").status_code == 401
    wrong = request_link(client, "Test Guest", "other@example.test")
    right = request_link(client)
    assert wrong.status_code == right.status_code == 202
    assert wrong.json() == right.json()
    with db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1
    link = latest_link()
    assert "guest@example.test" not in link
    assert client.get("/api/session").status_code == 401
    assert client.get(link.replace("http://localhost:3000", "")).status_code == 303
    assert client.get("/api/session").json() == {"display_name": "Test Guest"}
    assert client.get(link.replace("http://localhost:3000", "")).headers["location"].endswith(
        "?link=invalid"
    )
    assert client.post("/api/logout", headers=ORIGIN).status_code == 200
    assert client.get("/api/session").status_code == 401
    assert request_link(client).status_code == 202
    with db() as conn:
        conn.execute("UPDATE login_links SET expires=?", (time.time() - 1,))
    assert client.get(latest_link().replace("http://localhost:3000", "")).headers[
        "location"
    ].endswith("?link=invalid")


def test_plan_is_public_owner_only_and_idempotent(client):
    assert client.get("/api/session").status_code == 401
    draft = {
        "id": str(uuid.uuid4()),
        "when": "Saturday afternoon",
        "area": "South Kolkata",
        "outing": "Coffee and a walk",
        "note": "Somewhere quiet",
    }
    assert client.post("/api/plan", json=draft).status_code == 403
    assert client.post(
        "/api/plan", headers=ORIGIN, json={**draft, "to": "attacker@example.test"}
    ).status_code == 422
    result = client.post("/api/plan", headers=ORIGIN, json=draft)
    assert result.status_code == 200 and result.json() == {"sent": True, "delivery": "local"}
    assert client.post("/api/plan", headers=ORIGIN, json=draft).status_code == 200
    assert client.post(
        "/api/plan", headers=ORIGIN, json={**draft, "area": "Elsewhere"}
    ).status_code == 409
    with db() as conn:
        mail = conn.execute(
            "SELECT recipients,body FROM outbox WHERE subject LIKE 'A date plan%'"
        ).fetchall()
    assert len(mail) == 1
    assert json.loads(mail[0]["recipients"]) == ["spandan@example.test"]
    assert "Saturday afternoon" in mail[0]["body"]
    assert "Somewhere quiet" in mail[0]["body"]


def test_plan_failure_keeps_retry_available_and_rate_limit(client, monkeypatch):
    assert client.get("/api/session").status_code == 401
    draft = {"id": str(uuid.uuid4()), "when": "Friday", "area": "Park",
             "outing": "Walk", "note": ""}
    monkeypatch.delenv("OWNER_EMAIL")
    assert client.post("/api/plan", headers=ORIGIN, json=draft).status_code == 503
    monkeypatch.setenv("OWNER_EMAIL", "spandan@example.test")
    assert client.post("/api/plan", headers=ORIGIN, json=draft).status_code == 200
    for _ in range(2):
        assert client.post(
            "/api/plan", headers=ORIGIN, json={**draft, "id": str(uuid.uuid4())}
        ).status_code == 200
    assert client.post(
        "/api/plan", headers=ORIGIN, json={**draft, "id": str(uuid.uuid4())}
    ).status_code == 429


def test_resend_acceptance_and_idempotency_key(client, monkeypatch):
    assert client.get("/api/session").status_code == 401
    monkeypatch.setenv("MAIL_MODE", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("MAIL_FROM", "Invite <invite@example.test>")
    calls = []

    class Accepted:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "provider-accepted-1"}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Accepted()

    monkeypatch.setattr("main.httpx.post", fake_post)
    draft = {"id": str(uuid.uuid4()), "when": "Friday", "area": "Park",
             "outing": "Walk", "note": ""}
    assert client.post("/api/plan", headers=ORIGIN, json=draft).status_code == 200
    assert client.post("/api/plan", headers=ORIGIN, json=draft).status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == "https://api.resend.com/emails"
    assert calls[0][1]["headers"]["Idempotency-Key"] == f"plan/{draft['id']}"
    assert calls[0][1]["json"]["to"] == ["spandan@example.test"]


def test_existing_password_database_migrates_without_losing_guest(tmp_path, monkeypatch):
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.executescript("""
          CREATE TABLE guests (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL, salt TEXT NOT NULL, digest TEXT NOT NULL
          );
          CREATE TRIGGER single_recipient BEFORE INSERT ON guests
          WHEN EXISTS (SELECT 1 FROM guests)
          BEGIN SELECT RAISE(ABORT, 'one person'); END;
          INSERT INTO guests(name,display_name,salt,digest)
          VALUES ('thanisha','Thanisha','old','old');
        """)
    monkeypatch.setenv("DATABASE_PATH", str(database))
    with db() as conn:
        row = conn.execute("SELECT name,display_name,email FROM guests").fetchone()
        assert (row["name"], row["display_name"], row["email"]) == (
            "thanisha", "Thanisha", None
        )
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='single_recipient'"
        ).fetchone() is None


def test_game_health_does_not_depend_on_optional_plan_configuration(client, monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/plan").status_code == 503
    assert client.get("/api/plan/status").status_code == 503
    draft = {"id": str(uuid.uuid4()), "when": "Friday", "area": "Park", "outing": "Walk"}
    assert client.post("/api/plan", headers=ORIGIN, json=draft).status_code == 503
