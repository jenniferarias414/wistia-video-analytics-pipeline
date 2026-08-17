from datetime import timezone

import src.ingestion.wistia_ingest as ingestion


def test_parse_timestamp_handles_wistia_z_timestamp():
    result = ingestion.parse_timestamp("2026-08-15T07:51:28.000Z")

    assert result.year == 2026
    assert result.month == 8
    assert result.day == 15
    assert result.tzinfo == timezone.utc


def test_incremental_ingestion_saves_only_newer_events(monkeypatch):
    checkpoint = "2026-08-15T07:51:28.000Z"

    api_events = [
        {
            "event_key": "already-processed",
            "received_at": checkpoint,
        },
        {
            "event_key": "new-event",
            "received_at": "2026-08-15T08:00:00.000Z",
        },
    ]

    saved_payloads = []

    def fake_get_json(session, url, params=None):
        return api_events

    def fake_put_json(s3_client, key, payload):
        saved_payloads.append(
            {
                "key": key,
                "payload": payload,
            }
        )

    monkeypatch.setattr(
        ingestion,
        "get_json",
        fake_get_json,
    )

    monkeypatch.setattr(
        ingestion,
        "put_json",
        fake_put_json,
    )

    result = ingestion.fetch_media_events(
        session=object(),
        s3_client=object(),
        media_id="test-media",
        run_prefix="raw/test-run",
        last_received_at=checkpoint,
    )

    assert result["mode"] == "incremental"
    assert result["events_fetched"] == 2
    assert result["events_saved"] == 1

    assert len(saved_payloads) == 1
    assert saved_payloads[0]["payload"] == [
        {
            "event_key": "new-event",
            "received_at": "2026-08-15T08:00:00.000Z",
        }
    ]
