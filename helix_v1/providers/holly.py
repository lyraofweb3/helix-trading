"""Trade Ideas — Holly AI adapter for HELIX.

Fuses Holly trade ideas into HELIX without replacing the quant brain or MT5 EA.

Ingest paths (credentials optional — clean integration points):
  1. POST webhook JSON → /api/v1/holly/ingest
  2. Drop file at HELIX_HOLLY_IDEAS_PATH (default data/holly_ideas.json)
  3. Env TRADE_IDEAS_API_KEY / HOLLY_API_KEY for future live API poll
     (interface ready; live poll enabled when key + HOLLY_API_URL set)

Normalized idea shape:
  { symbol, side: buy|sell|flat, confidence: 0..1, thesis, source, ts, meta }
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class HollyIdea:
    symbol: str
    side: str  # buy | sell | flat
    confidence: float
    thesis: str = ""
    source: str = "trade_ideas_holly"
    ts: str = ""
    strategy: str = ""
    timeframe: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HollyProvider(Protocol):
    name: str

    def fetch_ideas(self, symbol: str | None = None) -> list[HollyIdea]: ...


def ideas_path() -> Path:
    env = os.environ.get("HELIX_HOLLY_IDEAS_PATH", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "holly_ideas.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_side(v: Any) -> str:
    s = str(v or "flat").strip().lower()
    if s in {"buy", "long", "b", "call"}:
        return "buy"
    if s in {"sell", "short", "s", "put"}:
        return "sell"
    return "flat"


def _norm_symbol(v: Any) -> str:
    return str(v or "").strip().upper().replace("/", "").replace("=", "")


def parse_idea(raw: dict[str, Any]) -> HollyIdea | None:
    """Accept Holly / Trade Ideas-like payloads from webhook or file."""
    if not isinstance(raw, dict):
        return None
    # Common field aliases from alert exports / OEM payloads
    symbol = _norm_symbol(
        raw.get("symbol")
        or raw.get("ticker")
        or raw.get("Symbol")
        or raw.get("sym")
    )
    if not symbol:
        return None
    side = _norm_side(
        raw.get("side")
        or raw.get("action")
        or raw.get("direction")
        or raw.get("signal")
        or raw.get("Type")
    )
    conf_raw = raw.get("confidence", raw.get("score", raw.get("strength", raw.get("odds"))))
    try:
        conf = float(conf_raw) if conf_raw is not None else 0.55
    except (TypeError, ValueError):
        conf = 0.55
    if conf > 1.0:
        conf = conf / 100.0
    conf = max(0.0, min(1.0, conf))
    thesis = str(
        raw.get("thesis")
        or raw.get("reason")
        or raw.get("rationale")
        or raw.get("description")
        or raw.get("Alert")
        or "Holly AI trade idea"
    )
    return HollyIdea(
        symbol=symbol,
        side=side,
        confidence=conf,
        thesis=thesis[:500],
        source=str(raw.get("source") or "trade_ideas_holly"),
        ts=str(raw.get("ts") or raw.get("time") or _now()),
        strategy=str(raw.get("strategy") or raw.get("channel") or "holly"),
        timeframe=str(raw.get("timeframe") or raw.get("tf") or ""),
        meta={k: v for k, v in raw.items() if k not in {"symbol", "ticker", "side", "action"}},
    )


def load_ideas_file(path: Path | None = None) -> list[HollyIdea]:
    p = path or ideas_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Holly ideas file unreadable: %s", type(exc).__name__)
        return []
    items = data if isinstance(data, list) else data.get("ideas") or data.get("alerts") or []
    out: list[HollyIdea] = []
    for raw in items:
        idea = parse_idea(raw) if isinstance(raw, dict) else None
        if idea:
            out.append(idea)
    return out


def save_ideas(ideas: list[HollyIdea], path: Path | None = None) -> Path:
    p = path or ideas_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": _now(),
        "source": "trade_ideas_holly",
        "ideas": [i.to_dict() for i in ideas],
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def ingest_payload(body: dict[str, Any] | list[Any]) -> list[HollyIdea]:
    """Merge webhook body into stored ideas file (append + dedupe by symbol+side+ts)."""
    existing = load_ideas_file()
    incoming: list[HollyIdea] = []
    if isinstance(body, list):
        for raw in body:
            if isinstance(raw, dict):
                idea = parse_idea(raw)
                if idea:
                    incoming.append(idea)
    elif isinstance(body, dict):
        if "ideas" in body or "alerts" in body:
            for raw in body.get("ideas") or body.get("alerts") or []:
                if isinstance(raw, dict):
                    idea = parse_idea(raw)
                    if idea:
                        incoming.append(idea)
        else:
            idea = parse_idea(body)
            if idea:
                incoming.append(idea)
    # Keep last 200
    merged = existing + incoming
    # light dedupe
    seen: set[str] = set()
    uniq: list[HollyIdea] = []
    for i in reversed(merged):
        key = f"{i.symbol}|{i.side}|{i.ts}|{i.thesis[:40]}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(i)
    uniq.reverse()
    save_ideas(uniq[-200:])
    return incoming


class FileHollyProvider:
    """Reads dropped / webhook-persisted Holly ideas."""

    name = "holly_file"

    def fetch_ideas(self, symbol: str | None = None) -> list[HollyIdea]:
        ideas = load_ideas_file()
        if symbol:
            sym = _norm_symbol(symbol)
            # Also match Exness m-suffix
            ideas = [i for i in ideas if i.symbol == sym or i.symbol + "M" == sym or i.symbol == sym.rstrip("M")]
        return ideas


class ApiHollyProvider:
    """
    Live Trade Ideas / Holly API poller.
    Requires HOLLY_API_URL + (TRADE_IDEAS_API_KEY or HOLLY_API_KEY).
    Until credentials are set, returns [] cleanly.
    """

    name = "holly_api"

    def __init__(self) -> None:
        self.base = os.environ.get("HOLLY_API_URL", "").strip()
        self.key = (
            os.environ.get("TRADE_IDEAS_API_KEY", "").strip()
            or os.environ.get("HOLLY_API_KEY", "").strip()
        )

    @property
    def configured(self) -> bool:
        return bool(self.base and self.key)

    def fetch_ideas(self, symbol: str | None = None) -> list[HollyIdea]:
        if not self.configured:
            return []
        try:
            import httpx
        except ImportError:
            logger.warning("httpx missing for Holly API")
            return []
        headers = {
            "Authorization": f"Bearer {self.key}",
            "X-API-Key": self.key,
            "Accept": "application/json",
        }
        params: dict[str, str] = {}
        if symbol:
            params["symbol"] = _norm_symbol(symbol)
        try:
            with httpx.Client(timeout=20.0) as client:
                r = client.get(self.base, headers=headers, params=params)
                r.raise_for_status()
                data = r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Holly API fetch failed: %s", type(exc).__name__)
            return []
        body = data if isinstance(data, (dict, list)) else {}
        return ingest_payload(body)  # also persists


def collect_holly_ideas(symbol: str | None = None) -> list[HollyIdea]:
    """Merge file + API providers for a symbol (or all)."""
    ideas: list[HollyIdea] = []
    ideas.extend(FileHollyProvider().fetch_ideas(symbol))
    api = ApiHollyProvider()
    if api.configured:
        ideas.extend(api.fetch_ideas(symbol))
    # Prefer highest confidence per symbol+side
    best: dict[str, HollyIdea] = {}
    for i in ideas:
        k = f"{i.symbol}|{i.side}"
        if k not in best or i.confidence > best[k].confidence:
            best[k] = i
    return list(best.values())


def holly_vote_for_symbol(symbol: str) -> dict[str, Any]:
    """Summary vote HELIX can fuse — never executes alone."""
    ideas = collect_holly_ideas(symbol)
    if not ideas:
        return {
            "available": False,
            "side": "flat",
            "confidence": 0.0,
            "ideas": [],
            "provider_configured": ApiHollyProvider().configured,
            "file_path": str(ideas_path()),
        }
    buy = [i for i in ideas if i.side == "buy"]
    sell = [i for i in ideas if i.side == "sell"]
    if buy and (not sell or max(i.confidence for i in buy) >= max(i.confidence for i in sell)):
        side = "buy"
        conf = max(i.confidence for i in buy)
        thesis = buy[0].thesis
    elif sell:
        side = "sell"
        conf = max(i.confidence for i in sell)
        thesis = sell[0].thesis
    else:
        side, conf, thesis = "flat", 0.0, ""
    return {
        "available": True,
        "side": side,
        "confidence": conf,
        "thesis": thesis,
        "ideas": [i.to_dict() for i in ideas],
        "provider_configured": ApiHollyProvider().configured,
        "file_path": str(ideas_path()),
    }
