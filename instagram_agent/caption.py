import json
import random
from datetime import date
from pathlib import Path

_HANDLES_PATH = Path(__file__).parent / "team_handles.json"

_PUNS = [
    "The weekend's looking WHEELY good 🛼",
    "Lace up — it's bout time 🏳️",
    "Your weekend plans just got a whole lot jammier ✨",
    "Hit the floor running — here's what's on this weekend 💥",
    "Block your diary. Literally. 🛼",
    "No faking it — these bouts are the real wheel deal 🏆",
    "Skate don't wait — it's a big weekend for UK derby 🌟",
    "The hits keep coming this weekend 💫",
]

_HASHTAGS = (
    "#rollerderby #ukrollerderby #jamfinder #flattrack "
    "#rollerderbybout #weekendsports #wftda #rollerskating"
)


def _load_handles() -> dict:
    try:
        return json.loads(_HANDLES_PATH.read_text())
    except Exception:
        return {}


def _tag(team_name: str, handles: dict) -> str:
    return handles.get(team_name, team_name)


def build_caption(events: list[dict], overflow: int = 0) -> str:
    handles = _load_handles()
    sat = [e for e in events if date.fromisoformat(e["date"][:10]).weekday() == 5]
    sun = [e for e in events if date.fromisoformat(e["date"][:10]).weekday() == 6]

    lines = [random.choice(_PUNS), ""]

    for day_label, day_events in [("🗓 SATURDAY", sat), ("🗓 SUNDAY", sun)]:
        if not day_events:
            continue
        lines.append(day_label)
        for ev in day_events:
            is_scrim = ev.get("isScrim", False)
            closed_doors_note = " (Closed Doors)" if is_scrim else ""
            games = ev.get("games", [])
            if games:
                for g in games:
                    home = _tag(g["home"], handles)
                    away = _tag(g["away"], handles)
                    lines.append(f"• {home} vs {away}{closed_doors_note}")
            else:
                lines.append(f"• {ev['summary']}{closed_doors_note}")
            loc = ev.get("location", "")
            if loc:
                lines.append(f"  📍 {loc}")
        lines.append("")

    if overflow > 0:
        lines.append(f"...plus {overflow} more event{'s' if overflow > 1 else ''} on jamfinder.app")
        lines.append("")

    lines.append("🔗 Full listings at jamfinder.app (link in bio)")
    lines.append("")
    lines.append(_HASHTAGS)

    return "\n".join(lines)
