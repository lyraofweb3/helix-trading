"""Scalp trade style — additive to swing."""

import os

from helix_v1.trade_style import TradeStyle, current_trade_style, is_scalp, scalp_min_rr
from helix_v1.strategies.scalp import ScalpStrategy


def test_default_swing(monkeypatch):
    monkeypatch.delenv("HELIX_TRADE_STYLE", raising=False)
    assert current_trade_style() is TradeStyle.SWING
    assert is_scalp() is False


def test_scalp_env(monkeypatch):
    monkeypatch.setenv("HELIX_TRADE_STYLE", "scalp")
    assert current_trade_style() is TradeStyle.SCALP
    assert is_scalp() is True
    assert scalp_min_rr() == 1.2


def test_scalp_strategy_inactive_in_swing():
    sig = ScalpStrategy().evaluate({"trade_style": "swing", "rsi": 55, "last_close": 1.1}, {}, None)
    assert sig.direction == "flat"
    assert "inactive_swing_mode" in sig.reasons


def test_scalp_strategy_long_trigger():
    snap = {
        "trade_style": "scalp",
        "rsi": 55,
        "ema21": 1.1000,
        "ema50": 1.0990,
        "last_close": 1.1005,
        "scalp_bias": "bullish",
        "atr": 0.0003,
    }
    sig = ScalpStrategy().evaluate(snap, {}, None)
    assert sig.direction == "buy"
    assert sig.score > 0
