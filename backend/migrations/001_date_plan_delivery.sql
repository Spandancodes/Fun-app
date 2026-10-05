-- Optional dashboard migration. The backend applies these additions automatically.
-- Keep itsdonebro out of Supabase's exposed schemas.
BEGIN;
CREATE SCHEMA IF NOT EXISTS itsdonebro;
CREATE TABLE IF NOT EXISTS itsdonebro.date_bookings (
  id TEXT PRIMARY KEY, payload_digest TEXT NOT NULL, provider_id TEXT NOT NULL,
  delivery_mode TEXT NOT NULL, requester_key TEXT NOT NULL,
  created DOUBLE PRECISION NOT NULL
);
ALTER TABLE itsdonebro.date_bookings ADD COLUMN IF NOT EXISTS guest_email TEXT;
ALTER TABLE itsdonebro.date_bookings ADD COLUMN IF NOT EXISTS payload TEXT;
ALTER TABLE itsdonebro.date_bookings ADD COLUMN IF NOT EXISTS mail_payload TEXT;
ALTER TABLE itsdonebro.date_bookings ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'accepted';
CREATE TABLE IF NOT EXISTS itsdonebro.booking_rate_limits (
  key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS itsdonebro.outbox (
  id TEXT PRIMARY KEY, recipients TEXT NOT NULL,
  subject TEXT NOT NULL, body TEXT NOT NULL, created DOUBLE PRECISION NOT NULL
);
COMMIT;
