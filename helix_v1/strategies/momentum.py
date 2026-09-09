"""Momentum continuation / exhaustion."""

from __future__ import annotations

from typing import Any

from helix_v1.strategies.base import StrategySignal


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class MomentumStrategy:
    name = "momentum"

    def evaluate(self, snapshot: dict[str, Any], structure: dict[str, Any] | None, regime: Any) -> StrategySignal:
        rsi = _f(snapshot.get("rsi"))
        bias = getattr(regime, "trend_bias", "neutral")
        reasons: list[str] = []
        if rsi is None:
            return StrategySignal(self.name, "flat", 0.0, 0.1, ["no_rsi"], [])

        direction = "flat"
        score = 0.0
        conf = 0.35

        if 55 <= rsi <= 68 and bias == "bullish":
            direction, score, conf = "buy", 0.45, 0.5
            reasons.append("bull_momentum_continuation")
        elif 32 <= rsi <= 45 and bias == "bearish":
            direction, score, conf = "sell", -0.45, 0.5
            reasons.append("bear_momentum_continuation")
        elif rsi >= 75:
            direction, score, conf = "sell", -0.25, 0.4
            reasons.append("momentum_exhaustion_long")
        elif rsi <= 25:
            direction, score, conf = "buy", 0.25, 0.4
            reasons.append("momentum_exhaustion_short")
        else:
            reasons.append("momentum_neutral")

        return StrategySignal(self.name, direction, score, conf, reasons, ["momentum"])
