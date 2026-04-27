from __future__ import annotations

import argparse
import json
import re
import sys
import time
import tomllib
import uuid
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning

USER_AGENT = "HermesDailyBriefingCollector/0.1 (+https://github.com/rss)"
TRACKING_PARAMS_PREFIXES = ("utm_",)
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "ref"}
RELEVANCE_KEYWORDS = {
    "dev": {
        "architecture", "system", "systems", "distributed", "database", "performance",
        "latency", "security", "infra", "infrastructure", "llm", "ai", "model",
        "compiler", "runtime", "debugging", "observability", "cache", "storage",
        "scaling", "reliability", "backend", "frontend", "open source", "kubernetes",
    },
    "econ": {
        "inflation", "rate", "rates", "monetary", "fiscal", "productivity", "labor",
        "market", "markets", "trade", "growth", "recession", "policy", "central bank",
        "credit", "debt", "supply", "demand", "wage", "employment", "gdp", "data",
        "technology", "industry", "china", "global",
    },
}
LOW_VALUE_KEYWORDS = {
    "announcement", "announcing", "release notes", "weekly roundup", "webinar", "event",
    "sponsored", "product launch", "launch", "newsletter",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CollectionEventLogger:
    """Append-only JSONL logger for improving feed quality and ranking later."""

    def __init__(self, log_path: Path | None, run_id: str | None = None, now: Any = utc_now) -> None:
        self.log_path = log_path
        self.run_id = run_id or uuid.uuid4().hex
        self._now = now
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **fields: Any) -> None:
        if not self.log_path:
            return
        payload: dict[str, Any] = {
            "ts": self._now().astimezone(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event": event,
        }
        payload.update({key: self._jsonable(value) for key, value in fields.items()})
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def _jsonable(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        if isinstance(value, BaseException):
            return f"{type(value).__name__}: {value}"
        if isinstance(value, Path):
            return str(value)
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)


@dataclass(slots=True)
class ArticleCandidate:
    title: str
    url: str
    source: str
    category: str
    published_at: datetime | None = None
    summary: str = ""
    feed_url: str = ""
    extracted_text: str = ""
    date_status: str = "known"
    score: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat() if self.published_at else None
        return data


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    if "<" in value and ">" in value:
        soup = BeautifulSoup(value, "html.parser")
        text = soup.get_text(" ")
    else:
        text = value
    return re.sub(r"\s+", " ", text).strip()


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, time.struct_time):
        dt = datetime(*value[:6], tzinfo=timezone.utc)
    elif isinstance(value, str):
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lower = key.lower()
        if lower in TRACKING_PARAMS or any(lower.startswith(prefix) for prefix in TRACKING_PARAMS_PREFIXES):
            continue
        query.append((key, value))
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query, doseq=True), ""))


def parse_feed_entries(feed_bytes: bytes, source_name: str, source_category: str, feed_url: str) -> list[ArticleCandidate]:
    parsed = feedparser.parse(feed_bytes)
    candidates: list[ArticleCandidate] = []
    for entry in parsed.entries:
        title = clean_text(entry.get("title"))
        raw_url = entry.get("link") or entry.get("id") or ""
        if not title or not raw_url.startswith(("http://", "https://")):
            continue
        published = (
            parse_datetime(entry.get("published_parsed"))
            or parse_datetime(entry.get("updated_parsed"))
            or parse_datetime(entry.get("published"))
            or parse_datetime(entry.get("updated"))
        )
        summary = clean_text(entry.get("summary") or entry.get("description") or "")
        candidates.append(
            ArticleCandidate(
                title=title,
                url=canonicalize_url(raw_url),
                source=source_name,
                category=source_category,
                published_at=published,
                summary=summary,
                feed_url=feed_url,
                date_status="known" if published else "unknown",
            )
        )
    return candidates


def filter_recent_candidates(
    candidates: Iterable[ArticleCandidate],
    now: datetime,
    days: int,
    include_unknown_dates: bool = False,
) -> list[ArticleCandidate]:
    cutoff = now.astimezone(timezone.utc) - timedelta(days=days)
    kept: list[ArticleCandidate] = []
    for item in candidates:
        if item.published_at is None:
            item.date_status = "unknown"
            if include_unknown_dates:
                kept.append(item)
            continue
        item.published_at = item.published_at.astimezone(timezone.utc)
        item.date_status = "known"
        if item.published_at >= cutoff and item.published_at <= now.astimezone(timezone.utc) + timedelta(hours=6):
            kept.append(item)
    return kept


def _candidate_quality_tuple(item: ArticleCandidate) -> tuple[int, datetime, int]:
    has_text = 1 if len(item.extracted_text) >= 400 else 0
    published = item.published_at or datetime.min.replace(tzinfo=timezone.utc)
    text_len = len(item.extracted_text or item.summary or "")
    return (has_text, published, text_len)


def deduplicate_candidates(candidates: Iterable[ArticleCandidate]) -> list[ArticleCandidate]:
    by_url: dict[str, ArticleCandidate] = {}
    for item in candidates:
        key = canonicalize_url(item.url)
        item.url = key
        prev = by_url.get(key)
        if prev is None or _candidate_quality_tuple(item) > _candidate_quality_tuple(prev):
            by_url[key] = item
    return sorted(by_url.values(), key=lambda i: (i.published_at or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)


def score_candidate(item: ArticleCandidate) -> float:
    haystack = f"{item.title} {item.summary} {item.extracted_text[:2000]}".lower()
    score = 0.0
    for keyword in RELEVANCE_KEYWORDS.get(item.category, set()):
        if keyword in haystack:
            score += 2.0 if keyword in item.title.lower() else 1.0
    for keyword in LOW_VALUE_KEYWORDS:
        if keyword in haystack:
            score -= 3.0
    if len(item.extracted_text) >= 1200:
        score += 3.0
    elif len(item.summary) >= 160:
        score += 1.0
    if item.published_at:
        age_hours = max(0.0, (datetime.now(timezone.utc) - item.published_at).total_seconds() / 3600)
        score += max(0.0, 2.0 - age_hours / 72.0)
    if item.date_status == "unknown":
        score -= 1.0
    return round(score, 3)


def fetch_url(session: requests.Session, url: str, timeout: float, verify_ssl: bool = True) -> bytes:
    with warnings.catch_warnings():
        if not verify_ssl:
            warnings.simplefilter("ignore", InsecureRequestWarning)
        response = session.get(url, timeout=timeout, verify=verify_ssl, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.8"})
    response.raise_for_status()
    return response.content


def extract_article_text(session: requests.Session, url: str, timeout: float, max_chars: int) -> tuple[str, str | None]:
    try:
        response = session.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        response.raise_for_status()
    except Exception as exc:  # network failures should not drop metadata candidates
        return "", f"article_fetch_failed: {type(exc).__name__}: {exc}"
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        return "", f"article_not_html: {content_type}"
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = re.sub(r"\s+", " ", main.get_text(" ")).strip()
    return text[:max_chars], None


def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def collect_candidates(
    config: dict[str, Any],
    days: int,
    per_category: int,
    fetch_full_text: bool,
    timeout: float,
    now: datetime | None = None,
    event_logger: CollectionEventLogger | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    logger = event_logger or CollectionEventLogger(None)
    logger.log("collection_start", days=days, per_category=per_category, fetch_full_text=fetch_full_text, source_count=len(config.get("sources", [])))
    session = requests.Session()
    raw_candidates: list[ArticleCandidate] = []
    source_errors: list[dict[str, str]] = []
    for source in config.get("sources", []):
        source_started = time.perf_counter()
        source_name = source.get("name", "unknown")
        source_category = source.get("category", "unknown")
        feed_url = source.get("feed_url", "")
        logger.log("feed_fetch_start", source=source_name, category=source_category, url=feed_url, verify_ssl=bool(source.get("verify_ssl", True)))
        try:
            feed_bytes = fetch_url(session, source["feed_url"], timeout=timeout, verify_ssl=bool(source.get("verify_ssl", True)))
            parsed_items = parse_feed_entries(feed_bytes, source["name"], source["category"], source["feed_url"])
            raw_candidates.extend(parsed_items)
            logger.log(
                "feed_fetch_success",
                source=source_name,
                category=source_category,
                url=feed_url,
                bytes=len(feed_bytes),
                parsed_count=len(parsed_items),
                elapsed_ms=round((time.perf_counter() - source_started) * 1000),
            )
        except Exception as exc:
            source_errors.append({"source": source_name, "url": feed_url, "error": f"{type(exc).__name__}: {exc}"})
            logger.log(
                "feed_fetch_error",
                source=source_name,
                category=source_category,
                url=feed_url,
                error=exc,
                elapsed_ms=round((time.perf_counter() - source_started) * 1000),
            )
    logger.log("feed_parse_summary", raw_count=len(raw_candidates), source_error_count=len(source_errors))
    recent = filter_recent_candidates(raw_candidates, now=now, days=days, include_unknown_dates=bool(config.get("include_unknown_dates", False)))
    logger.log("date_filter_summary", input_count=len(raw_candidates), kept_count=len(recent), dropped_count=len(raw_candidates) - len(recent), days=days)
    deduped = deduplicate_candidates(recent)
    logger.log("dedupe_summary", input_count=len(recent), kept_count=len(deduped), dropped_count=len(recent) - len(deduped))
    if fetch_full_text:
        fetch_success = 0
        fetch_error = 0
        for item in deduped:
            article_started = time.perf_counter()
            logger.log("article_fetch_start", source=item.source, category=item.category, title=item.title, url=item.url)
            text, error = extract_article_text(session, item.url, timeout=timeout, max_chars=int(config.get("max_article_chars", 6000)))
            item.extracted_text = text
            if error:
                item.errors.append(error)
                fetch_error += 1
                logger.log("article_fetch_error", source=item.source, category=item.category, title=item.title, url=item.url, error=error, elapsed_ms=round((time.perf_counter() - article_started) * 1000))
            else:
                fetch_success += 1
                logger.log("article_fetch_success", source=item.source, category=item.category, title=item.title, url=item.url, text_chars=len(text), elapsed_ms=round((time.perf_counter() - article_started) * 1000))
        logger.log("article_fetch_summary", attempted_count=len(deduped), success_count=fetch_success, error_count=fetch_error)
    for item in deduped:
        item.score = score_candidate(item)
    logger.log(
        "scoring_summary",
        scored_count=len(deduped),
        top_scores=[{"category": item.category, "source": item.source, "title": item.title, "score": item.score} for item in sorted(deduped, key=lambda i: i.score, reverse=True)[:10]],
    )
    grouped: dict[str, list[ArticleCandidate]] = {"dev": [], "econ": []}
    for item in sorted(deduped, key=lambda i: i.score, reverse=True):
        grouped.setdefault(item.category, [])
        if len(grouped[item.category]) < per_category:
            grouped[item.category].append(item)
    logger.log("selection_summary", selected_counts={category: len(items) for category, items in grouped.items()}, per_category=per_category)
    result = {
        "generated_at": now.isoformat(),
        "window_days": days,
        "policy": config.get("policy", {}),
        "source_errors": source_errors,
        "candidates": {category: [item.to_jsonable() for item in items] for category, items in grouped.items()},
    }
    logger.log("collection_finish", dev_count=len(result["candidates"].get("dev", [])), econ_count=len(result["candidates"].get("econ", [])), source_error_count=len(source_errors))
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect RSS/article candidates for the daily Korean dev/economy briefing.")
    parser.add_argument("--config", default="config/sources.toml", help="TOML source config path")
    parser.add_argument("--output", default="output/candidates.json", help="JSON output path")
    parser.add_argument("--days", type=int, default=1, help="Recent window in days")
    parser.add_argument("--per-category", type=int, default=12, help="Max candidates per category for LLM selection")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds")
    parser.add_argument("--event-log", default="output/events.jsonl", help="Append structured JSONL collection events to this path; use empty string to disable")
    parser.add_argument("--run-id", default=None, help="Stable run id for correlating event log rows")
    parser.add_argument("--no-full-text", action="store_true", help="Skip fetching article pages; RSS metadata only")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config_path = Path(args.config)
    output_path = Path(args.output)
    config = load_config(config_path)
    event_logger = CollectionEventLogger(Path(args.event_log), run_id=args.run_id) if args.event_log else None
    result = collect_candidates(
        config=config,
        days=args.days,
        per_category=args.per_category,
        fetch_full_text=not args.no_full_text,
        timeout=args.timeout,
        event_logger=event_logger,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output_path} dev={len(result['candidates'].get('dev', []))} econ={len(result['candidates'].get('econ', []))} errors={len(result['source_errors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
