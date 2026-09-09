"""Strategy protocol and shared signal type."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass
class StrategySignal:
    name: str
    direction: str  # buy | sell | flat
    score: float  # -1..+1
    confidence: float  # 0..1
    reasons: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def side(self) -> str:
        d = (self.direction or "flat").lower()
        if d in {"buy", "long"}:
            return "buy"
        if d in {"sell", "short"}:
            return "sell"
        return "flat"

    @property
    def strength(self) -> float:
        # fuse_signals uses strength 0..1 weighted by side
        return max(0.0, min(1.0, abs(float(self.score)) * float(self.confidence or 1.0)))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side
        d["strength"] = self.strength
        return d


class Strategy(Protocol):
    name: str

    def evaluate(
        self,
        snapshot: dict[str, Any],
        structure: dict[str, Any] | None,
        regime: Any,
    ) -> StrategySignal: ...
