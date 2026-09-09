"""Multi-timeframe analysis engine — higher TF context, lower TF execution."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TF_ORDER = ("1D", "4H", "1H", "30m", "15m", "5m", "1m")


@dataclass
class TFSnapshot:
    timeframe: str
    bias: str  # bullish | bearish | neutral
    strength: float  # 0..1
    rsi: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None
    last_close: float | None = None
    available: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MTFResult:
    htf_bias: str  # from 1D/4H/1H stack
    entry_bias: str  # from 15m/5m
    alignment: str  # aligned | mixed | conflicting
    alignment_score: float  # 0..1
    continuation_probability: float
    reversal_probability: float
    frames: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return float(ema)


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
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


def analyze_tf_bars(
    timeframe: str,
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
) -> TFSnapshot:
    if len(closes) < 20:
        return TFSnapshot(timeframe, "neutral", 0.2, available=False, note="insufficient_bars")
    ef = _ema(closes, 21)
    es = _ema(closes, 50)
    last = closes[-1]
    rsi = _rsi(closes, 14)
    bias = "neutral"
    strength = 0.35
    if ef is not None and es is not None:
        if ef > es and last >= es:
            bias = "bullish"
            strength = min(0.95, 0.45 + abs(ef - es) / max(abs(es), 1e-9) * 80)
        elif ef < es and last <= es:
            bias = "bearish"
            strength = min(0.95, 0.45 + abs(ef - es) / max(abs(es), 1e-9) * 80)
    return TFSnapshot(timeframe, bias, strength, rsi, ef, es, last, True)


def fuse_mtf(frames: dict[str, TFSnapshot]) -> MTFResult:
    notes: list[str] = []
    # HTF = 1D, 4H, 1H
    htf_keys = ["1D", "4H", "1H"]
    entry_keys = ["15m", "5m", "30m"]

    def _vote(keys: list[str]) -> tuple[str, float]:
        bull = bear = 0.0
        n = 0
        for k in keys:
            f = frames.get(k)
            if not f or not f.available:
                continue
            n += 1
            if f.bias == "bullish":
                bull += f.strength
            elif f.bias == "bearish":
                bear += f.strength
        if n == 0:
            return "neutral", 0.3
        if bull > bear * 1.15:
            return "bullish", min(0.99, bull / n)
        if bear > bull * 1.15:
            return "bearish", min(0.99, bear / n)
        return "neutral", 0.4

    htf_bias, htf_s = _vote(htf_keys)
    entry_bias, entry_s = _vote(entry_keys)

    if htf_bias == entry_bias and htf_bias != "neutral":
        alignment = "aligned"
        alignment_score = min(0.99, 0.55 + 0.25 * htf_s + 0.2 * entry_s)
        cont = alignment_score
        rev = max(0.05, 1 - alignment_score)
        notes.append("htf_ltf_aligned")
    elif htf_bias != "neutral" and entry_bias != "neutral" and htf_bias != entry_bias:
        alignment = "conflicting"
        alignment_score = 0.25
        cont = 0.25
        rev = 0.7
        notes.append("htf_ltf_conflict")
    else:
        alignment = "mixed"
        alignment_score = 0.45
        cont = 0.45
        rev = 0.45
        notes.append("mtf_mixed")

    return MTFResult(
        htf_bias=htf_bias,
        entry_bias=entry_bias,
        alignment=alignment,
        alignment_score=alignment_score,
        continuation_probability=cont,
        reversal_probability=rev,
        frames={k: v.to_dict() for k, v in frames.items()},
        notes=notes,
    )


def build_mtf(symbol: str, *, live: bool = True) -> MTFResult:
    """
    Build multi-timeframe picture.
    live=True hits Yahoo for available TFs; failures become unavailable frames (fail soft).
    """
    frames: dict[str, TFSnapshot] = {}
    if not live:
        return MTFResult("neutral", "neutral", "mixed", 0.4, 0.4, 0.4, {}, ["offline"])

    from helix.prices import (
        MTF_SPECS,
        fetch_ohlc_interval,
        fetch_ohlc_h1,
        fetch_ohlc_daily,
        resample_ohlc_to_4h,
    )

    # 1H
    try:
        o, h, l, c = fetch_ohlc_h1(symbol)
        frames["1H"] = analyze_tf_bars("1H", o, h, l, c)
        # 4H from H1
        o4, h4, l4, c4 = resample_ohlc_to_4h(o, h, l, c)
        frames["4H"] = analyze_tf_bars("4H", o4, h4, l4, c4)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MTF 1H/4H failed: %s", type(exc).__name__)
        frames["1H"] = TFSnapshot("1H", "neutral", 0.2, available=False, note=type(exc).__name__)
        frames["4H"] = TFSnapshot("4H", "neutral", 0.2, available=False, note=type(exc).__name__)

    # 1D
    try:
        o, h, l, c = fetch_ohlc_daily(symbol)
        frames["1D"] = analyze_tf_bars("1D", o, h, l, c)
    except Exception as exc:  # noqa: BLE001
        frames["1D"] = TFSnapshot("1D", "neutral", 0.2, available=False, note=type(exc).__name__)

    # Lower TFs — best effort
    for label in ("30m", "15m", "5m", "1m"):
        if label not in MTF_SPECS:
            continue
        interval, range_, min_bars = MTF_SPECS[label]
        try:
            o, h, l, c = fetch_ohlc_interval(symbol, interval, range_, min_bars=min_bars)
            frames[label] = analyze_tf_bars(label, o, h, l, c)
        except Exception as exc:  # noqa: BLE001
            frames[label] = TFSnapshot(label, "neutral", 0.2, available=False, note=type(exc).__name__)

    return fuse_mtf(frames)
