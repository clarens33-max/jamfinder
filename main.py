import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from scraper import fetch_events

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

cache: dict = {"events": [], "last_updated": None}

PERSIST_DIR = Path(os.environ.get("PERSIST_DIR", "."))
CACHE_FILE = PERSIST_DIR / "cache.json"
HISTORY_FILE = PERSIST_DIR / "events_history.json"


def _load_cache() -> None:
    try:
        data = json.loads(CACHE_FILE.read_text())
        cache["events"] = data["events"]
        cache["last_updated"] = data["last_updated"]
        logger.info(f"Loaded {len(cache['events'])} events from disk")
    except FileNotFoundError:
        logger.info("No cache file found — will scrape on startup")
    except Exception as exc:
        logger.warning(f"Could not load cache from disk: {exc} — will scrape on startup")


def _save_cache() -> None:
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache))
    tmp.replace(CACHE_FILE)


def _save_snapshot() -> None:
    snap_dir = PERSIST_DIR / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (snap_dir / f"events_{today}.json").write_text(json.dumps(cache))


def _update_history(events: list) -> None:
    try:
        history = json.loads(HISTORY_FILE.read_text()) if HISTORY_FILE.exists() else {}
    except Exception:
        history = {}
    for event in events:
        history[event["uid"]] = event
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(history))
    tmp.replace(HISTORY_FILE)
    logger.info(f"History file updated — {len(history)} total events")


async def refresh() -> None:
    logger.info("Fetching events from rollerderby.directory…")
    try:
        events = await fetch_events()
        cache["events"] = events
        cache["last_updated"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Cached {len(events)} events")
        _save_cache()
        _save_snapshot()
        _update_history(events)
    except Exception as exc:
        logger.error(f"Refresh failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_cache()
    # Run refresh in the background so the server starts immediately.
    # The frontend loading screen polls /api/events until status == "ready".
    if not cache["last_updated"]:
        asyncio.create_task(refresh())

    from instagram_agent.poster import post_weekly

    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh, CronTrigger(hour=3, minute=0, timezone="UTC"))
    scheduler.add_job(post_weekly, CronTrigger(day_of_week="wed", hour=18, minute=0, timezone="Europe/London"), args=[cache, refresh])
    scheduler.start()

    yield

    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/api/events")
async def get_events():
    return JSONResponse({
        "events": cache["events"],
        "last_updated": cache["last_updated"],
        "count": len(cache["events"]),
        "status": "ready" if cache["last_updated"] else "loading",
    })


@app.get("/api/refresh")
async def manual_refresh():
    """Trigger a manual data refresh (useful for testing)."""
    await refresh()
    return {"ok": True, "count": len(cache["events"]), "last_updated": cache["last_updated"]}


@app.get("/api/instagram-test")
async def instagram_test():
    """Manually trigger the Instagram agent (dry-run when META_ACCESS_TOKEN is unset)."""
    from instagram_agent.poster import post_weekly
    asyncio.create_task(post_weekly(cache, refresh))
    return {"ok": True, "message": "Instagram post job started — check logs for output"}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
