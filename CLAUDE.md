# Jam Finder

Community viewer for UK roller derby events. Fetches data overnight from [rollerderby.directory](https://rollerderby.directory) (TOaST — The Tournament OfficiAls Season Tracker) and presents it in a readable format. Not for volunteering — purely for the community to see where games are happening.

## Architecture

Single Python service deployed on Railway.

```
main.py          FastAPI app + APScheduler (3am UTC daily refresh)
scraper.py       ICS fetch, parse, classify, geocode
static/index.html  Frontend — same design as original, fetches /api/events
requirements.txt
Procfile         Railway entry point
```

**Data flow:** `rollerderby.directory/calendar.ics` → `scraper.py` parses + classifies + geocodes → cached in memory → `/api/events` serves JSON → frontend renders.

No database. Data lives in memory; refreshed on startup and nightly. No persistent volume needed.

## Running locally

```bash
pip install -r requirements.txt
python main.py
# visit http://localhost:8000
```

Force a data refresh without restarting:
```
GET /api/refresh
```

## Deploying to Railway

Push to GitHub → connect repo in Railway → Nixpacks auto-detects Python + Procfile. No env vars required. Railway injects `PORT` automatically.

## Key files

- `scraper.py` — ICS parsing, event classification (5 Nations, tiers, rookie, MRDA, junior, scrim, tournament), geocoding via hardcoded UK city coords lookup
- `main.py` — FastAPI lifespan starts scheduler; `/api/events` returns `{events, last_updated, count}`
- `static/index.html` — Leaflet map, timeline, and by-location views; Oswald + Inter fonts; pink (#E91E8C) accent

## Data source

`https://rollerderby.directory/calendar.ics` — publicly accessible ICS feed, no auth needed. Contains ~100 events per season (April–November). Event classification is regex-based on the SUMMARY field.

## Adding new cities

Edit the `COORDS` dict in `scraper.py`. Keys are lowercase city names.
