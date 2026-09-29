Static audio for the invitation. Browser URLs start with /audio/.

Installed:
- no_first.mp3: owner-supplied Lawde Bhojyam recording, played for every NO catch.
- yes_date_song.mp3: owner-supplied WhatsApp recording, played when YES is reached.

Retained but not played by the direct game:
- login_right.mp3 and login_wrong.mp3: former sign-in clips.
- no_third_alarm.mp3: plays on opening the optional third-NO UPI prompt.

There are no substitute sounds. Each event points only to its intended file; if
that file is absent, the event is silent and the development console identifies
the missing path.

No unrelated sound is played for YES.

See root AUDIO_SOURCES.md for sources, licenses, and current inventory.
Public attribution is in CREDITS.txt. No silent placeholders are included.
# Audio packaging

Only `login_right.mp3` and `no_third_alarm.mp3` are currently distributable;
their attribution is in `CREDITS.txt`. User-supplied `login_wrong.mp3`,
`no_first.mp3`, and `yes_date_song.mp3` are intentionally omitted from source
control and production packaging until hosting/redistribution permission is
confirmed. The app stays silent for absent exact clips and logs the missing
path in browser developer output.
