# Thanisha, It’s Done Bro

The page opens directly on a 7×7 snake ballot. Catch YES for the acceptance screen, or catch NO three times for a fictional ₹500 assessment with a free exit. There is no sign-in or email gate. A date-plan form appears only after YES; the guest reviews it and explicitly sends it to Spandan’s configured address. It does not book a calendar event or collect payment.

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

The Docker build exports Next.js as static files and serves them with FastAPI on Render’s `PORT`. The snake game works as soon as the page loads. The date-plan API requires `DATABASE_URL`, `OWNER_EMAIL`, `MAIL_MODE=resend`, `RESEND_API_KEY`, and a verified `MAIL_FROM` address. Plans have a server-side daily rate limit and are sent only to `OWNER_EMAIL`; the guest cannot choose a recipient. The production database should be durable PostgreSQL because Render Free disks are ephemeral.

The service configuration is in `render.yaml`. `APP_ORIGIN` is set to the custom domain, and the backend also accepts Render’s external hostname for same-origin POSTs. Put secrets in Render’s environment settings, never in the repository. When a new commit lands on the service’s linked branch, Render can deploy it automatically if Auto-Deploy is enabled. Verify the deployed commit on Render’s Deploys page.

`GET /health` checks that the server can serve the game and is the Render health check. `GET /health/plan` checks the optional date-plan database and mail configuration. The game remains available if plan delivery is not configured; plan submission returns 503 until the required environment settings above are present. For local development, `MAIL_MODE=local` and any valid test-only `OWNER_EMAIL` write plans to the SQLite outbox without sending email.

The YES screen checks `/api/plan/status` before showing the email form. When plan delivery is unavailable, it directs visitors to the existing Instagram link. A failed send keeps the entered draft on screen and says explicitly that no email was sent. The Render service must have a PostgreSQL database URL and a configured Resend account before email delivery can work; these values are not included in the repository.

## Audio

See [AUDIO_SOURCES.md](AUDIO_SOURCES.md). The owner confirmed public hosting permission for the uploaded recordings. All five MP3s are included in Git and Docker. YES plays `/audio/yes_date_song.mp3` with pause and volume controls. Build checks verify exact SHA-256 hashes before compilation and after static export; missing or changed audio fails the build. No external music link or substitute is used.

## Verification

```sh
cd backend && .venv/bin/pytest -q
cd ../frontend && npm run typecheck && STATIC_EXPORT=true npm run build && npm test
```

The browser suite covers desktop and emulated mobile input, direct board entry without sign-in, YES and NO paths, plan review, missing audio, and free assessment dismissal. The backend suite covers plan validation, owner-only delivery, rate limits, and provider idempotency.
