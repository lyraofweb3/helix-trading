"""HELIX market-structure helpers: swings, dealing range, OF, FVG, PDH/PDL."""

from __future__ import annotations

from typing import Any


def swing_points(
    highs: list[float],
    lows: list[float],
    n: int = 3,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """
    Simple fractal swings: high[i] is swing high if strictly greater than
    n bars on each side; same for lows. Returns (swing_highs, swing_lows)
    as (index, price) lists in chronological order.
    """
    sh: list[tuple[int, float]] = []
    sl: list[tuple[int, float]] = []
    length = min(len(highs), len(lows))
    if length < 2 * n + 1:
        return sh, sl
    for i in range(n, length - n):
        window_h = highs[i - n : i + n + 1]
        window_l = lows[i - n : i + n + 1]
        if highs[i] == max(window_h) and highs[i] > max(window_h[:n] + window_h[n + 1 :]):
            sh.append((i, float(highs[i])))
        elif highs[i] == max(window_h) and all(
            highs[i] > window_h[j] for j in range(len(window_h)) if j != n
        ):
            sh.append((i, float(highs[i])))
        if lows[i] == min(window_l) and all(
            lows[i] < window_l[j] for j in range(len(window_l)) if j != n
        ):
            sl.append((i, float(lows[i])))
    return sh, sl


def dealing_range(
    highs: list[float],
    lows: list[float],
    lookback: int = 48,
) -> dict[str, float | None]:
    """High / low / mid of the last `lookback` bars (H1 dealing range)."""
    if not highs or not lows:
        return {"high": None, "low": None, "mid": None}
    h = highs[-lookback:]
    l = lows[-lookback:]
    hi = float(max(h))
    lo = float(min(l))
    mid = (hi + lo) / 2.0
    return {"high": hi, "low": lo, "mid": mid}


def premium_discount(last: float | None, mid: float | None) -> str | None:
    if last is None or mid is None:
        return None
    if last > mid:
        return "premium"
    if last < mid:
        return "discount"
    return "equilibrium"


def prev_day_hl(
    daily_highs: list[float] | None,
    daily_lows: list[float] | None,
    daily_closes: list[float] | None = None,
) -> dict[str, Any]:
    """
    Previous completed day high/low from daily bars.
    Uses second-to-last bar when last bar may be the in-progress day.
    """
    out: dict[str, Any] = {
        "pdh": None,
        "pdl": None,
        "reaction_hint": None,
    }
    if not daily_highs or not daily_lows or len(daily_highs) < 2 or len(daily_lows) < 2:
        return out
    # Prior completed day = -2; current forming = -1
    pdh = float(daily_highs[-2])
    pdl = float(daily_lows[-2])
    out["pdh"] = pdh
    out["pdl"] = pdl
    if daily_closes and len(daily_closes) >= 2:
        last_c = float(daily_closes[-1])
        # Rough reaction vs prior day extremes using current daily close
        if last_c > pdh:
            out["reaction_hint"] = "close_above_pdh_higher"
        elif last_c < pdl:
            out["reaction_hint"] = "close_below_pdl_lower"
        elif last_c > (pdh + pdl) / 2:
            # inside, upper half — context-dependent; flag inside
            out["reaction_hint"] = "inside_prior_day_upper"
        else:
            out["reaction_hint"] = "inside_prior_day_lower"
    return out


def order_flow_heuristic(
    swing_highs: list[tuple[int, float]],
    swing_lows: list[tuple[int, float]],
) -> str:
    """
    Rough OF from last two swing highs and lows.
    Bullish: higher highs + higher lows; bearish: lower highs + lower lows;
    else mixed.
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "mixed"
    h1, h2 = swing_highs[-2][1], swing_highs[-1][1]
    l1, l2 = swing_lows[-2][1], swing_lows[-1][1]
    hh = h2 > h1
    hl = l2 > l1
    lh = h2 < h1
    ll = l2 < l1
    if hh and hl:
        return "bullish"
    if lh and ll:
        return "bearish"
    # Partial: break highs / reject lows style
    if hh and not ll:
        return "bullish"
    if ll and not hh:
        return "bearish"
    return "mixed"


def fvg_hint(
    highs: list[float],
    lows: list[float],
    lookback: int = 30,
) -> dict[str, Any]:
    """
    3-candle FVG detection on recent bars.
    Bullish FVG: lows[i] > highs[i-2] (gap up between candle i-2 and i).
    Bearish FVG: highs[i] < lows[i-2].
    Returns most recent gap hint if any.
    """
    h = highs[-lookback:] if len(highs) > lookback else highs
    l = lows[-lookback:] if len(lows) > lookback else lows
    n = min(len(h), len(l))
    last: dict[str, Any] | None = None
    for i in range(2, n):
        # bullish imbalance
        if l[i] > h[i - 2]:
            last = {
                "type": "bullish_fvg",
                "gap_low": float(h[i - 2]),
                "gap_high": float(l[i]),
                "bar_offset_from_end": i - (n - 1),
            }
        # bearish imbalance
        if h[i] < l[i - 2]:
            last = {
                "type": "bearish_fvg",
                "gap_low": float(h[i]),
                "gap_high": float(l[i - 2]),
                "bar_offset_from_end": i - (n - 1),
            }
    if last is None:
        return {"present": False}
    return {"present": True, **last}


def _r(v: float | None, symbol: str) -> float | None:
    if v is None:
        return None
    if "JPY" in symbol.upper():
        return round(v, 3)
    return round(v, 5)


def compute_structure(
    symbol: str,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    daily_highs: list[float] | None = None,
    daily_lows: list[float] | None = None,
    daily_closes: list[float] | None = None,
    swing_n: int = 3,
    range_lookback: int = 48,
) -> dict[str, Any]:
    """Build structure dict for market snapshot."""
    sh, sl = swing_points(highs, lows, n=swing_n)
    dr = dealing_range(highs, lows, lookback=range_lookback)
    last = float(closes[-1]) if closes else None
    zone = premium_discount(last, dr["mid"] if isinstance(dr["mid"], float) else None)
    of = order_flow_heuristic(sh, sl)
    pd = prev_day_hl(daily_highs, daily_lows, daily_closes)
    fvg = fvg_hint(highs, lows)

    summary = (
        f"OF={of}; zone={zone}; "
        f"PDH={_r(pd.get('pdh'), symbol)}; PDL={_r(pd.get('pdl'), symbol)}; "
        f"reaction={pd.get('reaction_hint')}; "
        f"FVG={fvg.get('type') if fvg.get('present') else 'none'}"
    )
    return {
        "swing_highs": [_r(p, symbol) for _, p in sh[-5:]],
        "swing_lows": [_r(p, symbol) for _, p in sl[-5:]],
        "dealing_range_high": _r(dr["high"] if isinstance(dr["high"], float) else None, symbol),
        "dealing_range_low": _r(dr["low"] if isinstance(dr["low"], float) else None, symbol),
        "dealing_range_mid": _r(dr["mid"] if isinstance(dr["mid"], float) else None, symbol),
        "premium_discount": zone,
        "pdh": _r(pd["pdh"], symbol) if pd.get("pdh") is not None else None,
        "pdl": _r(pd["pdl"], symbol) if pd.get("pdl") is not None else None,
        "pdh_pdl_reaction_hint": pd.get("reaction_hint"),
        "order_flow_heuristic": of,
        "fvg_hint": fvg,
        "swing_n": swing_n,
        "range_lookback": range_lookback,
        "summary": summary,
    }
