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
CHECKPOINT_FILE = Path("data/state/checkpoint.json")

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


def parse_timestamp(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def load_checkpoint():
    if not CHECKPOINT_FILE.exists():
        return {}

    return json.loads(
        CHECKPOINT_FILE.read_text(encoding="utf-8")
    )


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


def fetch_media_events(
    session,
    media_id,
    output_dir,
    last_received_at=None,
):
    page = 1
    pages_fetched = 0
    events_fetched = 0
    events_saved = 0
    newest_received_at = last_received_at

    params_base = {
        "media_id": media_id,
        "per_page": EVENT_PAGE_SIZE,
    }

    checkpoint_dt = None

    if last_received_at:
        checkpoint_dt = parse_timestamp(last_received_at)

        params_base["start_date"] = (
            checkpoint_dt.date().isoformat()
        )

        logger.info(
            "Incremental mode for media %s starting from %s",
            media_id,
            last_received_at,
        )
    else:
        logger.info(
            "Full-load mode for media %s",
            media_id,
        )

    while True:
        logger.info(
            "Fetching events for media %s, page %s",
            media_id,
            page,
        )

        params = {
            **params_base,
            "page": page,
        }

        events = get_json(
            session,
            f"{BASE_URL}/stats/events",
            params=params,
        )

        if not events:
            break

        pages_fetched += 1
        events_fetched += len(events)

        new_events = []

        for event in events:
            received_at = event.get("received_at")

            if not received_at:
                continue

            event_dt = parse_timestamp(received_at)

            if checkpoint_dt is None or event_dt > checkpoint_dt:
                new_events.append(event)

            if (
                newest_received_at is None
                or event_dt > parse_timestamp(newest_received_at)
            ):
                newest_received_at = received_at

        if new_events:
            page_file = (
                output_dir
                / "events"
                / media_id
                / f"page_{page:03d}.json"
            )

            save_json(page_file, new_events)

            events_saved += len(new_events)

            logger.info(
                "Saved %s new events from page %s",
                len(new_events),
                page,
            )
        else:
            logger.info(
                "No new events to save from page %s",
                page,
            )

        if len(events) < EVENT_PAGE_SIZE:
            break

        page += 1

    return {
        "mode": (
            "incremental"
            if last_received_at
            else "full"
        ),
        "checkpoint_before": last_received_at,
        "checkpoint_after": newest_received_at,
        "pages_fetched": pages_fetched,
        "events_fetched": events_fetched,
        "events_saved": events_saved,
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
    checkpoint = load_checkpoint()
    updated_checkpoint = dict(checkpoint)

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

            last_received_at = checkpoint.get(
                media_id,
                {},
            ).get("last_received_at")

            event_summary = fetch_media_events(
                session,
                media_id,
                output_dir,
                last_received_at,
            )

            manifest["media"][media_id] = event_summary

            if event_summary["checkpoint_after"]:
                updated_checkpoint[media_id] = {
                    "last_received_at": (
                        event_summary["checkpoint_after"]
                    )
                }

        finished_at = datetime.now(timezone.utc)

        manifest["finished_at_utc"] = finished_at.isoformat()
        manifest["status"] = "success"

        save_json(
            output_dir / "run_manifest.json",
            manifest,
        )

        save_json(
            CHECKPOINT_FILE,
            updated_checkpoint,
        )

        logger.info("Wistia ingestion completed successfully")
        logger.info("Raw data saved under %s", output_dir)
        logger.info(
            "Checkpoint saved to %s",
            CHECKPOINT_FILE,
        )

        for media_id, summary in manifest["media"].items():
            logger.info(
                "Media %s: mode=%s, fetched=%s, saved=%s, pages=%s",
                media_id,
                summary["mode"],
                summary["events_fetched"],
                summary["events_saved"],
                summary["pages_fetched"],
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
