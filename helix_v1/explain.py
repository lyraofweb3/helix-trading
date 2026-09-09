"""Auditable trade explanations."""

from __future__ import annotations

from typing import Any

from helix_v1.signal_fusion import FusionResult


def build_explanation(
    *,
    snapshot: dict[str, Any],
    regime: Any,
    fusion: FusionResult,
    risk: dict[str, Any] | None = None,
    sizing: dict[str, Any] | None = None,
    manage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    regime_d = regime.to_dict() if hasattr(regime, "to_dict") else dict(regime or {})
    why = []
    for v in fusion.votes:
        side = v.get("side") or v.get("direction")
        if side in ("buy", "sell") and (v.get("strength") or 0) > 0.05:
            why.append(f"{v.get('name')}:{side}")
    if fusion.rationale:
        why.insert(0, fusion.rationale)
    if not why:
        why = ["insufficient_positive_factors"]

    invalidation: list[str]
    if fusion.action == "buy":
        invalidation = ["break_below_structure_low", "regime_flips_bearish", "confluence_drops_below_3"]
    elif fusion.action == "sell":
        invalidation = ["break_above_structure_high", "regime_flips_bullish", "confluence_drops_below_3"]
    else:
        invalidation = ["n/a_no_trade"]

    return {
        "WHY_HELIX_ENTERED": why[:10],
        "MARKET_CONTEXT": {
            "regime": regime_d.get("regime"),
            "trend_bias": regime_d.get("trend_bias") or regime_d.get("direction"),
            "volatility": regime_d.get("volatility"),
            "symbol": snapshot.get("symbol"),
            "timeframe": snapshot.get("timeframe", "H1"),
            "rsi": snapshot.get("rsi"),
            "ema_trend": snapshot.get("ema_trend"),
        },
        "CONFIRMATIONS": {
            "confluence": fusion.confluence_count,
            "flags": fusion.confluence_flags,
            "score": fusion.helix_confidence_score,
            "state": fusion.state.value,
            "votes": fusion.votes,
        },
        "RISK": risk or {},
        "SIZING": sizing or {},
        "INVALIDATION": invalidation,
        "EXIT_LOGIC": manage
        or {
            "rules": ["thesis_invalid", "stop_hit", "target_hit", "emergency_exit", "kill_switch"],
        },
    }
