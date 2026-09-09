"""M5/M15 scalp strategy — additive; active when trade_style=scalp."""

from __future__ import annotations

from typing import Any

from helix_v1.strategies.base import StrategySignal


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class ScalpStrategy:
    name = "scalp_m5"

    def evaluate(self, snapshot: dict[str, Any], structure: dict[str, Any] | None, regime: Any) -> StrategySignal:
        style = str(snapshot.get("trade_style") or "").lower()
        if style not in {"scalp", "scalping"}:
            return StrategySignal(self.name, "flat", 0.0, 0.0, ["inactive_swing_mode"], ["scalp"])

        rsi = _f(snapshot.get("rsi"))
        e21 = _f(snapshot.get("ema21"))
        e50 = _f(snapshot.get("ema50"))
        last = _f(snapshot.get("last_close"))
        atr = _f(snapshot.get("atr"))
        bias = str(snapshot.get("scalp_bias") or getattr(regime, "trend_bias", "neutral") or "neutral")
        reasons: list[str] = []

        if last is None or rsi is None:
            return StrategySignal(self.name, "flat", 0.0, 0.15, ["no_scalp_price"], ["scalp"])

        direction = "flat"
        score = 0.0
        conf = 0.3

        # Micro pullback with M15 bias
        if bias == "bullish" and e21 and last >= e21 * 0.999 and 48 <= rsi <= 62:
            direction, score, conf = "buy", 0.55, 0.58
            reasons.append("scalp_long_pullback_m15_bull")
        elif bias == "bearish" and e21 and last <= e21 * 1.001 and 38 <= rsi <= 52:
            direction, score, conf = "sell", -0.55, 0.58
            reasons.append("scalp_short_pullback_m15_bear")
        # Momentum burst
        elif bias == "bullish" and e21 and e50 and last > e21 > e50 and 55 <= rsi <= 70:
            direction, score, conf = "buy", 0.5, 0.55
            reasons.append("scalp_long_momentum")
        elif bias == "bearish" and e21 and e50 and last < e21 < e50 and 30 <= rsi <= 45:
            direction, score, conf = "sell", -0.5, 0.55
            reasons.append("scalp_short_momentum")
        else:
            reasons.append("scalp_no_trigger")

        tags = ["scalp", "m5"]
        if atr:
            tags.append(f"atr={atr:.5f}")
        return StrategySignal(self.name, direction, score, conf, reasons, tags)
