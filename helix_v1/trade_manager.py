"""Manage open thesis: hold / reduce / trail / exit recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from helix_v1.regime import RegimeResult
from helix_v1.signal_fusion import FusionResult, FusionState


@dataclass
class ManageRecommendation:
    action: str  # hold | reduce | trail | exit
    reason: str
    trail_points: float | None = None
    reduce_fraction: float | None = None
    urgency: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "trail_points": self.trail_points,
            "reduce_fraction": self.reduce_fraction,
            "urgency": self.urgency,
            "meta": dict(self.meta),
        }


def manage_open_thesis(
    open_position: dict[str, Any] | None,
    fusion: FusionResult,
    regime: RegimeResult,
    snapshot: dict[str, Any] | None = None,
) -> ManageRecommendation | None:
    """Return management advice when an open position exists; else None."""
    if not open_position:
        return None

    side = str(open_position.get("side") or open_position.get("action") or "").lower()
    if side in {"long"}:
        side = "buy"
    if side in {"short"}:
        side = "sell"

    snap = snapshot or {}
    atr = snap.get("atr_points")
    try:
        atr_f = float(atr) if atr is not None else None
    except (TypeError, ValueError):
        atr_f = None

    if fusion.state is FusionState.EXIT or fusion.action == "close":
        return ManageRecommendation(
            action="exit",
            reason=fusion.rationale or "fusion EXIT",
            urgency=0.9,
        )

    # Regime flip against position
    if side == "buy" and regime.direction == "bearish" and regime.regime in {
        "strong_trend",
        "breakout",
        "high_vol",
    }:
        return ManageRecommendation(
            action="exit",
            reason=f"regime flipped bearish ({regime.regime})",
            urgency=0.85,
        )
    if side == "sell" and regime.direction == "bullish" and regime.regime in {
        "strong_trend",
        "breakout",
        "high_vol",
    }:
        return ManageRecommendation(
            action="exit",
            reason=f"regime flipped bullish ({regime.regime})",
            urgency=0.85,
        )

    # Reduce in high vol
    if regime.regime == "high_vol":
        return ManageRecommendation(
            action="reduce",
            reason="high_vol — cut heat",
            reduce_fraction=0.5,
            urgency=0.6,
        )

    # Trail in strong trend with position
    if regime.regime == "strong_trend" and (
        (side == "buy" and regime.direction == "bullish")
        or (side == "sell" and regime.direction == "bearish")
    ):
        trail = (atr_f * 1.0) if atr_f else 30.0
        return ManageRecommendation(
            action="trail",
            reason="strong_trend — trail stop",
            trail_points=trail,
            urgency=0.4,
        )

    if fusion.state is FusionState.POSITION_MGMT:
        return ManageRecommendation(
            action="hold",
            reason="position management — maintain thesis",
            urgency=0.2,
        )

    # Soft adverse vote
    if side == "buy" and fusion.sell_score > fusion.buy_score + 0.2:
        return ManageRecommendation(
            action="reduce",
            reason="votes leaning against long",
            reduce_fraction=0.33,
            urgency=0.5,
        )
    if side == "sell" and fusion.buy_score > fusion.sell_score + 0.2:
        return ManageRecommendation(
            action="reduce",
            reason="votes leaning against short",
            reduce_fraction=0.33,
            urgency=0.5,
        )

    return ManageRecommendation(action="hold", reason="thesis intact", urgency=0.1)
