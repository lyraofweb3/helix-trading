"""HELIX Champion Cycle — scan the universe, act only on the top-ranked setup.

Quality over quantity: if nothing clears the gate, hold. Additive module.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from helix_v1.idea_engine import ideas_payload
from helix_v1.modes import TradingMode, current_mode
from helix_v1.pipeline import run_helix_cycle
from helix_v1.scanner import DEFAULT_UNIVERSE, scan_market
from helix_v1.signal_fusion import FusionState

logger = logging.getLogger(__name__)


# Symbol → headline keyword hints (auto market intelligence)
_NEWS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "EURUSD": ("euro", "ecb", "eurozone", "eur/", "germany", "lagarde"),
    "GBPUSD": ("pound", "sterling", "boe", "uk ", "britain", "bailey"),
    "USDJPY": ("yen", "boj", "japan", "usd/jpy", "tokyo"),
    "AUDUSD": ("aussie", "australia", "rba", "aud/"),
    "USDCAD": ("loonie", "canada", "boc", "oil", "cad"),
    "USDCHF": ("swiss", "snb", "franc", "chf"),
    "XAUUSD": ("gold", "xau", "bullion", "safe haven", "yield"),
    "XAGUSD": ("silver", "xag", "bullion", "industrial metal", "safe haven"),
    "USOIL": ("oil", "wti", "crude", "opec", "petroleum", "inventory"),
    "UKOIL": ("brent", "oil", "opec", "crude", "north sea"),
}


def news_bias_for_symbol(symbol: str, headlines: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Score how news leans for a symbol. Returns bias buy/sell/flat + heat 0..1."""
    if not headlines:
        return {"bias": "flat", "heat": 0.0, "hits": 0, "titles": []}
    keys = _NEWS_KEYWORDS.get(symbol.upper(), (symbol[:3].lower(),))
    # Generic tone words. Asset-specific overrides below.
    bull = ("rally", "surge", "gain", "hawkish", "beat", "growth", "demand", "risk-on", "strong", "climb", "jump")
    bear = ("fall", "drop", "slide", "dovish", "miss", "recession", "risk-off", "weak", "slash", "plunge", "tumble")
    # Gold/oil often *rise* on geopolitical stress — do not treat "war" as bear for them
    if symbol.upper() not in {"XAUUSD", "XAGUSD", "USOIL", "UKOIL"}:
        bear = bear + ("war", "conflict")
    else:
        bull = bull + ("war", "safe haven", "geopolit")
    hits = 0
    bull_n = bear_n = 0
    titles: list[str] = []
    for h in headlines:
        title = str(h.get("title") or "").lower()
        if not any(k in title for k in keys):
            continue
        hits += 1
        titles.append(str(h.get("title") or "")[:120])
        if any(b in title for b in bull):
            bull_n += 1
        if any(b in title for b in bear):
            bear_n += 1
    if hits == 0:
        return {"bias": "flat", "heat": 0.0, "hits": 0, "titles": []}
    heat = min(1.0, hits / 4.0)
    if bull_n > bear_n:
        bias = "buy"
    elif bear_n > bull_n:
        bias = "sell"
    else:
        bias = "flat"
    return {"bias": bias, "heat": heat, "hits": hits, "titles": titles[:5]}



def _soft_weights() -> dict[str, float]:
    """Optional soft multipliers from learning suggestions (never rewrite live logic)."""
    try:
        from helix_v1.learning import latest_suggestions

        sug = latest_suggestions()
        weights = (sug or {}).get("weights") or {}
        if isinstance(weights, dict):
            return {str(k): float(v) for k, v in weights.items() if isinstance(v, (int, float))}
    except Exception:  # noqa: BLE001
        pass
    return {}


def rank_score(row: dict[str, Any], weights: dict[str, float] | None = None) -> float:
    """Composite champion score: fusion + confluence + idea odds + soft weights."""
    score = float(row.get("score") or 0.0)  # 0..1
    conf = float(row.get("confluence") or 0)
    odds = float(row.get("idea_odds") or 0.0) / 100.0  # 0..1
    state = str(row.get("state") or "")
    action = str(row.get("action") or "hold")

    news_heat = float(row.get("news_heat") or 0.0)
    news_bias = str(row.get("news_bias") or "flat")
    base = score * 0.45 + min(conf / 8.0, 1.0) * 0.22 + odds * 0.18 + news_heat * 0.15
    if state in (FusionState.HIGH_CONFIDENCE.value, "HIGH_CONFIDENCE", "HIGH_CONFIDENCE_SETUP"):
        base += 0.08
    elif state in (FusionState.VALID_SETUP.value, "VALID_SETUP"):
        base += 0.04
    if action in ("buy", "sell") and news_bias == action:
        base += 0.06 * news_heat
    elif action in ("buy", "sell") and news_bias in ("buy", "sell") and news_bias != action:
        base *= 0.75  # news conflict — demote
    if action not in ("buy", "sell"):
        base *= 0.35

    w = weights or {}
    regime = ((row.get("regime") or {}) if isinstance(row.get("regime"), dict) else {})
    reg_name = str(regime.get("regime") or "")
    if reg_name and reg_name in w:
        base *= max(0.5, min(1.5, w[reg_name]))
    channel = str(row.get("idea_channel") or "")
    if channel and channel in w:
        base *= max(0.5, min(1.5, w[channel]))
    return max(0.0, min(1.0, base))


def enrich_scan_row(row: dict[str, Any], snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    out = dict(row)
    try:
        if snapshot is None:
            from helix_v1.trade_style import is_scalp
            if is_scalp():
                from helix_v1.scalp import build_scalp_snapshot
                snapshot = build_scalp_snapshot(row["symbol"])
            else:
                from helix.brain import build_market_snapshot
                snapshot = build_market_snapshot(row["symbol"])
        ideas = ideas_payload(snapshot)
        top = ideas.get("top") or {}
        out["idea_odds"] = float(top.get("odds") or 0.0)
        out["idea_channel"] = str(top.get("channel") or "")
        out["idea_thesis"] = str(top.get("thesis") or "")
        out["idea_engine"] = ideas
    except Exception as exc:  # noqa: BLE001
        logger.warning("idea enrich failed for %s: %s", row.get("symbol"), type(exc).__name__)
        out["idea_odds"] = 0.0
        out["idea_channel"] = ""
    out["champion_score"] = rank_score(out, _soft_weights())
    return out


def champion_scan(
    symbols: list[str] | None = None,
    headlines: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if headlines is None:
        try:
            from helix.news import fetch_headlines
            headlines = fetch_headlines()
        except Exception as exc:  # noqa: BLE001
            logger.warning("champion news fetch failed: %s", type(exc).__name__)
            headlines = []
    rows = scan_market(symbols or DEFAULT_UNIVERSE)
    enriched: list[dict[str, Any]] = []
    for r in rows:
        e = enrich_scan_row(r)
        nb = news_bias_for_symbol(str(e.get("symbol") or ""), headlines)
        e["news_bias"] = nb["bias"]
        e["news_heat"] = nb["heat"]
        e["news_hits"] = nb["hits"]
        e["news_titles"] = nb["titles"]
        e["champion_score"] = rank_score(e, _soft_weights())
        enriched.append(e)
    enriched.sort(key=lambda r: float(r.get("champion_score") or 0), reverse=True)
    return enriched


def run_champion_cycle(
    *,
    symbols: list[str] | None = None,
    mode: TradingMode | str | None = None,
    min_champion_score: float | None = None,
    min_confluence: int = 3,
    require_valid_state: bool = True,
) -> dict[str, Any]:
    """
    Scan → pick #1 → run full HELIX cycle only on that symbol if it clears gates.
    Otherwise write a hold and report why.
    """
    min_score = min_champion_score
    if min_score is None:
        min_score = float(os.environ.get("HELIX_CHAMPION_MIN_SCORE", "0.55") or 0.55)

    try:
        from helix.news import fetch_headlines
        headlines = fetch_headlines()
    except Exception:  # noqa: BLE001
        headlines = []
    ranked = champion_scan(symbols, headlines=headlines)
    top = ranked[0] if ranked else None
    gate_fail: list[str] = []

    if not top:
        gate_fail.append("empty_universe")
    else:
        if float(top.get("champion_score") or 0) < min_score:
            gate_fail.append(f"score<{min_score}")
        if int(top.get("confluence") or 0) < min_confluence:
            gate_fail.append(f"confluence<{min_confluence}")
        if require_valid_state and str(top.get("state") or "") not in {
            FusionState.VALID_SETUP.value,
            FusionState.HIGH_CONFIDENCE.value,
            "VALID_SETUP",
            "HIGH_CONFIDENCE",
            "HIGH_CONFIDENCE_SETUP",
        }:
            gate_fail.append(f"state={top.get('state')}")
        if str(top.get("action") or "hold") not in ("buy", "sell"):
            gate_fail.append("no_directional_action")

    if gate_fail or not top:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "champion": True,
            "acted": False,
            "auto_market": True,
            "reason": "no_trade_gate",
            "gate_fail": gate_fail,
            "ranked": ranked[:10],
            "news_count": len(headlines),
            "plan": {"action": "hold", "symbol": (top or {}).get("symbol"), "rationale": "champion gate — waiting for best market"},
        }

    symbol = str(top["symbol"])
    # Quant pipeline still runs for fusion/risk/journal context…
    result = run_helix_cycle(symbol, mode=mode, headlines=headlines, use_llm=True)
    # …then Grok is the full decision brain (xAI → OpenAI → Anthropic failover).
    grok_meta: dict[str, Any] = {}
    try:
        from helix.config import llm_brain_enabled
        from helix.brain import build_market_snapshot, _decide_with_failover
        from helix.decision import TradeDecision
        from helix.brain import write_signal

        if llm_brain_enabled():
            snap = build_market_snapshot(symbol)
            if headlines:
                snap = {**snap, "headlines": headlines}
            decision, used_client, provider = _decide_with_failover(symbol, snap, headlines or [])
            # Keep risk veto: if quant risk rejected entries, force hold unless Grok says close
            risk = ((result.get("plan") or {}).get("meta") or {}).get("risk") or result.get("risk") or {}
            if isinstance(risk, dict) and risk.get("approved") is False and decision.action in {"buy", "sell"}:
                decision = TradeDecision(
                    action="hold",
                    symbol=decision.symbol,
                    confidence=decision.confidence,
                    rationale=f"grok:{decision.action} vetoed by risk ({risk.get('code') or risk.get('reasons')})",
                    stop_hint=decision.stop_hint,
                    take_hint=decision.take_hint,
                )
            path = write_signal(
                decision,
                meta={
                    "auto_market": True,
                    "champion": True,
                    "picked": top,
                    "provider": provider,
                    "model": getattr(used_client, "model", None),
                    "brain": "xai_grok_full",
                    "quant_plan": result.get("plan"),
                },
            )
            plan = {
                "action": decision.action,
                "symbol": decision.symbol,
                "confidence": decision.confidence,
                "rationale": decision.rationale,
                "stop_hint": decision.stop_hint,
                "take_hint": decision.take_hint,
            }
            grok_meta = {"provider": provider, "signal_path": str(path), "plan": plan}
            result = {**result, "plan": plan, "grok": grok_meta}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Grok full-brain layer failed (%s); keeping quant plan", type(exc).__name__)
        grok_meta = {"error": type(exc).__name__}

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "champion": True,
        "acted": True,
        "auto_market": True,
        "picked": top,
        "ranked": ranked[:10],
        "news_count": len(headlines),
        "result": result,
        "plan": result.get("plan"),
        "brain": "xai_grok_full",
        "grok": grok_meta,
    }
