"""HELIX trade style: swing (H1) vs scalp (M5/M15). Additive — swing remains default."""

from __future__ import annotations

import os
from enum import Enum


class TradeStyle(str, Enum):
    SWING = "swing"
    SCALP = "scalp"


def current_trade_style() -> TradeStyle:
    raw = (os.environ.get("HELIX_TRADE_STYLE") or "swing").strip().lower()
    if raw in {"scalp", "scalping", "m5", "m15"}:
        return TradeStyle.SCALP
    return TradeStyle.SWING


def is_scalp() -> bool:
    return current_trade_style() == TradeStyle.SCALP


def scalp_risk_percent(default_swing: float = 0.5) -> float:
    """Slightly tighter default risk for scalp; overridable via env."""
    env = os.environ.get("HELIX_SCALP_RISK_PERCENT", "").strip()
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    if is_scalp():
        return min(default_swing, 0.35)
    return default_swing


def scalp_min_rr() -> float:
    env = os.environ.get("HELIX_SCALP_MIN_RR", "").strip()
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return 1.2


def scalp_sl_atr_mult() -> float:
    env = os.environ.get("HELIX_SCALP_SL_ATR", "").strip()
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return 0.8
