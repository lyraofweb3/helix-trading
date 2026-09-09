"""Scalp market snapshot — M5 execution + M15 bias. Additive to H1 swing path."""

from __future__ import annotations

import logging
from typing import Any

from helix.prices import MTF_SPECS, fetch_ohlc_interval
from helix.structure import compute_structure

logger = logging.getLogger(__name__)


def _ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - (100 / (1 + rs))


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def _pack(symbol: str, label: str, o: list[float], h: list[float], l: list[float], c: list[float]) -> dict[str, Any]:
    last = c[-1] if c else None
    e21, e50 = _ema(c, 21), _ema(c, 50)
    rsi = _rsi(c)
    atr = _atr(h, l, c)
    structure = {}
    try:
        structure = compute_structure(h, l, c) or {}
    except Exception:  # noqa: BLE001
        structure = {}
    return {
        "symbol": symbol,
        "timeframe": label,
        "last_close": last,
        "bid": last,
        "ask": last,
        "ema21": e21,
        "ema50": e50,
        "rsi": rsi,
        "atr": atr,
        "structure": structure,
        "bars": len(c),
        "price_provider": "yahoo",
    }


def build_scalp_snapshot(symbol: str) -> dict[str, Any]:
    """
    Primary TF = 5m, bias TF = 15m. Fail soft to empty fields if Yahoo thin on FX.
    """
    out: dict[str, Any] = {
        "symbol": symbol,
        "trade_style": "scalp",
        "timeframe": "5m",
        "bias_timeframe": "15m",
        "note": "scalp_snapshot",
    }
    try:
        interval, range_, min_bars = MTF_SPECS["5m"]
        o, h, l, c = fetch_ohlc_interval(symbol, interval, range_, min_bars=min_bars)
        m5 = _pack(symbol, "5m", o, h, l, c)
        out.update(m5)
        out["m5"] = m5
    except Exception as exc:  # noqa: BLE001
        logger.warning("scalp M5 failed for %s: %s", symbol, type(exc).__name__)
        out["note"] = f"scalp_m5_unavailable:{type(exc).__name__}"
        out["m5"] = {"available": False}

    try:
        interval, range_, min_bars = MTF_SPECS["15m"]
        o, h, l, c = fetch_ohlc_interval(symbol, interval, range_, min_bars=min_bars)
        m15 = _pack(symbol, "15m", o, h, l, c)
        out["m15"] = m15
        # HTF bias from M15 EMA stack
        e21, e50 = m15.get("ema21"), m15.get("ema50")
        last = m15.get("last_close")
        if e21 and e50 and last:
            if last > e21 > e50:
                out["scalp_bias"] = "bullish"
            elif last < e21 < e50:
                out["scalp_bias"] = "bearish"
            else:
                out["scalp_bias"] = "neutral"
        else:
            out["scalp_bias"] = "neutral"
    except Exception as exc:  # noqa: BLE001
        logger.warning("scalp M15 failed for %s: %s", symbol, type(exc).__name__)
        out["m15"] = {"available": False}
        out["scalp_bias"] = "neutral"

    return out
