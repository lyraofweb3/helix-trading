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

    base = score * 0.55 + min(conf / 8.0, 1.0) * 0.25 + odds * 0.20
    if state in (FusionState.HIGH_CONFIDENCE.value, "HIGH_CONFIDENCE", "HIGH_CONFIDENCE_SETUP"):
        base += 0.08
    elif state in (FusionState.VALID_SETUP.value, "VALID_SETUP"):
        base += 0.04
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


def champion_scan(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    rows = scan_market(symbols or DEFAULT_UNIVERSE)
    enriched = [enrich_scan_row(r) for r in rows]
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

    ranked = champion_scan(symbols)
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
            "reason": "no_trade_gate",
            "gate_fail": gate_fail,
            "ranked": ranked[:10],
            "plan": {"action": "hold", "symbol": (top or {}).get("symbol"), "rationale": "champion gate"},
        }

    symbol = str(top["symbol"])
    result = run_helix_cycle(symbol, mode=mode)
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "champion": True,
        "acted": True,
        "picked": top,
        "ranked": ranked[:10],
        "result": result,
        "plan": result.get("plan"),
    }
