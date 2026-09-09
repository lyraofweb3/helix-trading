"""Economic calendar interface for HELIX 1.0.

Free HTML/RSS best-effort providers plus NullCalendar / EnvCalendar placeholders.
No paid APIs. Fail soft.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    when: datetime
    title: str
    currency: str | None = None
    impact: str = "unknown"  # low / medium / high / unknown
    source: str = ""
    url: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "when": self.when.isoformat(),
            "title": self.title,
            "currency": self.currency,
            "impact": self.impact,
            "source": self.source,
            "url": self.url,
            "meta": self.meta,
        }


@runtime_checkable
class EconomicCalendarProvider(Protocol):
    """Protocol for economic calendar backends."""

    name: str

    def upcoming(
        self,
        *,
        lookback_hours: float = 1.0,
        lookahead_hours: float = 24.0,
        currencies: list[str] | None = None,
    ) -> list[CalendarEvent]:
        """Return events in [now-lookback, now+lookahead]."""
        ...

    def high_impact_blackout(
        self,
        *,
        buffer_minutes: int = 45,
        currencies: list[str] | None = None,
    ) -> bool:
        """True if we are inside a blackout window around a high-impact event."""
        ...


class NullCalendar:
    """Always empty — safe default when no calendar is configured."""

    name = "null"

    def upcoming(
        self,
        *,
        lookback_hours: float = 1.0,
        lookahead_hours: float = 24.0,
        currencies: list[str] | None = None,
    ) -> list[CalendarEvent]:
        return []

    def high_impact_blackout(
        self,
        *,
        buffer_minutes: int = 45,
        currencies: list[str] | None = None,
    ) -> bool:
        return False


class EnvCalendar:
    """Placeholder driven by HELIX_CALENDAR_EVENTS env (pipe-separated titles).

    Format (optional): TITLE@YYYY-MM-DDTHH:MMZ|TITLE2
    If no timestamp, events are treated as "now" for blackout testing only.
    """

    name = "env"

    def __init__(self, raw: str | None = None) -> None:
        self._raw = raw if raw is not None else os.environ.get("HELIX_CALENDAR_EVENTS", "")

    def _parse(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        now = datetime.now(timezone.utc)
        for part in (self._raw or "").split("|"):
            part = part.strip()
            if not part:
                continue
            title, when = part, now
            impact = "high"
            if "@" in part:
                title, ts = part.split("@", 1)
                title = title.strip()
                ts = ts.strip()
                try:
                    if ts.endswith("Z"):
                        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        when = datetime.fromisoformat(ts)
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                except ValueError:
                    when = now
            events.append(
                CalendarEvent(
                    when=when,
                    title=title or "env-event",
                    impact=impact,
                    source="env",
                )
            )
        return events

    def upcoming(
        self,
        *,
        lookback_hours: float = 1.0,
        lookahead_hours: float = 24.0,
        currencies: list[str] | None = None,
    ) -> list[CalendarEvent]:
        now = datetime.now(timezone.utc)
        lo = now - timedelta(hours=lookback_hours)
        hi = now + timedelta(hours=lookahead_hours)
        out = [e for e in self._parse() if lo <= e.when <= hi]
        if currencies:
            # Env events rarely have currency; keep all
            pass
        return out

    def high_impact_blackout(
        self,
        *,
        buffer_minutes: int = 45,
        currencies: list[str] | None = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        buf = timedelta(minutes=buffer_minutes)
        for e in self._parse():
            if e.impact.lower() != "high":
                continue
            if abs((e.when - now).total_seconds()) <= buf.total_seconds():
                return True
        return False


class RssCalendar:
    """Best-effort: parse public forex RSS headlines as soft calendar hints.

    Not a true economic calendar — titles mentioning NFP/CPI/FOMC/rate are
    tagged high impact. Uses feedparser if available; else empty.
    """

    name = "rss"

    DEFAULT_FEEDS = (
        "https://www.forexlive.com/feed",
        "https://www.federalreserve.gov/feeds/press_all.xml",
    )

    HIGH_KEYWORDS = re.compile(
        r"\b(NFP|non[- ]?farm|CPI|FOMC|interest rate|rate decision|ECB|Fed |payroll)\b",
        re.I,
    )

    def __init__(self, feeds: list[str] | None = None) -> None:
        self.feeds = list(feeds or self.DEFAULT_FEEDS)

    def upcoming(
        self,
        *,
        lookback_hours: float = 1.0,
        lookahead_hours: float = 24.0,
        currencies: list[str] | None = None,
    ) -> list[CalendarEvent]:
        try:
            import feedparser  # type: ignore
        except ImportError:
            logger.info("RssCalendar: feedparser not installed")
            return []

        import httpx

        now = datetime.now(timezone.utc)
        lo = now - timedelta(hours=max(lookback_hours, 24.0))  # RSS is backward-looking
        events: list[CalendarEvent] = []
        headers = {"User-Agent": "HELIX-Calendar/1.0 (research)"}
        for url in self.feeds:
            try:
                with httpx.Client(timeout=15.0, follow_redirects=True, headers=headers) as client:
                    resp = client.get(url)
                    resp.raise_for_status()
                    parsed = feedparser.parse(resp.text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("RssCalendar feed failed %s: %s", url, type(exc).__name__)
                continue
            for entry in getattr(parsed, "entries", [])[:30]:
                title = str(getattr(entry, "title", "") or "")
                published = getattr(entry, "published_parsed", None) or getattr(
                    entry, "updated_parsed", None
                )
                when = now
                if published:
                    try:
                        when = datetime(*published[:6], tzinfo=timezone.utc)
                    except Exception:  # noqa: BLE001
                        when = now
                if when < lo:
                    continue
                impact = "high" if self.HIGH_KEYWORDS.search(title) else "low"
                link = getattr(entry, "link", None)
                events.append(
                    CalendarEvent(
                        when=when,
                        title=title[:200],
                        impact=impact,
                        source="rss",
                        url=str(link) if link else url,
                    )
                )
        events.sort(key=lambda e: e.when)
        return events

    def high_impact_blackout(
        self,
        *,
        buffer_minutes: int = 45,
        currencies: list[str] | None = None,
    ) -> bool:
        # RSS is lagging news, not scheduled calendar — never hard-blackout
        return False


def get_calendar(provider: str | None = None) -> EconomicCalendarProvider:
    """Factory: HELIX_CALENDAR_PROVIDER = null|env|rss (default null)."""
    name = (provider or os.environ.get("HELIX_CALENDAR_PROVIDER", "null")).strip().lower()
    if name == "env":
        return EnvCalendar()
    if name == "rss":
        return RssCalendar()
    return NullCalendar()
