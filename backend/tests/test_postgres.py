"""Opt-in integration against disposable, localhost-only Postgres."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from main import app, db


def test_postgres_save_before_send_and_concurrent_duplicates(monkeypatch):
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to disposable localhost Postgres")
    assert urlsplit(url).hostname in {"127.0.0.1", "localhost"}
    import psycopg
    from psycopg import sql
    name = "bro_test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    monkeypatch.setenv("DATABASE_URL", url.rsplit("/", 1)[0] + "/" + name)
    monkeypatch.delenv("RENDER", raising=False)
    for key, value in {"MAIL_MODE": "resend", "OWNER_EMAIL": "owner@example.test", "RESEND_API_KEY": "test-only", "MAIL_FROM": "Plan <plan@example.test>", "APP_ORIGIN": "http://localhost:3000"}.items():
        monkeypatch.setenv(key, value)
    draft = {"email": "guest@example.test", "id": str(uuid.uuid4()), "when": "Friday", "area": "Park", "outing": "Walk"}
    calls = []
    def post(*args, **kwargs):
        with db() as conn:
            saved = conn.execute("SELECT payload,status FROM date_bookings WHERE id=?", (draft["id"],)).fetchone()
            assert saved["status"] == "pending"
            assert "guest@example.test" in saved["payload"]
        calls.append(kwargs)
        return type("Accepted", (), {"raise_for_status": lambda self: None, "json": lambda self: {"id": "postgres-test-accepted"}})()
    monkeypatch.setattr("main.httpx.post", post)
    try:
        with db() as conn:
            conn.executescript(Path("migrations/001_date_plan_delivery.sql").read_text())
        with TestClient(app) as client:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: client.post("/api/plan", headers={"Origin": "http://localhost:3000"}, json=draft), range(2)))
            assert [r.status_code for r in responses] == [200, 200]
            assert len(calls) == 1
            assert client.get("/health/db").status_code == 200
        with db() as conn:
            saved = conn.execute("SELECT status,provider_id FROM date_bookings WHERE id=?", (draft["id"],)).fetchone()
            assert saved == {"status": "accepted", "provider_id": "postgres-test-accepted"}
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
