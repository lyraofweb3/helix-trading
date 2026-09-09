"""Range / volatility / structure breakouts."""

from __future__ import annotations

from typing import Any

from helix_v1.strategies.base import StrategySignal


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class BreakoutStrategy:
    name = "breakout"

    def evaluate(self, snapshot: dict[str, Any], structure: dict[str, Any] | None, regime: Any) -> StrategySignal:
        regime_name = getattr(regime, "regime", "uncertain")
        structure = structure or snapshot.get("structure") or {}
        last = _f(snapshot.get("last_close") or snapshot.get("bid"))
        pdh = _f(structure.get("pdh") or structure.get("prev_day_high"))
        pdl = _f(structure.get("pdl") or structure.get("prev_day_low"))
        reasons: list[str] = []
        direction = "flat"
        score = 0.0
        conf = 0.25

        if regime_name not in ("breakout", "high_vol", "strong_trend"):
            return StrategySignal(self.name, "flat", 0.0, 0.2, ["regime_not_breakout"], [])

        if last is not None and pdh is not None and last > pdh:
            direction, score, conf = "buy", 0.65, 0.6
            reasons.append("break_above_pdh")
        elif last is not None and pdl is not None and last < pdl:
            direction, score, conf = "sell", -0.65, 0.6
            reasons.append("break_below_pdl")
        elif structure.get("bos") or structure.get("break_of_structure"):
            bias = getattr(regime, "trend_bias", "neutral")
            if bias == "bullish":
                direction, score, conf = "buy", 0.5, 0.5
            elif bias == "bearish":
                direction, score, conf = "sell", -0.5, 0.5
            reasons.append("bos_flag")
        else:
            reasons.append("no_break_level")

        return StrategySignal(self.name, direction, score, conf, reasons, ["breakout"])
