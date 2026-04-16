import asyncio
import logging
import os
import re
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TOAST_BASE = "https://rollerderby.directory"
ICS_URL = f"{TOAST_BASE}/calendar.ics"

COORDS = {
    'hull': [53.7457, -0.3367],
    'cheltenham': [51.8994, -2.0783],
    'belfast': [54.5973, -5.9301],
    'guildford': [51.2362, -0.5704],
    'havant': [50.8561, -1.0059],
    'portsmouth': [50.8148, -1.0877],
    'cardiff': [51.4816, -3.1791],
    'london': [51.5074, -0.1278],
    'waterford': [52.2593, -7.1101],
    'ireland': [53.4129, -8.2439],
    'bideford': [51.0167, -4.2000],
    'glasgow': [55.8642, -4.2518],
    'kirkwall': [58.9809, -2.9600],
    'orkney': [58.9809, -2.9600],
    'manchester': [53.4808, -2.2426],
    'edinburgh': [55.9533, -3.1883],
    'bournemouth': [50.7192, -1.8808],
    'sheffield': [53.3811, -1.4701],
    'gloucester': [51.8640, -2.2441],
    'liverpool': [53.4084, -2.9916],
    'stoke': [53.0027, -2.1794],
    'stoke on trent': [53.0027, -2.1794],
    'stoke-on-trent': [53.0027, -2.1794],
    'bedford': [52.1386, -0.4667],
    'york': [53.9600, -1.0800],
    'durham': [54.7761, -1.5733],
    'bristol': [51.4545, -2.5879],
    'nottingham': [52.9548, -1.1581],
    'haywards heath': [51.0047, -0.0960],
    'andover': [51.2083, -1.4833],
    'high wycombe': [51.6283, -0.7483],
    'wycombe': [51.6283, -0.7483],
    'keynsham': [51.4136, -2.4904],
    'merthyr': [51.7461, -3.3762],
    'birmingham': [52.4862, -1.8904],
    'salford': [53.4875, -2.2901],
    'newcastle upon tyne': [54.9783, -1.6178],
    'newcastle': [54.9783, -1.6178],
    'gateshead': [54.9526, -1.6014],
    'flint': [53.2484, -3.1367],
    'chelmsford': [51.7356, 0.4685],
    'barrow-in-furness': [54.1108, -3.2266],
    'barrow': [54.1108, -3.2266],
    'herne bay': [51.3737, 1.1213],
    'neath': [51.6602, -3.8067],
    'cambridge': [52.2053, 0.1218],
    'oxford': [51.7520, -1.2577],
    'maidstone': [51.2720, 0.5290],
    'leicester': [52.6369, -1.1398],
    'dalkeith': [55.8947, -3.0622],
    'wirral': [53.3727, -3.1000],
    'dundee': [56.4620, -2.9707],
    'eastbourne': [50.7680, 0.2843],
    'leeds': [53.8008, -1.5491],
    'norwich': [52.6309, 1.2974],
    'norfolk': [52.6143, 1.0226],
    'bath': [51.3811, -2.3590],
    'coventry': [52.4068, -1.5197],
    'brighton': [50.8225, -0.1372],
    'swansea': [51.6214, -3.9436],
    'exeter': [50.7236, -3.5275],
    'plymouth': [50.3755, -4.1427],
    'southampton': [50.9097, -1.4044],
    'reading': [51.4543, -0.9781],
    'swindon': [51.5558, -1.7797],
    'wolverhampton': [52.5862, -2.1285],
    'derby': [52.9225, -1.4746],
    'huddersfield': [53.6458, -1.7850],
    'bradford': [53.7960, -1.7594],
    'wakefield': [53.6830, -1.4977],
    'hull': [53.7457, -0.3367],
    'middlesbrough': [54.5742, -1.2350],
    'sunderland': [54.9058, -1.3810],
    'aberdeen': [57.1497, -2.0943],
    'inverness': [57.4778, -4.2247],
    'stirling': [56.1165, -3.9369],
    'perth': [56.3950, -3.4312],
    'newport': [51.5842, -2.9977],
    'wrexham': [53.0464, -2.9977],
    'bangor': [53.2274, -4.1293],
    'aberystwyth': [52.4153, -4.0829],
    'dublin': [53.3498, -6.2603],
    'cork': [51.8985, -8.4756],
    'limerick': [52.6638, -8.6267],
}


def geocode(location: str) -> list | None:
    if not location:
        return None
    raw = location.lower()
    raw = re.sub(r'[()]', ' ', raw)
    raw = re.sub(r',', ' ', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    if raw in COORDS:
        return COORDS[raw]
    words = raw.split(' ')
    for length in range(len(words), 0, -1):
        for start in range(len(words) - length + 1):
            phrase = ' '.join(words[start:start + length])
            if phrase in COORDS:
                return COORDS[phrase]
    return None


def parse_ics(text: str) -> list[dict]:
    unfolded = re.sub(r'\r?\n[ \t]', '', text)
    lines = re.split(r'\r?\n', unfolded)
    events = []
    cur = None

    for line in lines:
        if line == 'BEGIN:VEVENT':
            cur = {}
            continue
        if line == 'END:VEVENT' and cur is not None:
            events.append(cur)
            cur = None
            continue
        if cur is None:
            continue
        colon = line.find(':')
        if colon < 1:
            continue
        key = line[:colon].split(';')[0].upper()
        val = line[colon + 1:]
        cur[key] = val

    result = []
    for e in events:
        dtstr = e.get('DTSTART', '')
        m = re.match(r'(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})', dtstr)
        if not m:
            continue
        tz = timezone.utc if dtstr.endswith('Z') else timezone.utc
        date = datetime(
            int(m[1]), int(m[2]), int(m[3]),
            int(m[4]), int(m[5]), int(m[6]),
            tzinfo=tz,
        )
        desc = e.get('DESCRIPTION', '').replace('\\n', '\n').replace('\\', '').strip()
        host_match = re.match(r'^(.+?)\s+host\s+in', desc, re.IGNORECASE)
        result.append({
            'uid': e.get('UID', ''),
            'summary': e.get('SUMMARY', '').strip(),
            'location': e.get('LOCATION', '').strip(),
            'description': desc,
            'url': e.get('URL', '').strip(),
            'host': host_match.group(1).strip() if host_match else '',
            'date': date.isoformat(),
        })

    return result


def classify(summary: str) -> dict:
    s = summary
    is5N = bool(re.search(r'5\s*[Nn](ations?|rd)?|five\s*nations', s, re.IGNORECASE))

    tier = None
    tm = re.search(r'\bT([1-5])(?:[^0-9]|$)', s, re.IGNORECASE)
    tw = re.search(r'[Tt]ier\s*([1-5])', s)
    if tm:
        tier = int(tm.group(1))
    elif tw:
        tier = int(tw.group(1))

    # Multi-game detection
    game_count_m = re.search(r'\b(double|triple|quad)\s+header\b', s, re.IGNORECASE)
    game_count = {'double': 2, 'triple': 3, 'quad': 4}.get(
        game_count_m.group(1).lower(), 1
    ) if game_count_m else 1

    # Gender/category classification
    # OTA: explicit "OTA", "Open To All", or standalone O suffix in tier context
    isOTA = bool(re.search(r'\bOTA\b|open\s+to\s+all|\bT[1-5]\s*O\b|\bO\b\s*$', s, re.IGNORECASE))
    # MRDA: explicit "MRDA" or T[x]M tier code
    isMRDA = bool(re.search(r'\bMRDA\b|\bT[1-5]\s*M\b', s))
    # WFTDA: explicit tag, or default (anything not MRDA/OTA)
    isWFTDA = bool(re.search(r'\bWFTDA\b|\bT[1-5]\s*W\b|women', s, re.IGNORECASE)) or (not isMRDA and not isOTA)

    return {
        'is5N': is5N,
        'tier': tier,
        'gameCount': game_count,
        'isScrim': bool(re.search(r'\bscrim\b|closed\s*door', s, re.IGNORECASE)),
        'isRookie': bool(re.search(r'\brookies?\b', s, re.IGNORECASE)),
        'isMRDA': isMRDA,
        'isOTA': isOTA,
        'isWFTDA': isWFTDA,
        'isJunior': bool(re.search(r'\b(JRDA|[Jj]unior)\b', s)),
        'isTournament': bool(re.search(
            r'\b(tournament|cup|weekender|big\s*weekend|showdown|showcase|championship|playoffs?)\b',
            s, re.IGNORECASE,
        )),
        'isOpen': bool(re.search(r'open\s*(wftda|scrim)', s, re.IGNORECASE)),
    }


async def geocode_nominatim(client: httpx.AsyncClient, address: str, city: str) -> list | None:
    """Precise geocoding via Nominatim. Falls back to None on any failure."""
    query = f"{address}, {city}, UK" if city else f"{address}, UK"
    try:
        await asyncio.sleep(1)  # Nominatim rate limit: 1 req/sec
        resp = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "gb,ie"},
            headers={"User-Agent": "JamFinder/1.0 (uk-roller-derby-community-viewer)"},
            timeout=8,
        )
        data = resp.json()
        if data:
            return [float(data[0]["lat"]), float(data[0]["lon"])]
    except Exception as exc:
        logger.debug("Nominatim failed for '%s': %s", address, exc)
    return None


async def login(client: httpx.AsyncClient) -> bool:
    """Log in to TOaST. Returns True if successful."""
    email = os.environ.get("TOAST_EMAIL", "")
    password = os.environ.get("TOAST_PASSWORD", "")
    if not email or not password:
        logger.warning("TOAST_EMAIL / TOAST_PASSWORD not set — skipping login")
        return False
    try:
        resp = await client.get(f"{TOAST_BASE}/accounts/login/")
        m = re.search(r'name="csrfmiddlewaretoken"[^>]*value="([^"]+)"', resp.text)
        if not m:
            logger.warning("Login: could not find CSRF token")
            return False
        csrf = m.group(1)
        login_resp = await client.post(
            f"{TOAST_BASE}/accounts/login/",
            data={"csrfmiddlewaretoken": csrf, "username": email, "password": password, "next": ""},
            headers={"Referer": f"{TOAST_BASE}/accounts/login/"},
            follow_redirects=True,
        )
        success = "/accounts/login/" not in str(login_resp.url)
        logger.info("Login %s", "succeeded" if success else "FAILED — check credentials")
        return success
    except Exception as exc:
        logger.error("Login error: %s", exc)
        return False


async def fetch_event_details(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> dict:
    """
    Fetch games and info from a TOaST event page.
    Returns {games: [...], address: str|None, timings: str|None}
    """
    empty = {"games": [], "address": None, "timings": None}
    async with sem:
        try:
            await asyncio.sleep(2)  # be polite — one request every 2 seconds
            resp = await client.get(url, follow_redirects=True, timeout=15)
            if resp.status_code != 200 or "/accounts/login/" in str(resp.url):
                return empty

            soup = BeautifulSoup(resp.text, "html.parser")
            result = {"games": [], "address": None, "timings": None}

            # ── Games tab (#games) ───────────────────────────────────────────
            games_pane = soup.find(id="games")
            if games_pane:
                for row in games_pane.find_all("tr")[1:]:  # skip header row
                    cells = row.find_all("td")
                    if len(cells) < 2:
                        continue
                    # Strip badge spans so we get clean team names
                    for cell in cells:
                        for span in cell.find_all("span"):
                            span.decompose()
                    home = cells[0].get_text(strip=True)
                    away = cells[1].get_text(strip=True)
                    association = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                    game_type = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                    if home and away:
                        result["games"].append({
                            "home": home,
                            "away": away,
                            "association": association,
                            "gameType": game_type,
                        })

            # ── Info tab (#details) ─────────────────────────────────────────
            details_pane = soup.find(id="details")
            if details_pane:
                divisions = []
                for row in details_pane.find_all("tr"):
                    th = row.find("th")
                    td = row.find("td")
                    if not th or not td:
                        continue
                    label = th.get_text(strip=True).lower()

                    if label == "address":
                        for a in td.find_all("a"):
                            a.decompose()
                        result["address"] = td.get_text(strip=True)
                        city = soup.find(id="details")
                        city_text = ""
                        if city:
                            for r in city.find_all("tr"):
                                th = r.find("th")
                                td2 = r.find("td")
                                if th and td2 and th.get_text(strip=True).lower() == "city":
                                    city_text = td2.get_text(strip=True)
                                    break
                        result["precise_coords"] = await geocode_nominatim(
                            client, result["address"], city_text
                        )

                    elif label == "timings":
                        pre = td.find("pre")
                        if pre:
                            result["timings"] = pre.get_text(strip=True)

                    elif "division" in label:
                        for badge in td.find_all("span", class_="badge-info"):
                            div_text = badge.get_text(strip=True)
                            if div_text and div_text not in divisions:
                                divisions.append(div_text)

                result["divisions"] = divisions

            if result["games"]:
                logger.debug("Found %d games at %s", len(result["games"]), url)
            return result

        except Exception as exc:
            logger.warning("Could not fetch details from %s: %s", url, exc)
            return empty


def expand_multi_tier(event: dict) -> list[dict]:
    """Split 'T1 and T3' style summaries into two separate events."""
    m = re.search(r'\bT([1-5])\s+and\s+T([1-5])\b', event['summary'], re.IGNORECASE)
    if not m:
        return [event]
    tier1, tier2 = m.group(1), m.group(2)
    results = []
    for tier in [tier1, tier2]:
        ev = dict(event)
        ev['uid'] = f"{event['uid']}_t{tier}"
        ev['summary'] = re.sub(
            r'\bT[1-5]\s+and\s+T[1-5]\b',
            f'T{tier}',
            event['summary'],
            flags=re.IGNORECASE,
        )
        results.append(ev)
    return results


async def fetch_events() -> list[dict]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        # Fetch ICS — this always works regardless of auth
        resp = await client.get(ICS_URL)
        resp.raise_for_status()
        raw = parse_ics(resp.text)

        # Build base events
        events = []
        for e in raw:
            for ev in expand_multi_tier(e):
                events.append({
                    **ev,
                    **classify(ev['summary']),
                    'coords': geocode(ev['location']),
                    'games': [],
                    'address': None,
                    'timings': None,
                })

        # Try to enrich with games + address + timings from event pages
        logged_in = await login(client)
        if logged_in:
            sem = asyncio.Semaphore(1)  # sequential — avoid hammering the server
            # Deduplicate by original URL (split events share the same page)
            url_to_uids: dict[str, list[str]] = {}
            for ev in events:
                if ev.get('url'):
                    url_to_uids.setdefault(ev['url'], []).append(ev['uid'])

            tasks = {
                url: asyncio.create_task(fetch_event_details(client, url, sem))
                for url in url_to_uids
            }
            detail_results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            url_to_details = dict(zip(tasks.keys(), detail_results))

            uid_index = {ev['uid']: ev for ev in events}
            for url, uids in url_to_uids.items():
                details = url_to_details.get(url)
                if not isinstance(details, dict):
                    continue
                for uid in uids:
                    ev = uid_index.get(uid)
                    if not ev:
                        continue
                    ev['games'] = details.get('games', [])
                    ev['address'] = details.get('address')
                    ev['timings'] = details.get('timings')

                    # Fill in tier/is5N from division badges when title regex missed them
                    divisions = details.get('divisions', [])
                    if divisions:
                        if not ev['tier']:
                            for div in divisions:
                                m = re.match(r'T([1-5])', div, re.IGNORECASE)
                                if m:
                                    ev['tier'] = int(m.group(1))
                                    break
                        if not ev['is5N']:
                            ev['is5N'] = True  # division badges imply 5NRD

                    # Precise map coords from venue address (overrides city-level)
                    if details.get('precise_coords'):
                        ev['coords'] = details['precise_coords']

                    # Rookie flag from game team names
                    if not ev['isRookie'] and ev['games']:
                        ev['isRookie'] = any(
                            'rookie' in (g.get('home', '') + ' ' + g.get('away', '')).lower()
                            for g in ev['games']
                        )

            enriched = sum(
                1 for d in url_to_details.values()
                if isinstance(d, dict) and d.get('games')
            )
            logger.info("Enrichment complete: %d/%d event pages had game data",
                        enriched, len(url_to_details))

    return sorted(events, key=lambda x: x['date'])
