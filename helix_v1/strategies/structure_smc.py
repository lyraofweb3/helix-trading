"""Market structure / SMC-style confluence (OF, FVG, PDH/PDL, BOS/CHOCH)."""

from __future__ import annotations

from typing import Any

from helix_v1.strategies.base import StrategySignal


class StructureSMCStrategy:
    name = "structure_smc"

    def evaluate(self, snapshot: dict[str, Any], structure: dict[str, Any] | None, regime: Any) -> StrategySignal:
        structure = structure or snapshot.get("structure") or {}
        reasons: list[str] = []
        score = 0.0
        direction = "flat"
        conf = 0.3

        of = structure.get("order_flow") or structure.get("of") or structure.get("bias")
        fvg = structure.get("fvg") or structure.get("fair_value_gap")
        loc = structure.get("premium_discount") or structure.get("location")
        choch = structure.get("choch") or structure.get("change_of_character")
        bos = structure.get("bos") or structure.get("break_of_structure")

        bull = 0
        bear = 0
        if of in ("bullish", "buy", "up"):
            bull += 1
            reasons.append("of_bullish")
        elif of in ("bearish", "sell", "down"):
            bear += 1
            reasons.append("of_bearish")

        if fvg in ("bullish", "up", True) or (isinstance(fvg, dict) and fvg.get("side") == "bullish"):
            bull += 1
            reasons.append("bullish_fvg")
        elif fvg in ("bearish", "down") or (isinstance(fvg, dict) and fvg.get("side") == "bearish"):
            bear += 1
            reasons.append("bearish_fvg")

        if loc in ("discount", "below_eq"):
            bull += 1
            reasons.append("discount_zone")
        elif loc in ("premium", "above_eq"):
            bear += 1
            reasons.append("premium_zone")

        if choch in ("bullish", "buy"):
            bull += 2
            reasons.append("choch_bull")
        elif choch in ("bearish", "sell"):
            bear += 2
            reasons.append("choch_bear")

        if bos in ("bullish", "buy", True) and of != "bearish":
            bull += 1
            reasons.append("bos_bull")
        elif bos in ("bearish", "sell"):
            bear += 1
            reasons.append("bos_bear")

        if bull - bear >= 2:
            direction, score, conf = "buy", 0.35 + 0.1 * (bull - bear), min(0.85, 0.4 + 0.1 * bull)
        elif bear - bull >= 2:
            direction, score, conf = "sell", -(0.35 + 0.1 * (bear - bull)), min(0.85, 0.4 + 0.1 * bear)
        else:
            reasons.append("structure_mixed")

        return StrategySignal(self.name, direction, float(score), float(conf), reasons, ["smc", "structure"])
