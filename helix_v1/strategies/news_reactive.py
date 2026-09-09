"""Pre/post news reaction — does not blindly trade headlines."""

from __future__ import annotations

from typing import Any

from helix_v1.strategies.base import StrategySignal


class NewsReactiveStrategy:
    name = "news_reactive"

    def evaluate(self, snapshot: dict[str, Any], structure: dict[str, Any] | None, regime: Any) -> StrategySignal:
        headlines = snapshot.get("headlines") or snapshot.get("news") or []
        reasons: list[str] = []
        direction = "flat"
        score = 0.0
        conf = 0.2

        if not headlines:
            return StrategySignal(self.name, "flat", 0.0, 0.15, ["no_news_context"], ["news"])

        text = " ".join(
            (h if isinstance(h, str) else str(h.get("title") or h.get("text") or ""))
            for h in headlines[:12]
        ).lower()

        hot = any(k in text for k in ("fomc", "nfp", "cpi", "interest rate", "fed ", "ecb", "boe"))
        if hot:
            reasons.append("high_impact_keywords")
            # Prefer caution unless price already reacting with regime high_vol/breakout
            regime_name = getattr(regime, "regime", "")
            bias = getattr(regime, "trend_bias", "neutral")
            if regime_name in ("high_vol", "breakout") and bias == "bullish":
                direction, score, conf = "buy", 0.3, 0.4
                reasons.append("post_news_confirmed_bull")
            elif regime_name in ("high_vol", "breakout") and bias == "bearish":
                direction, score, conf = "sell", -0.3, 0.4
                reasons.append("post_news_confirmed_bear")
            else:
                reasons.append("news_wait_for_price_confirmation")
                conf = 0.35
        else:
            reasons.append("no_high_impact_news")

        return StrategySignal(self.name, direction, score, conf, reasons, ["news"])
