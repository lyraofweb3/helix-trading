"""Trend following / continuation / pullback."""

from __future__ import annotations

from typing import Any

from helix_v1.strategies.base import StrategySignal


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class TrendStrategy:
    name = "trend"

    def evaluate(self, snapshot: dict[str, Any], structure: dict[str, Any] | None, regime: Any) -> StrategySignal:
        regime_name = getattr(regime, "regime", None) or (regime or {}).get("regime")
        bias = getattr(regime, "trend_bias", None) or (regime or {}).get("trend_bias", "neutral")
        ema_f = _f(snapshot.get("ema_fast"))
        ema_s = _f(snapshot.get("ema_slow"))
        last = _f(snapshot.get("last_close") or snapshot.get("bid"))
        reasons: list[str] = []
        direction = "flat"
        score = 0.0
        conf = 0.0

        if regime_name not in ("strong_trend", "weak_trend", "breakout"):
            return StrategySignal(self.name, "flat", 0.0, 0.15, ["regime_not_trend"], ["skip"])

        if ema_f is None or ema_s is None or last is None:
            return StrategySignal(self.name, "flat", 0.0, 0.1, ["missing_emas"], [])

        if bias == "bullish" and ema_f > ema_s:
            direction = "buy"
            score = 0.55 if regime_name == "weak_trend" else 0.75
            # pullback: price near slow ema
            if abs(last - ema_s) / max(abs(ema_s), 1e-9) < 0.001:
                score += 0.1
                reasons.append("pullback_to_ema_slow")
            reasons.append("bullish_ema_stack")
            conf = 0.55 + (0.2 if regime_name == "strong_trend" else 0.05)
        elif bias == "bearish" and ema_f < ema_s:
            direction = "sell"
            score = -0.55 if regime_name == "weak_trend" else -0.75
            if abs(last - ema_s) / max(abs(ema_s), 1e-9) < 0.001:
                score -= 0.1
                reasons.append("pullback_to_ema_slow")
            reasons.append("bearish_ema_stack")
            conf = 0.55 + (0.2 if regime_name == "strong_trend" else 0.05)
        else:
            reasons.append("bias_ema_conflict")
            conf = 0.2

        return StrategySignal(self.name, direction, float(score), float(min(0.95, conf)), reasons, ["trend"])
