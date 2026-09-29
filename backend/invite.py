"""Add or update an invited guest without publishing the invite list."""

import argparse
import secrets
import sqlite3

from main import db, normalize_email

parser = argparse.ArgumentParser(description="Add or update an invited guest")
parser.add_argument("--name", required=True)
parser.add_argument("--email", required=True)
args = parser.parse_args()
name = args.name.strip()
if not 1 <= len(name) <= 80:
    parser.error("Name must contain 1–80 characters")
try:
    email = normalize_email(args.email)
except ValueError as exc:
    parser.error(str(exc))
try:
    with db() as conn:
        existing = conn.execute("SELECT id FROM guests WHERE name=?", (name.casefold(),)).fetchone()
        if existing:
            conn.execute("UPDATE guests SET display_name=?, email=? WHERE id=?",
                         (name, email, existing["id"]))
            conn.execute("DELETE FROM sessions WHERE guest_id=?", (existing["id"],))
        else:
            conn.execute("INSERT INTO guests(name,display_name,salt,digest,email) "
                         "VALUES (?,?,?,?,?)",
                         (name.casefold(), name, secrets.token_hex(16),
                          secrets.token_hex(32), email))
except Exception as exc:
    if isinstance(exc, sqlite3.IntegrityError) or exc.__class__.__name__ == "UniqueViolation":
        parser.error("That email is already assigned to another invited guest")
    raise
print(f"Invite saved for {name} <{email}>.")
