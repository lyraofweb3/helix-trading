"""Liquidity sweep / mean reversion / structure reversal."""

from __future__ import annotations

from typing import Any

from helix_v1.strategies.base import StrategySignal


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class ReversalStrategy:
    name = "reversal"

    def evaluate(self, snapshot: dict[str, Any], structure: dict[str, Any] | None, regime: Any) -> StrategySignal:
        regime_name = getattr(regime, "regime", "uncertain")
        rsi = _f(snapshot.get("rsi"))
        structure = structure or snapshot.get("structure") or {}
        reasons: list[str] = []
        direction = "flat"
        score = 0.0
        conf = 0.25

        # Prefer range / uncertain / exhaustion
        if regime_name in ("strong_trend", "breakout"):
            return StrategySignal(self.name, "flat", 0.0, 0.15, ["avoid_reversal_in_trend"], [])

        premium = structure.get("premium_discount") or structure.get("location")
        if rsi is not None and rsi >= 72 and premium in ("premium", "above_eq", None):
            direction, score, conf = "sell", -0.4, 0.45
            reasons.append("mean_reversion_premium")
        elif rsi is not None and rsi <= 28 and premium in ("discount", "below_eq", None):
            direction, score, conf = "buy", 0.4, 0.45
            reasons.append("mean_reversion_discount")

        if structure.get("liquidity_sweep") or structure.get("sweep"):
            sweep = structure.get("liquidity_sweep") or structure.get("sweep")
            if sweep in ("high", "buy_side"):
                direction, score, conf = "sell", -0.55, 0.55
                reasons.append("buy_side_liquidity_sweep")
            elif sweep in ("low", "sell_side"):
                direction, score, conf = "buy", 0.55, 0.55
                reasons.append("sell_side_liquidity_sweep")

        if not reasons:
            reasons.append("no_reversal_trigger")

        return StrategySignal(self.name, direction, score, conf, reasons, ["reversal"])
