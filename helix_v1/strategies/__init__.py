"""Strategy modules registry."""

from __future__ import annotations

from helix_v1.strategies.base import StrategySignal
from helix_v1.strategies.breakout import BreakoutStrategy
from helix_v1.strategies.momentum import MomentumStrategy
from helix_v1.strategies.news_reactive import NewsReactiveStrategy
from helix_v1.strategies.reversal import ReversalStrategy
from helix_v1.strategies.session import SessionStrategy
from helix_v1.strategies.structure_smc import StructureSMCStrategy
from helix_v1.strategies.trend import TrendStrategy

ALL_STRATEGIES = [
    TrendStrategy(),
    MomentumStrategy(),
    BreakoutStrategy(),
    ReversalStrategy(),
    StructureSMCStrategy(),
    SessionStrategy(),
    NewsReactiveStrategy(),
]


def run_all(snapshot, structure, regime) -> list[StrategySignal]:
    out: list[StrategySignal] = []
    for s in ALL_STRATEGIES:
        try:
            out.append(s.evaluate(snapshot, structure, regime))
        except Exception as exc:  # noqa: BLE001
            out.append(
                StrategySignal(
                    name=getattr(s, "name", type(s).__name__),
                    direction="flat",
                    score=0.0,
                    confidence=0.0,
                    reasons=[f"error:{type(exc).__name__}"],
                )
            )
    return out
