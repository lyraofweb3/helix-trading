"""Free live forex OHLC via Yahoo Finance chart API. Fail soft — no paid keys."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from helix.structure import compute_structure

logger = logging.getLogger(__name__)

# HELIX majors → Yahoo Finance FX tickers (verified 2026-09).
# USDJPY=X and JPY=X both resolve; prefer explicit pair forms where available.
YAHOO_SYMBOL_MAP: dict[str, str] = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
}

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
# ~60 calendar days of H1 ≈ enough history for EMA200 after weekends/gaps
YAHOO_INTERVAL = "60m"
YAHOO_RANGE = "60d"
YAHOO_DAILY_INTERVAL = "1d"
YAHOO_DAILY_RANGE = "6mo"
YAHOO_TIMEOUT_SEC = 20.0

# Rough mid→bid/ask stub when Yahoo has no quote book (points = MT5 Point units).
_STUB_SPREAD_POINTS_DEFAULT = 12  # ~1.2 pip on 5-digit majors
_STUB_SPREAD_POINTS_JPY = 15


def yahoo_ticker(symbol: str) -> str:
    """Map HELIX symbol (EURUSD) to Yahoo ticker (EURUSD=X)."""
    sym = symbol.strip().upper().replace("/", "").replace("=", "")
    if sym.endswith("X") and len(sym) > 6:
        # already a yahoo-ish form without =
        pass
    if sym in YAHOO_SYMBOL_MAP:
        return YAHOO_SYMBOL_MAP[sym]
    # Heuristic: XXXYYY → XXXYYY=X (works for most Yahoo FX pairs)
    if len(sym) == 6 and sym.isalpha():
        return f"{sym}=X"
    raise ValueError(f"unsupported forex symbol: {symbol}")


def point_size(symbol: str) -> float:
    """MT5-style Point: 0.001 for JPY quotes, 0.00001 for 5-digit majors."""
    sym = symbol.strip().upper().replace("/", "").replace("=X", "").replace("=", "")
    if "JPY" in sym:
        return 0.001
    return 0.00001


def stub_spread_points(symbol: str) -> int:
    sym = symbol.strip().upper()
    if "JPY" in sym:
        return _STUB_SPREAD_POINTS_JPY
    return _STUB_SPREAD_POINTS_DEFAULT


def _ema(values: list[float], period: int) -> float | None:
    if period < 1 or len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1.0 - k)
    return ema


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None
    trs: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def _null_price_fields(note: str) -> dict[str, Any]:
    return {
        "bid": None,
        "ask": None,
        "spread_points": None,
        "atr_points": None,
        "ema_fast": None,
        "ema_slow": None,
        "ema_trend": None,
        "rsi": None,
        "last_close": None,
        "note": note,
        "price_provider": None,
        "structure": None,
    }


def _round_px(x: float, symbol: str) -> float:
    """Reasonable display precision by pair family."""
    if "JPY" in symbol.upper():
        return round(x, 3)
    return round(x, 5)


def _fetch_yahoo_ohlc(
    symbol: str,
    interval: str,
    range_: str,
    min_bars: int,
) -> tuple[list[float], list[float], list[float], list[float]]:
    """
    Download OHLC from Yahoo chart API for the given interval/range.
    Returns (opens, highs, lows, closes) with null bars dropped.
    Raises on HTTP/parse failure.
    """
    ticker = yahoo_ticker(symbol)
    url = YAHOO_CHART_URL.format(ticker=ticker)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HELIX-Brain/0.1; forex research)",
    }
    params = {"interval": interval, "range": range_}
    with httpx.Client(
        timeout=YAHOO_TIMEOUT_SEC,
        follow_redirects=True,
        headers=headers,
    ) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

    chart = payload.get("chart") or {}
    results = chart.get("result")
    if not results:
        err = (chart.get("error") or {}).get("description") or "empty chart result"
        raise RuntimeError(f"yahoo chart error: {err}")

    result = results[0]
    quote_list = (result.get("indicators") or {}).get("quote") or []
    if not quote_list:
        raise RuntimeError("yahoo chart missing quote series")
    q = quote_list[0]
    opens_raw = q.get("open") or []
    highs_raw = q.get("high") or []
    lows_raw = q.get("low") or []
    closes_raw = q.get("close") or []
    n = min(len(opens_raw), len(highs_raw), len(lows_raw), len(closes_raw))
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for i in range(n):
        o, h, l, c = opens_raw[i], highs_raw[i], lows_raw[i], closes_raw[i]
        if o is None or h is None or l is None or c is None:
            continue
        opens.append(float(o))
        highs.append(float(h))
        lows.append(float(l))
        closes.append(float(c))
    if len(closes) < min_bars:
        raise RuntimeError(f"insufficient bars from Yahoo ({len(closes)} < {min_bars})")
    return opens, highs, lows, closes


def fetch_ohlc_h1(symbol: str) -> tuple[list[float], list[float], list[float], list[float]]:
    """Download H1 (60m) OHLC from Yahoo chart API."""
    return _fetch_yahoo_ohlc(symbol, YAHOO_INTERVAL, YAHOO_RANGE, min_bars=50)


def fetch_ohlc_daily(symbol: str) -> tuple[list[float], list[float], list[float], list[float]]:
    """Download daily (1d, 6mo) OHLC for PDH/PDL and D1 context."""
    return _fetch_yahoo_ohlc(symbol, YAHOO_DAILY_INTERVAL, YAHOO_DAILY_RANGE, min_bars=5)


def fetch_snapshot(symbol: str) -> dict[str, Any]:
    """
    Fetch recent H1 OHLC, compute EMA21/50/200, RSI14, ATR14, last close,
    a rough bid/ask/spread stub, and structure (swings, range, PDH/PDL, OF, FVG).

    Returns dict matching brain snapshot price fields. On any failure returns
    null price fields + note (fail soft — caller should prefer hold).
    """
    sym = symbol.strip().upper()
    try:
        _opens, highs, lows, closes = fetch_ohlc_h1(sym)
    except Exception as exc:  # noqa: BLE001 — fail soft
        logger.warning("Price feed failed for %s: %s", sym, type(exc).__name__)
        return _null_price_fields(
            f"Live prices unavailable ({type(exc).__name__}) — treat as incomplete; prefer hold."
        )

    daily_highs: list[float] | None = None
    daily_lows: list[float] | None = None
    daily_closes: list[float] | None = None
    daily_note = ""
    try:
        _do, daily_highs, daily_lows, daily_closes = fetch_ohlc_daily(sym)
    except Exception as exc:  # noqa: BLE001 — PDH/PDL optional
        logger.warning("Daily feed failed for %s: %s", sym, type(exc).__name__)
        daily_note = f" Daily OHLC unavailable ({type(exc).__name__}); PDH/PDL omitted."

    last = closes[-1]
    ema21 = _ema(closes, 21)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(highs, lows, closes, 14)

    pt = point_size(sym)
    spread_pts = stub_spread_points(sym)
    half = (spread_pts * pt) / 2.0
    bid = last - half
    ask = last + half
    atr_pts = (atr14 / pt) if atr14 is not None and pt > 0 else None

    structure = compute_structure(
        sym,
        highs,
        lows,
        closes,
        daily_highs=daily_highs,
        daily_lows=daily_lows,
        daily_closes=daily_closes,
    )

    note = (
        f"Yahoo Finance H1 ({yahoo_ticker(sym)}); "
        f"bid/ask stubbed ±{spread_pts // 2} points around last close (no live book)."
        f"{daily_note}"
    )

    def _r(v: float | None) -> float | None:
        if v is None:
            return None
        return _round_px(v, sym)

    return {
        "bid": _r(bid),
        "ask": _r(ask),
        "spread_points": float(spread_pts),
        "atr_points": round(atr_pts, 1) if atr_pts is not None else None,
        "ema_fast": _r(ema21),
        "ema_slow": _r(ema50),
        "ema_trend": _r(ema200),
        "rsi": round(rsi14, 2) if rsi14 is not None else None,
        "last_close": _r(last),
        "note": note,
        "price_provider": "yahoo",
        "structure": structure,
    }
