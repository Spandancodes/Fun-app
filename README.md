# One Question

The page opens with a private invitation from Spandan. The visitor can read five optional replies, answer YES or NO directly, and leave freely after NO. A second and third deliberate NO play the existing clips; the third shows a fake ₹500 assessment with a free exit. YES plays the existing song and reveals the date-plan form. Nothing is booked or paid for.

Set the recipient's first name in **`frontend/lib/site.ts`**. Leave it blank for the generic “For you.” opening and “Hey.” greeting. This is the only place the recipient name is configured.

## Local development

Requires Node.js 22+ and Python 3.11+. From the repository root:

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Set `OWNER_EMAIL` in `backend/.env` if you want to test the optional plan form. In one terminal:

```sh
cd backend
set -a; source .env; set +a
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

In another:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. No invite or account is needed. With `MAIL_MODE=local`, a submitted plan goes only to the local SQLite outbox; inspect it with `backend/.venv/bin/python backend/mailbox.py --latest` from the repository root.

## Render deployment

The Docker build exports Next.js as static files and serves them with FastAPI on Render’s `PORT`. The invitation works as soon as the page loads. The date-plan API requires `DATABASE_URL`, `OWNER_EMAIL`, `MAIL_MODE=resend`, `RESEND_API_KEY`, and a verified `MAIL_FROM` address. Plans have a server-side daily rate limit and are sent to the validated guest email and configured `OWNER_EMAIL`. The production database should be durable PostgreSQL because Render Free disks are ephemeral.

The service configuration is in `render.yaml`. `APP_ORIGIN` is set to the custom domain, and the backend also accepts Render’s external hostname for same-origin POSTs. Put secrets in Render’s environment settings, never in the repository. When a new commit lands on the service’s linked branch, Render can deploy it automatically if Auto-Deploy is enabled. Verify the deployed commit on Render’s Deploys page.

`GET /health` checks that the server can serve the page and is the Render health check. `GET /health/plan` checks the optional date-plan database and mail configuration. The invitation remains available if plan delivery is not configured; plan submission returns 503 until the required environment settings above are present. For local development, `MAIL_MODE=local` and any valid test-only `OWNER_EMAIL` write plans to the SQLite outbox without sending email.

The YES screen checks `/api/plan/status` before showing the email form. When delivery is unavailable, it explains that the plan cannot be sent yet. A failed send keeps the entered draft on screen and reuses its submission ID on retry. The Render service must have a PostgreSQL database URL and a configured Resend account before email delivery can work; these values are not included in the repository.

### Supabase Postgres

Create a Supabase project, then open **Connect → Session pooler** and copy its PostgreSQL connection string. Use session mode on port 5432 for the long-running Render backend when an IPv4 connection is needed. Replace the password placeholder with your database password, percent-encoding reserved URL characters, and add `?sslmode=require` (or `&sslmode=require` if the string already has a query). Put the complete string only in Render's `DATABASE_URL` environment variable; never in Git, frontend variables, or chat. Do not use the transaction pooler on port 6543 with this app.

The backend automatically creates its tables in the private `itsdonebro` schema on first database connection. Keep that schema out of Supabase's **Exposed schemas** setting. The app uses the server-side PostgreSQL connection directly, so it needs no Supabase anon key, service-role key, or browser database client. Once `DATABASE_URL` is set, `/health/plan` will still report unavailable until `OWNER_EMAIL`, `MAIL_MODE=resend`, `RESEND_API_KEY`, and a verified `MAIL_FROM` are also configured. Check `/health/plan` after Render redeploys, then send a test plan only when it reports healthy.

`GET /health/db` checks the database connection separately. It should return 200 after `DATABASE_URL` is saved in Render, even before email delivery is configured.

If that check returns 503, run `backend/.venv/bin/python backend/check_database.py` from the repository root. Paste the complete `DATABASE_URL` from Render at its hidden prompt. The script checks the URI and tries a read-only connection, printing only a safe error category; it never prints or saves the password. A successful local connection with a failing Render health check means the value or deployment in Render differs from what you tested.

### Real plan delivery

The Yes screen collects a name and email with the proposed plan. Only **Send our plan** calls `POST /api/plan`; Yes, page loads, and edits never send mail. Local outbox and mocked tests never send real emails.

| Render variable | Purpose and source |
| --- | --- |
| `DATABASE_URL` | Supabase Connect → Session pooler URI, port 5432. URL-encode the password; add `sslmode=require`. Secret. |
| `OWNER_EMAIL` | Your recipient inbox, configured in Render. |
| `MAIL_MODE` | `resend` in production; `local` for development. |
| `RESEND_API_KEY` | Resend API Keys → a sending key for the verified domain. Secret. |
| `MAIL_FROM` | Sender on your Resend-verified subdomain, e.g. `It's Done Bro <plans@mail.example.com>`. |
| `APP_ORIGIN` | Comma-separated HTTPS origins. Render's external hostname is accepted automatically. |

Add a sending subdomain in Resend → Domains, then add only the exact DNS records Resend supplies for it (DNS-only for CNAMEs). Keep website and main-domain mail records unchanged. Click Verify DNS Records and wait for Verified; use an address on that domain as MAIL_FROM. Do not guess DNS values: they vary by region/provider. Store secrets only in ignored local `.env` and Render Environment, then Save, rebuild, and deploy.

The backend migrates its private `itsdonebro` schema once per process. For manual migration, paste `backend/migrations/001_date_plan_delivery.sql` into Supabase SQL Editor and run it. Keep the schema out of Exposed schemas. Check `/health/db` and `/health/plan` for 200. The latter checks configuration/storage, not domain verification or inbox arrival. `X-App-Commit` identifies the deployed commit when Render provides `RENDER_GIT_COMMIT`.

Plans are committed with `pending` status, complete payload, guest email, and immutable email payload **before** sending. Row locks and a stable `plan/<submission UUID>` Resend key prevent duplicate sends. Accepted rows return their stored result. Provider/network failures keep the draft retryable with the same UUID. Success requires a provider email ID and a successful database commit. Logs contain only stage, exception type, SQLSTATE, HTTP status, plan UUID, mode, and recipient count; no passwords, API keys, URLs, addresses, or message contents.

Resend keys last 24 hours; uncertain drafts older than 23 hours fail closed (409) for manual review in Resend Emails. There is no automatic retry worker. A timeout or database failure after provider acceptance can need manual reconciliation. A 200 means accepted by Resend, not proof of inbox receipt. Test only with an address you control, inspect Resend's delivery status, then check both inboxes including spam. Never use the intended guest's email for setup tests.

The form validates email syntax but does not verify mailbox ownership; keep this invitation private. A changed plan receives a new UUID. After an unconfirmed send, retry the same draft instead of creating another copy.

Optional Postgres test (from backend, disposable localhost database only):

```sh
TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1:55439/postgres .venv/bin/python -m pytest -q tests/test_postgres.py
```

## Audio

See [AUDIO_SOURCES.md](AUDIO_SOURCES.md). The owner confirmed public hosting permission for the uploaded recordings. All five MP3s are included in Git and Docker. First and second NO play `/audio/no_first.mp3`, third NO plays `/audio/no_third_alarm.mp3`, and YES plays `/audio/yes_date_song.mp3`. The page has a persistent sound toggle and a separate YES-song pause control. Build checks verify exact SHA-256 hashes before compilation and after static export; missing or changed audio fails the build. No external music link or substitute is used.

## Verification

```sh
cd backend && .venv/bin/python -m pytest -q
cd ../frontend && npm run typecheck && STATIC_EXPORT=true npm run build && npm test
```

The browser suite covers desktop and emulated mobile, all five replies, YES and NO paths, plan review and retry, missing audio, mute persistence, and free assessment dismissal. The backend suite covers plan validation, guest and owner delivery, rate limits, and provider idempotency.
