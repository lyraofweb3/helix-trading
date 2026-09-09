"""Fetch recent forex-related headlines from free public RSS feeds. Fail soft."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

from helix.config import NEWS_FEEDS, NEWS_LOOKBACK_HOURS, NEWS_MAX_HEADLINES

logger = logging.getLogger(__name__)


def _parse_published(entry: dict[str, Any]) -> datetime | None:
    for key in ("published", "updated", "created"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
    # feedparser structured time
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            try:
                return datetime(*st[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _fetch_feed(name: str, url: str, client: httpx.Client) -> list[dict[str, Any]]:
    """Download and parse one RSS feed. Returns [] on any failure."""
    try:
        resp = client.get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:  # noqa: BLE001 — fail soft
        logger.warning("News feed %s failed: %s", name, type(exc).__name__)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)
    items: list[dict[str, Any]] = []
    for entry in parsed.entries or []:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        published = _parse_published(entry)
        if published and published < cutoff:
            continue
        link = (entry.get("link") or "").strip()
        items.append(
            {
                "title": title,
                "source": name,
                "published": published.isoformat() if published else None,
                "url": link or None,
            }
        )
    return items


def fetch_headlines(max_items: int = NEWS_MAX_HEADLINES) -> list[dict[str, Any]]:
    """
    Pull recent headlines from configured RSS feeds.
    Returns list of {title, source, published, url}. Dedupes by title.
    """
    seen: set[str] = set()
    headlines: list[dict[str, Any]] = []

    with httpx.Client(
        timeout=15.0,
        follow_redirects=True,
        headers={"User-Agent": "HELIX-Brain/0.1 (forex research; demo)"},
    ) as client:
        for feed in NEWS_FEEDS:
            for item in _fetch_feed(feed["name"], feed["url"], client):
                key = item["title"].lower()
                if key in seen:
                    continue
                seen.add(key)
                headlines.append(item)

    # Prefer items with a published timestamp, newest first
    def sort_key(h: dict[str, Any]) -> str:
        return h.get("published") or ""

    headlines.sort(key=sort_key, reverse=True)
    return headlines[:max_items]
