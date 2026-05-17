"""
Meta Graph API client for Instagram carousel publishing.

Dry-run mode is active when META_ACCESS_TOKEN is not set — images are saved
to static/ig_tmp/ and the caption is logged, but nothing is posted.
"""
import asyncio
import logging
import os
import uuid
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v22.0"
_TMP_DIR = Path(__file__).parent.parent / "static" / "ig_tmp"


def _tmp_dir() -> Path:
    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    return _TMP_DIR


def _is_dry_run() -> bool:
    return not os.environ.get("META_ACCESS_TOKEN")


def _token() -> str:
    return os.environ["META_ACCESS_TOKEN"]


def _account_id() -> str:
    return os.environ["INSTAGRAM_BUSINESS_ACCOUNT_ID"]


def _public_url() -> str:
    base = os.environ.get("RAILWAY_PUBLIC_URL", "").rstrip("/")
    return base


def save_images_locally(slides: list[bytes]) -> list[Path]:
    """Write PNG bytes to static/ig_tmp/ and return paths."""
    paths = []
    tmp = _tmp_dir()
    for png in slides:
        path = tmp / f"{uuid.uuid4()}.png"
        path.write_bytes(png)
        paths.append(path)
    return paths


async def _upload_image_container(
    client: httpx.AsyncClient,
    image_url: str,
    account_id: str,
    token: str,
) -> str:
    """Create a single-image container and return its ID."""
    resp = await client.post(
        f"{_GRAPH_BASE}/{account_id}/media",
        json={
            "image_url": image_url,
            "is_carousel_item": True,
            "access_token": token,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        logger.error("Meta API error %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    return resp.json()["id"]


async def publish_carousel(slides: list[bytes], caption: str) -> None:
    """
    Publish slides as an Instagram carousel.
    Falls back to dry-run (local save + log) if META_ACCESS_TOKEN is absent.
    """
    if _is_dry_run():
        paths = save_images_locally(slides)
        logger.info(
            "[DRY RUN] Would post %d-slide carousel. Images saved:\n%s\n\nCaption:\n%s",
            len(slides),
            "\n".join(str(p) for p in paths),
            caption,
        )
        return

    tmp = _tmp_dir()
    paths = save_images_locally(slides)
    public_base = _public_url()
    token = _token()
    account_id = _account_id()

    image_urls = [f"{public_base}/static/ig_tmp/{p.name}" for p in paths]

    async with httpx.AsyncClient() as client:
        # Step 1: upload each image and get container IDs
        container_ids = []
        for url in image_urls:
            cid = await _upload_image_container(client, url, account_id, token)
            container_ids.append(cid)
            logger.info("Uploaded image container: %s", cid)

        # Step 2: create carousel container
        carousel_resp = await client.post(
            f"{_GRAPH_BASE}/{account_id}/media",
            json={
                "media_type": "CAROUSEL",
                "children": ",".join(container_ids),
                "caption": caption,
                "access_token": token,
            },
            timeout=30,
        )
        carousel_resp.raise_for_status()
        carousel_id = carousel_resp.json()["id"]
        logger.info("Carousel container created: %s", carousel_id)

        # Step 3: publish
        pub_resp = await client.post(
            f"{_GRAPH_BASE}/{account_id}/media_publish",
            json={"creation_id": carousel_id, "access_token": token},
            timeout=30,
        )
        pub_resp.raise_for_status()
        logger.info("Carousel published successfully. Media ID: %s", pub_resp.json().get("id"))

    # Clean up temp files after a short delay (Meta fetches them asynchronously)
    await asyncio.sleep(60)
    for p in paths:
        try:
            p.unlink(missing_ok=True)
        except Exception as exc:
            logger.debug("Could not delete temp image %s: %s", p, exc)
