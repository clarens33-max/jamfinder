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

## Instagram Agent (IN PROGRESS)

### Context
Adding a weekly autonomous Instagram poster to the existing Jam Finder app.
Full architecture discussion: [paste this conversation URL]

### What exists
- Python app on Railway
- In-memory event cache — plain dict in `main.py:18`: `cache = {"events": [], "last_updated": None}`. Each event: `uid`, `summary`, `location`, `date` (ISO string), `coords`, `games` (list of `{home, away, association, gameType}` — populated only when TOaST login succeeds), `address`, `timings`, plus flags: `is5N`, `tier`, `isScrim`, `isRookie`, `isMRDA`, `isOTA`, `isWFTDA`, `isJunior`, `isTournament`
- Overnight Toast scraper

### What we're building
- APScheduler cron job (Thursday 9am UK)
- Playwright HTML → PNG image generator (one slide per event + CTA)
- Meta Graph API carousel publisher
- Temporary Railway static file serving for image hosting

### Key decisions made
- Agent lives inside the existing Railway service, not separate
- Reads directly from existing in-memory cache, no DB or API needed
- Playwright not Puppeteer (Python stack)
- Image hosting via temporary route on own app (no extra storage bucket)

### Files created
- `instagram_agent/poster.py` — scheduler entry point, event filtering, retry logic
- `instagram_agent/image_gen.py` — Playwright HTML→PNG slide generator
- `instagram_agent/caption.py` — caption builder with puns + @handle lookups
- `instagram_agent/instagram_api.py` — Meta Graph API client (dry-run when token absent)
- `instagram_agent/team_handles.json` — team name → @instagram map (add handles here)
- `static/ig_tmp/` — temp PNG hosting for Meta image fetch (auto-cleaned after publish)

### Railway env vars needed
```
META_ACCESS_TOKEN
INSTAGRAM_BUSINESS_ACCOUNT_ID
RAILWAY_PUBLIC_URL   # e.g. https://jamfinder-production.up.railway.app
```

### Railway deployment note — Playwright/Chromium
Playwright needs Chromium. In Railway dashboard, set one env var:
```
NIXPACKS_BUILD_CMD=pip install -r requirements.txt && playwright install chromium --with-deps
```
That replaces the default build command and installs the browser at deploy time.

### Manual setup checklist (one-time)

**1. Instagram account**
- Go to Instagram Settings → Account → Switch to Professional Account → Creator or Business

**2. Facebook Page**
- Create a Facebook Page (any name/category is fine)
- In Instagram Settings → Account → Linked Accounts → link to that Facebook Page

**3. Meta Developer App**
- Go to [developers.facebook.com](https://developers.facebook.com) → Create App → Business type
- Add product: **Instagram Graph API**
- Under App Settings → Basic: note your App ID

**4. App permissions**
- In the App dashboard → Instagram Graph API → add these permissions:
  - `instagram_basic`
  - `instagram_content_publish`
- Switch the app from **Development → Live mode** (top of the dashboard) — posts only work in Live mode

**5. System User token (doesn't expire — use this, not a personal token)**
- Go to [business.facebook.com](https://business.facebook.com) → Settings → System Users → Add
- Assign your Instagram account to the System User with `FULL_CONTROL`
- Generate a token for the System User, select your app, tick `instagram_basic` + `instagram_content_publish`
- Copy the token → this is your `META_ACCESS_TOKEN`

**6. Find your Instagram Business Account ID**
- Call: `GET https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_TOKEN`
- Then: `GET https://graph.facebook.com/v19.0/PAGE_ID?fields=instagram_business_account&access_token=YOUR_TOKEN`
- The `id` in `instagram_business_account` is your `INSTAGRAM_BUSINESS_ACCOUNT_ID`

**7. Railway env vars** — add in Railway dashboard → your service → Variables:
```
META_ACCESS_TOKEN
INSTAGRAM_BUSINESS_ACCOUNT_ID
RAILWAY_PUBLIC_URL   # e.g. https://jamfinder-production.up.railway.app
NIXPACKS_BUILD_CMD   # see Playwright note above
```

**8. Populate team handles**
- Edit `instagram_agent/team_handles.json` — map team names (as they appear in TOaST) to their Instagram @handle
- These are used for @mentions in the caption text
