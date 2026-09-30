# Production audio inventory

The game opens without sign-in. No login audio plays. Only clips with identified redistribution rights are included in the distributable image. Missing clips are reported in the browser console; the game continues without substitute sound.

| Event | Browser path | Production status |
| --- | --- | --- |
| First and second NO | `/audio/no_first.mp3` | Omitted pending redistribution permission for the supplied clip. |
| Third NO | `/audio/no_third_alarm.mp3` | Included; source and license in `frontend/public/audio/CREDITS.txt`. |
| YES | `/audio/yes_date_song.mp3` | Local copy of the uploaded `WhatsApp Audio 2026-09-30 at 00.25.05.mpeg`; starts on YES with pause and volume controls. The existing public-distribution filter still excludes this recording. |

The YES copy is byte-for-byte identical to the supplied file (SHA-256 `ff6b1dbf15edf57bb4475fe0e796baca04c59432b92a28f8b588af4f01df0ac0`). There is no YouTube link or substitute music. Missing music produces a developer-console warning and leaves the celebration usable.

To add the omitted NO clip, provide an authorized MP3 copy at `frontend/public/audio/no_first.mp3` and update the Dockerfile’s distribution filter once redistribution is permitted. The fake assessment graphic is non-scannable and cannot accept payment.
