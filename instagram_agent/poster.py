"""
Weekly Instagram poster for Jam Finder.
Scheduled every Thursday 9am UK time from main.py.
"""
import asyncio
import logging
from datetime import date, timedelta

from .caption import build_caption
from .image_gen import generate_cta_slide, generate_event_slide
from .instagram_api import publish_carousel

logger = logging.getLogger(__name__)

_MAX_CAROUSEL_EVENTS = 9  # leave room for CTA slide (carousel max = 10)
_REFRESH_RETRIES = 3
_REFRESH_DELAY_SECS = 60


def _this_weekend() -> tuple[date, date]:
    today = date.today()
    days_to_sat = (5 - today.weekday()) % 7
    saturday = today + timedelta(days=days_to_sat)
    return saturday, saturday + timedelta(days=1)


def _qualifying_events(all_events: list[dict]) -> list[dict]:
    """Return public weekend events that have game data, sorted by date."""
    saturday, sunday = _this_weekend()
    weekend_dates = {saturday.isoformat(), sunday.isoformat()}
    result = []
    for ev in all_events:
        event_date = ev.get("date", "")[:10]
        if event_date not in weekend_dates:
            continue
        if ev.get("isScrim"):
            continue
        if not ev.get("games"):
            continue
        result.append(ev)
    return result


async def post_weekly(cache: dict, refresh_fn) -> None:
    """Entry point called by APScheduler every Thursday 9am UK.

    Args:
        cache: The shared in-memory event cache from main.py.
        refresh_fn: The async refresh() coroutine function from main.py.
    """
    logger.info("Instagram agent: starting weekly post")

    # Attempt to find qualifying events; retry with refresh if none found
    events = _qualifying_events(cache.get("events", []))

    if not events:
        logger.info("No qualifying events in cache — attempting refresh")
        for attempt in range(1, _REFRESH_RETRIES + 1):
            await refresh_fn()
            events = _qualifying_events(cache.get("events", []))
            if events:
                logger.info("Refresh attempt %d succeeded — %d events found", attempt, len(events))
                break
            if attempt < _REFRESH_RETRIES:
                logger.info(
                    "Still no events after refresh attempt %d/%d — waiting %ds",
                    attempt, _REFRESH_RETRIES, _REFRESH_DELAY_SECS,
                )
                await asyncio.sleep(_REFRESH_DELAY_SECS)

    if not events:
        logger.warning(
            "Instagram agent: no qualifying weekend events after %d refresh attempts — skipping post",
            _REFRESH_RETRIES,
        )
        return

    featured = events[:_MAX_CAROUSEL_EVENTS]
    overflow = len(events) - len(featured)
    logger.info("Generating %d event slide(s) + CTA (overflow=%d)", len(featured), overflow)

    # Generate slides concurrently
    event_slides = await asyncio.gather(*[generate_event_slide(ev) for ev in featured])
    cta_slide = await generate_cta_slide(overflow)
    all_slides = list(event_slides) + [cta_slide]

    caption = build_caption(featured, overflow=overflow)

    await publish_carousel(all_slides, caption)
    logger.info("Instagram agent: post complete")
