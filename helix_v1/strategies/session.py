"""Session awareness: Asia / London / NY / overlap."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from helix_v1.strategies.base import StrategySignal


def _session_utc(hour: int) -> str:
    # Rough FX session windows in UTC
    if 0 <= hour < 7:
        return "asia"
    if 7 <= hour < 8:
        return "asia_london"
    if 8 <= hour < 12:
        return "london"
    if 12 <= hour < 16:
        return "london_ny"
    if 16 <= hour < 21:
        return "ny"
    return "off"


class SessionStrategy:
    name = "session"

    def evaluate(self, snapshot: dict[str, Any], structure: dict[str, Any] | None, regime: Any) -> StrategySignal:
        now = datetime.now(timezone.utc)
        sess = _session_utc(now.hour)
        bias = getattr(regime, "trend_bias", "neutral")
        reasons = [f"session={sess}"]
        direction = "flat"
        score = 0.0
        conf = 0.25

        # Overlaps favor continuation with bias
        if sess in ("london_ny", "london") and bias == "bullish":
            direction, score, conf = "buy", 0.25, 0.4
            reasons.append("session_supports_long")
        elif sess in ("london_ny", "london") and bias == "bearish":
            direction, score, conf = "sell", -0.25, 0.4
            reasons.append("session_supports_short")
        elif sess == "asia":
            reasons.append("asia_range_bias")
            conf = 0.3
            if getattr(regime, "regime", "") == "range":
                conf = 0.35
        elif sess == "off":
            reasons.append("thin_liquidity_hours")
            conf = 0.15

        return StrategySignal(self.name, direction, score, conf, reasons, ["session", sess])
