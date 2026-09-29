# Production audio inventory

The deployment includes only assets with an identified redistribution license.
When a referenced exact clip is absent, the event stays silent and the browser
console identifies the missing path. No audio substitute is used.

| Event | Browser path | Production status |
| --- | --- | --- |
| Correct sign-in, after link verification | `/audio/login_right.mp3` | Included; attribution and CC BY 4.0 source in `frontend/public/audio/CREDITS.txt`. |
| Wrong sign-in | `/audio/login_wrong.mp3` | Not included: user-provided meme audio; redistribution permission is unconfirmed. |
| First and second NO | `/audio/no_first.mp3` | Not included: user-provided “Lavde me bhojyam.mpeg”; redistribution permission is unconfirmed. |
| Third NO | `/audio/no_third_alarm.mp3` | Included; attribution and CC BY 4.0 source in `frontend/public/audio/CREDITS.txt`. |
| YES | Official player link to Rihanna, “Don’t Stop the Music” | No track file redistributed. |

To include the omitted clips, supply a copy that you are authorized to host and
confirm redistribution rights. Install them respectively as
`frontend/public/audio/login_wrong.mp3` and `frontend/public/audio/no_first.mp3`.
Do not include the user-uploaded WhatsApp music recording without permission;
the app does not play it. The fake assessment graphic is non-scannable and
cannot initiate or accept payment.
