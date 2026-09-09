"""Trade Ideas Holly AI strategy vote — fused with HELIX quant, never solo."""

from __future__ import annotations

from typing import Any

from helix_v1.strategies.base import StrategySignal


class HollyAIStrategy:
    name = "holly_ai"

    def evaluate(self, snapshot: dict[str, Any], structure: dict[str, Any] | None, regime: Any) -> StrategySignal:
        holly = snapshot.get("holly") or {}
        if not holly.get("available"):
            return StrategySignal(
                self.name,
                "flat",
                0.0,
                0.1,
                ["holly_no_idea"],
                ["holly", "external"],
            )
        side = str(holly.get("side") or "flat")
        conf = float(holly.get("confidence") or 0.0)
        thesis = str(holly.get("thesis") or "holly")
        if side == "buy" and conf >= 0.35:
            return StrategySignal(
                self.name,
                "buy",
                0.35 + 0.5 * conf,
                min(0.9, 0.4 + conf * 0.5),
                [f"holly:{thesis[:80]}"],
                ["holly", "external", "momentum"],
            )
        if side == "sell" and conf >= 0.35:
            return StrategySignal(
                self.name,
                "sell",
                -(0.35 + 0.5 * conf),
                min(0.9, 0.4 + conf * 0.5),
                [f"holly:{thesis[:80]}"],
                ["holly", "external", "momentum"],
            )
        return StrategySignal(self.name, "flat", 0.0, 0.2, ["holly_flat"], ["holly", "external"])
