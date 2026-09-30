# Production audio inventory

The owner confirmed public hosting permission for the uploads on 2026-09-30. All five MP3 recordings are included in Git and Docker. The game opens without sign-in; login clips are retained but unused. Runtime failures remain silent with developer warnings. Build checks fail when an approved recording is missing or changed.

| Event | Browser path | Production status |
| --- | --- | --- |
| First and second NO | `/audio/no_first.mp3` | Included: authorized Lawde Bhojyam recording. |
| Third NO | `/audio/no_third_alarm.mp3` | Included; source and license in `frontend/public/audio/CREDITS.txt`. |
| YES | `/audio/yes_date_song.mp3` | Included: uploaded `WhatsApp Audio 2026-09-30 at 00.25.05.mpeg`; starts on YES with pause and volume controls. |

The YES copy is byte-for-byte identical to the supplied file (SHA-256 `ff6b1dbf15edf57bb4475fe0e796baca04c59432b92a28f8b588af4f01df0ac0`). There is no YouTube link or substitute music. Missing music produces a developer-console warning and leaves the celebration usable.

`frontend/scripts/check-audio.mjs` checks SHA-256 hashes before build and after static export, including inside Docker. The fake assessment graphic is non-scannable and cannot accept payment.
