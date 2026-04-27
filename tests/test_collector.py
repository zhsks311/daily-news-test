from __future__ import annotations

from datetime import datetime, timezone

from briefing_collector.collector import (
    ArticleCandidate,
    deduplicate_candidates,
    filter_recent_candidates,
    parse_feed_entries,
    score_candidate,
)


def test_parse_feed_entries_extracts_source_category_url_and_published_date():
    feed_xml = """<?xml version='1.0'?>
    <rss version='2.0'><channel><title>Example Feed</title>
      <item>
        <title>How we made storage faster</title>
        <link>https://example.com/storage</link>
        <guid>storage-1</guid>
        <pubDate>Mon, 27 Apr 2026 00:30:00 GMT</pubDate>
        <description>Deep dive into latency and caches.</description>
      </item>
    </channel></rss>"""

    items = parse_feed_entries(
        feed_xml.encode("utf-8"),
        source_name="Example Engineering",
        source_category="dev",
        feed_url="https://example.com/feed.xml",
    )

    assert len(items) == 1
    item = items[0]
    assert item.title == "How we made storage faster"
    assert item.url == "https://example.com/storage"
    assert item.source == "Example Engineering"
    assert item.category == "dev"
    assert item.feed_url == "https://example.com/feed.xml"
    assert item.published_at == datetime(2026, 4, 27, 0, 30, tzinfo=timezone.utc)
    assert "latency" in item.summary


def test_filter_recent_candidates_keeps_recent_and_unknown_dates_but_marks_unknown():
    now = datetime(2026, 4, 27, 9, 0, tzinfo=timezone.utc)
    recent = ArticleCandidate(title="Recent", url="https://a.com/1", source="A", category="dev", published_at=datetime(2026, 4, 26, tzinfo=timezone.utc))
    old = ArticleCandidate(title="Old", url="https://a.com/2", source="A", category="dev", published_at=datetime(2026, 4, 1, tzinfo=timezone.utc))
    unknown = ArticleCandidate(title="Unknown", url="https://a.com/3", source="A", category="dev", published_at=None)

    kept = filter_recent_candidates([recent, old, unknown], now=now, days=3, include_unknown_dates=True)

    assert [item.title for item in kept] == ["Recent", "Unknown"]
    assert kept[1].date_status == "unknown"


def test_deduplicate_candidates_prefers_item_with_text_and_newer_date():
    older = ArticleCandidate(title="Same", url="https://example.com/post?utm_source=x", source="A", category="dev", published_at=datetime(2026, 4, 25, tzinfo=timezone.utc), extracted_text="")
    newer = ArticleCandidate(title="Same", url="https://example.com/post", source="A", category="dev", published_at=datetime(2026, 4, 26, tzinfo=timezone.utc), extracted_text="long text")

    deduped = deduplicate_candidates([older, newer])

    assert len(deduped) == 1
    assert deduped[0].url == "https://example.com/post"
    assert deduped[0].published_at == datetime(2026, 4, 26, tzinfo=timezone.utc)


def test_score_candidate_rewards_deep_relevant_titles_and_penalizes_announcements():
    deep = ArticleCandidate(title="Designing resilient distributed cache systems", url="https://example.com/a", source="A", category="dev", summary="architecture performance latency", extracted_text="x" * 2000)
    shallow = ArticleCandidate(title="Product release announcement", url="https://example.com/b", source="B", category="dev", summary="new product launch", extracted_text="short")

    assert score_candidate(deep) > score_candidate(shallow)
