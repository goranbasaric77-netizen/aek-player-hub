# AEK Player Hub

Daily app for AEK Athens FC players: today's plan, the morning check-in and three rings to close
(check-in, session, gym). Built by the performance department.

- `index.html` is the whole app (one file, no build step). `photos/` holds the player portraits, `crest.webp` the club crest.
- `config.js` holds the backend URL. Empty URL = sketch mode with demo data. With a URL the app runs live.
- `backend/Code.gs` is the Google Apps Script that stores everything in a Google Sheet. `backend/UPUTSTVO.md` explains the one-time setup.
- `bridge/player_hub_feed.py` publishes each day's targets and results from the AEK GPS 2.5 data to the hub.
- `manifest.webmanifest`, `sw.js` and the icons make it installable on a phone (add to home screen).

Publish a new version: edit, then `git add -A && git commit -m "..." && git push`. Bump `CACHE` in `sw.js` when `index.html` changes, so phones pick up the new build.
