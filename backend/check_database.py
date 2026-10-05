"""Check a Supabase Postgres URI without displaying or storing its password."""

from getpass import getpass
from urllib.parse import urlsplit

import psycopg


def check_uri_shape(uri: str) -> str | None:
    try:
        parts = urlsplit(uri)
        port = parts.port
    except ValueError:
        return "The URI is malformed (check brackets, host, and port)."
    if parts.scheme not in {"postgres", "postgresql"}:
        return "The URI must start with postgresql://."
    if not parts.username or not parts.password or not parts.hostname:
        return "The URI needs a username, password, and host."
    if "[YOUR-PASSWORD]" in uri or "YOUR_PASSWORD" in uri:
        return "Replace the password placeholder with your actual database password."
    if parts.username != "postgres.xvfzppjtikkqnpbqdhxi":
        return "The Session pooler username does not match this Supabase project."
    if not parts.hostname.endswith(".pooler.supabase.com"):
        return "Use the Session pooler host from Supabase Connect."
    if parts.username.startswith("postgres.") and port != 5432:
        return "The Session pooler URI should use port 5432."
    if parts.path != "/postgres":
        return "The database path should be /postgres."
    return None


def main() -> int:
    print("Paste the full database URI from Render. Input is hidden and never saved.")
    uri = getpass("DATABASE_URL: ").strip()
    problem = check_uri_shape(uri)
    if problem:
        print(problem)
        return 1
    try:
        with psycopg.connect(uri, connect_timeout=10) as connection:
            connection.execute("SELECT 1").fetchone()
            schema_exists = connection.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'itsdonebro')"
            ).fetchone()[0]
    except psycopg.Error as exc:
        code = exc.sqlstate or "none"
        if code == "28P01":
            reason = "Password authentication failed. Check the current Supabase database password."
        elif code == "3D000":
            reason = "The database name is incorrect."
        elif code == "42501":
            reason = "The database user lacks permission."
        else:
            reason = f"Connection failed ({type(exc).__name__}, SQLSTATE {code}). Check the host and pooler mode."
        print(reason)
        return 1
    print("Connection works. The itsdonebro schema " + ("exists." if schema_exists else "is missing."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
