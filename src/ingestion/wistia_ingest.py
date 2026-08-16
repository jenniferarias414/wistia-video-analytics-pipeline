import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


API_VERSION = "2026-07"
MEDIA_IDS = ["8hunphufxp", "9k4tbcdfg0"]
BASE_URL = "https://api.wistia.com/modern"
EVENT_PAGE_SIZE = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def create_session(api_token):
    session = requests.Session()

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    session.headers.update(
        {
            "Authorization": f"Bearer {api_token}",
            "X-Wistia-API-Version": API_VERSION,
        }
    )

    return session


def get_json(session, url, params=None):
    response = session.get(
        url,
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def fetch_media_metadata(session):
    params = [
        ("hashed_ids[]", media_id)
        for media_id in MEDIA_IDS
    ]

    return get_json(
        session,
        f"{BASE_URL}/medias",
        params=params,
    )


def fetch_media_stats(session, media_id):
    return get_json(
        session,
        f"{BASE_URL}/stats/medias/{media_id}",
    )


def fetch_media_events(session, media_id, output_dir):
    page = 1
    total_events = 0

    while True:
        logger.info(
            "Fetching events for media %s, page %s",
            media_id,
            page,
        )

        events = get_json(
            session,
            f"{BASE_URL}/stats/events",
            params={
                "media_id": media_id,
                "page": page,
                "per_page": EVENT_PAGE_SIZE,
            },
        )

        if not events:
            break

        page_file = (
            output_dir
            / "events"
            / media_id
            / f"page_{page:03d}.json"
        )

        save_json(page_file, events)

        total_events += len(events)

        logger.info(
            "Saved %s events from page %s",
            len(events),
            page,
        )

        if len(events) < EVENT_PAGE_SIZE:
            break

        page += 1

    return {
        "pages_processed": page,
        "events_processed": total_events,
    }


def main():
    api_token = os.getenv("WISTIA_API_TOKEN")

    if not api_token:
        logger.error(
            "WISTIA_API_TOKEN environment variable is not set."
        )
        sys.exit(1)

    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")

    output_dir = Path("data/raw") / run_id

    logger.info("Starting Wistia ingestion run %s", run_id)

    session = create_session(api_token)

    manifest = {
        "run_id": run_id,
        "started_at_utc": started_at.isoformat(),
        "media_ids": MEDIA_IDS,
        "media": {},
        "status": "running",
    }

    try:
        logger.info("Fetching media metadata")

        metadata = fetch_media_metadata(session)

        save_json(
            output_dir / "media_metadata.json",
            metadata,
        )

        logger.info(
            "Saved metadata for %s media records",
            len(metadata),
        )

        for media_id in MEDIA_IDS:
            logger.info(
                "Fetching aggregate stats for media %s",
                media_id,
            )

            stats = fetch_media_stats(
                session,
                media_id,
            )

            save_json(
                output_dir
                / "media_stats"
                / f"{media_id}.json",
                stats,
            )

            event_summary = fetch_media_events(
                session,
                media_id,
                output_dir,
            )

            manifest["media"][media_id] = event_summary

        finished_at = datetime.now(timezone.utc)

        manifest["finished_at_utc"] = finished_at.isoformat()
        manifest["status"] = "success"

        save_json(
            output_dir / "run_manifest.json",
            manifest,
        )

        logger.info("Wistia ingestion completed successfully")
        logger.info("Raw data saved under %s", output_dir)

        for media_id, summary in manifest["media"].items():
            logger.info(
                "Media %s: %s events across %s page(s)",
                media_id,
                summary["events_processed"],
                summary["pages_processed"],
            )

    except requests.RequestException as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)

        save_json(
            output_dir / "run_manifest.json",
            manifest,
        )

        logger.exception("Wistia ingestion failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
