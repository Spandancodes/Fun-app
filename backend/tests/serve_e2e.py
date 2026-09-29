"""Disposable test server. Never touches the normal invite database."""
import os
import tempfile
from pathlib import Path
import uvicorn
from main import db

results = Path(__file__).resolve().parents[2] / "frontend" / "test-results"
results.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="bro-e2e-", dir=results) as folder:
    os.environ["DATABASE_PATH"] = folder + "/test.sqlite3"
    os.environ["MAIL_MODE"] = "local"
    os.environ["OWNER_EMAIL"] = "owner@example.test"
    os.environ["SESSION_SIGNING_SECRET"] = "test-only-signing-secret-should-be-over-32-chars"
    with db() as conn:
        conn.execute("INSERT INTO guests(name,display_name,salt,digest,email) VALUES (?,?,?,?,?)",
                     ("test guest", "Test Guest", "unused", "unused", "guest@example.test"))
    marker = results / "e2e-db-path"
    marker.write_text(os.environ["DATABASE_PATH"])
    try:
        uvicorn.run("main:app", host="127.0.0.1", port=8001)
    finally:
        marker.unlink(missing_ok=True)
