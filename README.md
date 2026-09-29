# Thanisha, It’s Done Bro

A small private-invitation game: a 7×7 snake ballot, an absurd three-NO
recount, a fake non-scannable ₹500 assessment with a free exit, and a date-plan
email form after YES. It does not collect payments. The site title and service
name are **Thanisha, It’s Done Bro**.

## Local development

Requirements: Node 22+ and Python 3.11+.

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Set a local organizer address in `backend/.env` (`OWNER_EMAIL`). In one
terminal, start the API:

```sh
cd backend
set -a; source .env; set +a
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. `MAIL_MODE=local` records email in SQLite without
sending it; inspect the latest messages with `backend/.venv/bin/python
backend/mailbox.py --latest` from the repository root.

## Inviting a guest

Configure `DATABASE_PATH` for local use (or `DATABASE_URL` for PostgreSQL),
then run:

```sh
cd backend
.venv/bin/python invite.py --name 'Guest Name' --email 'guest@example.com'
```

The list remains server-side and is never returned by the API. Sign-in always
uses a short-lived, one-use email link; an email address alone is not treated as
verified.

## Email delivery

Local mode writes to a development outbox only. Production uses Resend's email
API after the sender address/domain is verified. A submitted date plan goes to
the organizer and the email from the verified session, only after the guest
reviews and presses **Send our plan**. The form cannot choose recipient
addresses. Provider acceptance is reported as acceptance, not as a confirmed
calendar booking. Resend DNS verification records are separate from the site
CNAME.

## Free Render deployment

The Docker build runs Next.js with static export (`STATIC_EXPORT=true`) and
FastAPI serves the export plus `/api/*` on one origin. It binds to Render's
`PORT`. SQLite is development-only; production startup requires a durable
PostgreSQL `DATABASE_URL` because Render Free disks and Render's free database
are not persistent long-term. Use a free external PostgreSQL provider whose
limits fit this private app. Render's free web service can sleep after
inactivity, so the first visit after a quiet period may wait for a cold start.

Copy `.env.example` as a reference only; enter actual values into Render's
environment settings, never commit secrets. Render Free configuration is in
`render.yaml`; deploy the Dockerfile from the repository root. Required secrets
are listed in that file with `sync: false`.

Custom domain: add `itsdonebro.spandanghosal.in` in the service's Render
Custom Domains panel and use the exact CNAME target Render displays. The
`itsdonebro` DNS record is independent of any Resend sender-verification
records. Do not alter nameservers, apex, `www`, or existing mail records.

## Audio

See [AUDIO_SOURCES.md](AUDIO_SOURCES.md). Production includes only the
attributed “Yaay boy” sign-in success clip and bank-vault alarm. User-supplied
meme/song files whose distribution rights are unclear are excluded, leaving
their exact events silent. Supply authorized copies of the Gyanesh clip and
“Lawde Bhojyam” clip if you have permission to host them. YES links to Rihanna's
official video on YouTube; the site does not redistribute the track.

## Verification

```sh
cd backend && .venv/bin/pytest -q
cd ../frontend && npm run typecheck && STATIC_EXPORT=true npm run build && npm test
```

Playwright starts a disposable local API/database and tests desktop and mobile
controls, authentication UI, the YES plan-review flow, missing-audio silence,
three NO catches, alarm-only third catch, scanner safety, and free dismissal.
