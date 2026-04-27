import asyncio
import logging
import os

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


async def refresh() -> None:
    logger.info("Fetching events from rollerderby.directory…")
    try:
        events = await fetch_events()
        cache["events"] = events
        cache["last_updated"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Cached {len(events)} events")
    except Exception as exc:
        logger.error(f"Refresh failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run refresh in the background so the server starts immediately.
    # The frontend loading screen polls /api/events until status == "ready".
    asyncio.create_task(refresh())

    from instagram_agent.poster import post_weekly

    scheduler = AsyncIOScheduler()
    scheduler.add_job(refresh, CronTrigger(hour=3, minute=0, timezone="UTC"))
    scheduler.add_job(post_weekly, CronTrigger(day_of_week="thu", hour=9, minute=0, timezone="Europe/London"), args=[cache, refresh])
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
