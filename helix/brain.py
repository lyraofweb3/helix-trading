"""HELIX brain main loop: news → live snapshot → xAI → OpenAI → Claude → signal files."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from helix.anthropic_client import AnthropicClient
from helix.config import (
    DEFAULT_SYMBOL,
    JOURNAL_PATH,
    LATEST_SIGNAL_PATH,
    RISK_PERCENT,
    SIGNALS_DIR,
    SL_ATR_MULT,
    MIN_RR,
    MAX_DAILY_LOSS_PCT,
    MAX_POSITIONS,
    MAX_TRADES_PER_DAY,
    has_anthropic_api_key,
    has_openai_api_key,
)
from helix.decision import TradeDecision
from helix.news import fetch_headlines
from helix.openai_client import OpenAIClient
from helix.prices import fetch_snapshot
from helix.xai_client import XAIClient

logger = logging.getLogger(__name__)

ClientType = XAIClient | OpenAIClient | AnthropicClient

_PROVIDER_FAIL_EXC = (httpx.HTTPStatusError, httpx.RequestError, RuntimeError, ValueError)


def build_market_snapshot(symbol: str = DEFAULT_SYMBOL) -> dict[str, Any]:
    """
    Market snapshot with live H1 prices/indicators when the free feed works.
    On feed failure, price fields stay null + note so the model prefers hold.
    """
    prices = fetch_snapshot(symbol)
    return {
        "symbol": symbol,
        "timeframe": "H1",
        "bid": prices.get("bid"),
        "ask": prices.get("ask"),
        "spread_points": prices.get("spread_points"),
        "atr_points": prices.get("atr_points"),
        "ema_fast": prices.get("ema_fast"),
        "ema_slow": prices.get("ema_slow"),
        "ema_trend": prices.get("ema_trend"),
        "rsi": prices.get("rsi"),
        "last_close": prices.get("last_close"),
        "note": prices.get("note")
        or "Live prices not connected yet — treat as incomplete; prefer hold.",
        "price_provider": prices.get("price_provider"),
        "risk_context": {
            "risk_percent": RISK_PERCENT,
            "max_daily_loss_pct": MAX_DAILY_LOSS_PCT,
            "max_positions": MAX_POSITIONS,
            "max_trades_per_day": MAX_TRADES_PER_DAY,
            "min_rr": MIN_RR,
            "sl_atr_mult": SL_ATR_MULT,
        },
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def _ensure_signals_dir() -> None:
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)


def write_signal(decision: TradeDecision, meta: dict[str, Any] | None = None) -> Path:
    """Write latest.json and append one line to journal.jsonl."""
    _ensure_signals_dir()
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": decision.action,
        "symbol": decision.symbol,
        "confidence": decision.confidence,
        "rationale": decision.rationale,
        "stop_hint": decision.stop_hint,
        "take_hint": decision.take_hint,
        "source": "helix-brain",
        "meta": meta or {},
    }
    text = json.dumps(payload, ensure_ascii=False)
    LATEST_SIGNAL_PATH.write_text(text + "\n", encoding="utf-8")
    with JOURNAL_PATH.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return LATEST_SIGNAL_PATH


def _failure_status(exc: BaseException) -> str:
    """Safe status string for logs (no secrets)."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return str(exc.response.status_code)
    return type(exc).__name__


def _provider_name(client: ClientType) -> str:
    if isinstance(client, AnthropicClient):
        return "anthropic"
    if isinstance(client, OpenAIClient):
        return "openai"
    return "xai"


def run_once(
    symbol: str = DEFAULT_SYMBOL,
    client: ClientType | None = None,
) -> dict[str, Any]:
    """
    One brain cycle: pull news, build live snapshot, call xAI → OpenAI → Claude, write signals.
    Returns the written signal dict (no API key material).
    """
    logger.info("Fetching headlines…")
    headlines = fetch_headlines()
    logger.info("Got %d headlines", len(headlines))

    snapshot = build_market_snapshot(symbol)

    provider: str
    used_client: ClientType
    decision: TradeDecision

    if client is not None:
        # Explicit client injection (tests / forced provider)
        provider = _provider_name(client)
        logger.info("Calling %s for decision on %s…", provider, symbol)
        decision = client.analyze(snapshot, headlines)
        used_client = client
    else:
        decision, used_client, provider = _decide_with_failover(symbol, snapshot, headlines)

    logger.info(
        "Decision: %s %s conf=%.2f provider=%s model=%s",
        decision.action,
        decision.symbol,
        decision.confidence,
        provider,
        used_client.model,
    )

    path = write_signal(
        decision,
        meta={
            "headline_count": len(headlines),
            "provider": provider,
            "model": used_client.model,
            "snapshot_note": snapshot.get("note"),
        },
    )
    result = json.loads(path.read_text(encoding="utf-8"))
    return result


def _decide_with_failover(
    symbol: str,
    snapshot: dict[str, Any],
    headlines: list[dict[str, Any]],
) -> tuple[TradeDecision, ClientType, str]:
    """
    Provider order: xAI Grok → OpenAI → Anthropic Claude.
    After xAI fails (or key missing), try OpenAI if keyed; after OpenAI fails
    (or OpenAI key missing), try Anthropic if keyed.
    """
    xai_exc: BaseException | None = None

    # --- 1. xAI ---
    try:
        xai = XAIClient()
        logger.info("Calling xAI for decision on %s…", symbol)
        decision = xai.analyze(snapshot, headlines)
        return decision, xai, "xai"
    except KeyError:
        logger.warning("XAI_API_KEY missing; trying next provider")
        xai_exc = KeyError("XAI_API_KEY")
    except _PROVIDER_FAIL_EXC as exc:
        status = _failure_status(exc)
        logger.warning("xAI failed (%s); trying next provider", status)
        xai_exc = exc

    # --- 2. OpenAI ---
    openai_exc: BaseException | None = None
    if has_openai_api_key():
        try:
            oai = OpenAIClient()
            logger.info("Calling OpenAI for decision on %s…", symbol)
            decision = oai.analyze(snapshot, headlines)
            return decision, oai, "openai"
        except _PROVIDER_FAIL_EXC as exc:
            status = _failure_status(exc)
            logger.warning("OpenAI failed (%s); trying next provider", status)
            openai_exc = exc
        except KeyError as exc:
            logger.warning("OPENAI_API_KEY missing at call time; trying next provider")
            openai_exc = exc
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI failed (%s); trying next provider", type(exc).__name__)
            openai_exc = exc
    else:
        logger.warning("OpenAI fallback unavailable (no OPENAI_API_KEY)")

    # --- 3. Anthropic ---
    if has_anthropic_api_key():
        try:
            claude = AnthropicClient()
            logger.info("Calling Anthropic for decision on %s…", symbol)
            decision = claude.analyze(snapshot, headlines)
            return decision, claude, "anthropic"
        except Exception:
            logger.error("xAI, OpenAI, and Anthropic all failed")
            raise

    logger.error("All providers exhausted (no Anthropic key / prior failures)")
    if openai_exc is not None:
        raise openai_exc
    if xai_exc is not None:
        raise xai_exc
    raise RuntimeError("no AI provider available")
