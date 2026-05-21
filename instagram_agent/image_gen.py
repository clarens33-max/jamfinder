"""
Generate 1080×1080 PNG slides via Playwright (headless Chromium).
Event slides overlay text onto static/backgrounds/event_frame.png.
CTA slide uses static/backgrounds/cta.png directly — no text added.
"""
import base64
import re
from datetime import date
from pathlib import Path

_BACKGROUNDS = Path(__file__).parent.parent / "static" / "backgrounds"
_FONT_IMPORT = (
    "https://fonts.googleapis.com/css2?"
    "family=Oswald:wght@400;600;700&family=Inter:wght@400;600;700&display=swap"
)


def _b64_image(path: Path) -> str:
    """Return a base64 data URI for an image file."""
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def _day_label(iso_date: str) -> str:
    d = date.fromisoformat(iso_date[:10])
    return d.strftime("%A %d %B").lstrip("0").upper()


def _event_title(ev: dict) -> str:
    summary = ev.get("summary", "")
    clean = re.sub(r'\b(T[1-5][WMO]?|5N(rd)?|WFTDA|MRDA|OTA)\b', '', summary, flags=re.IGNORECASE)
    clean = re.sub(r'\s{2,}', ' ', clean).strip(" -–")
    return clean or summary


def _bout_rows(games: list[dict]) -> str:
    rows = []
    for g in games[:5]:
        home = g.get("home", "")
        away = g.get("away", "")
        rows.append(f"""
        <div class="bout">
          <span class="team">{home}</span>
          <span class="vs">VS</span>
          <span class="team">{away}</span>
        </div>""")
    return "\n".join(rows)


def _event_slide_html(ev: dict) -> str:
    frame_uri = _b64_image(_BACKGROUNDS / "event_frame.png")
    title = _event_title(ev)
    day = _day_label(ev["date"])
    location = ev.get("location", "")
    address = ev.get("address", "")
    games = ev.get("games", [])
    bout_html = _bout_rows(games)
    tier = ev.get("tier")
    is5n = ev.get("is5N", False)

    is_scrim = ev.get("isScrim", False)

    badges = ""
    if is5n:
        badges += '<span class="badge five-n">5 NATIONS</span>'
    if tier:
        badges += f'<span class="badge tier">TIER {tier}</span>'
    if is_scrim:
        badges += '<span class="badge closed-doors">SCRIMMAGE · CLOSED DOORS</span>'

    return f"""<!DOCTYPE html>
<html>
<head>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="stylesheet" href="{_FONT_IMPORT}">
  <style>
    *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      width: 1080px;
      height: 1080px;
      background: url('{frame_uri}') center/cover no-repeat;
      font-family: 'Inter', sans-serif;
      color: #fff;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    /* Text lives in the black centre of the frame */
    .content {{
      width: 700px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      text-align: center;
    }}

    .badges {{
      display: flex;
      gap: 8px;
      justify-content: center;
    }}

    .badge {{
      font-family: 'Oswald', sans-serif;
      font-size: 12px;
      letter-spacing: 2px;
      padding: 4px 14px;
      border-radius: 4px;
    }}
    .five-n {{ background: #9c27b0; }}
    .tier {{ background: #E91E8C; }}
    .closed-doors {{ background: #333; border: 1px solid #666; }}

    .event-name {{
      font-family: 'Oswald', sans-serif;
      font-size: 48px;
      font-weight: 700;
      line-height: 1.05;
      letter-spacing: 1px;
      color: #fff;
    }}

    .location {{
      font-size: 16px;
      color: #E91E8C;
      font-weight: 600;
    }}

    .address {{
      font-size: 13px;
      color: #aaa;
      margin-top: -8px;
    }}

    .date {{
      font-family: 'Oswald', sans-serif;
      font-size: 20px;
      letter-spacing: 2px;
      color: #fff;
    }}

    .divider {{
      border: none;
      border-top: 1px solid #333;
      margin: 4px 0;
    }}

    .bouts {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}

    .bout {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      font-family: 'Oswald', sans-serif;
      font-size: 22px;
      font-weight: 600;
    }}

    .vs {{
      color: #E91E8C;
      font-size: 16px;
    }}

    .team {{
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .team:first-child {{ text-align: right; }}
    .team:last-child {{ text-align: left; }}
  </style>
</head>
<body>
  <div class="content">
    {'<div class="badges">' + badges + '</div>' if badges else ''}
    <div class="event-name">{title}</div>
    {'<div class="location">📍 ' + location + '</div>' if location else ''}
    {'<div class="address">' + address + '</div>' if address else ''}
    <div class="date">🗓 {day}</div>
    <hr class="divider">
    <div class="bouts">{bout_html}</div>
  </div>
</body>
</html>"""


async def generate_event_slide(ev: dict) -> bytes:
    from playwright.async_api import async_playwright
    html = _event_slide_html(ev)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1080, "height": 1080})
        await page.set_content(html, wait_until="networkidle")
        png = await page.screenshot(type="png")
        await browser.close()
    return png


async def generate_cta_slide(overflow: int = 0) -> bytes:
    """CTA is a static image — just return the file bytes directly."""
    return (_BACKGROUNDS / "cta.png").read_bytes()
