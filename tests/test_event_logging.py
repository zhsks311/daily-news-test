from __future__ import annotations

import json
from datetime import datetime, timezone

from briefing_collector.collector import CollectionEventLogger


def test_collection_event_logger_writes_structured_jsonl_events(tmp_path):
    log_path = tmp_path / "events.jsonl"
    logger = CollectionEventLogger(log_path=log_path, run_id="run-1", now=lambda: datetime(2026, 4, 27, 9, 0, tzinfo=timezone.utc))

    logger.log("feed_fetch_start", source="Example", category="dev", url="https://example.com/feed.xml")
    logger.log("feed_fetch_success", source="Example", status_code=200, bytes=1234, elapsed_ms=42)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first == {
        "ts": "2026-04-27T09:00:00+00:00",
        "run_id": "run-1",
        "event": "feed_fetch_start",
        "source": "Example",
        "category": "dev",
        "url": "https://example.com/feed.xml",
    }
    assert second["event"] == "feed_fetch_success"
    assert second["elapsed_ms"] == 42


def test_collection_event_logger_sanitizes_exception_values(tmp_path):
    log_path = tmp_path / "events.jsonl"
    logger = CollectionEventLogger(log_path=log_path, run_id="run-2", now=lambda: datetime(2026, 4, 27, 9, 0, tzinfo=timezone.utc))

    logger.log("feed_fetch_error", source="Example", error=ValueError("bad value"))

    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert event["event"] == "feed_fetch_error"
    assert event["error"] == "ValueError: bad value"
