"""Market regime detection from OHLC / indicator snapshot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RegimeResult:
    regime: str
    strength: float  # 0..1
    trend_bias: str  # bullish | bearish | neutral
    volatility: str  # high | normal | low
    notes: list[str] = field(default_factory=list)

    @property
    def direction(self) -> str:
        """Alias for trend_bias (signal_fusion / trade_manager)."""
        return self.trend_bias

    @property
    def confidence(self) -> float:
        return self.strength

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["direction"] = self.trend_bias
        return d


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def detect_regime(snapshot: dict[str, Any]) -> RegimeResult:
    """Classify regime using EMA stack, ATR, RSI, and optional structure."""
    notes: list[str] = []
    ema_fast = _f(snapshot.get("ema_fast"))
    ema_slow = _f(snapshot.get("ema_slow"))
    ema_trend = _f(snapshot.get("ema_trend"))
    rsi = _f(snapshot.get("rsi"))
    atr = _f(snapshot.get("atr_points"))
    last = _f(snapshot.get("last_close") or snapshot.get("bid"))
    structure = snapshot.get("structure") or {}

    # Trend bias
    bias = "neutral"
    if ema_fast is not None and ema_slow is not None and last is not None:
        if ema_fast > ema_slow and (ema_trend is None or last >= ema_trend * 0.999):
            bias = "bullish"
        elif ema_fast < ema_slow and (ema_trend is None or last <= ema_trend * 1.001):
            bias = "bearish"

    # Volatility via ATR relative to price
    vol = "normal"
    atr_pct = None
    if atr is not None and last and last > 0:
        atr_pct = atr / last if atr < last else atr / (last * 10000)  # handle points-style ATR
        # Heuristic: forex points often large; also try raw atr/last
        if atr > last:  # likely points
            atr_pct = atr / (last * 10000)
        if atr_pct >= 0.0025:
            vol = "high"
        elif atr_pct <= 0.0006:
            vol = "low"

    # Regime selection
    regime = "uncertain"
    strength = 0.35

    spread = _f(snapshot.get("spread_points"))
    if snapshot.get("note") and "incomplete" in str(snapshot.get("note")).lower():
        notes.append("incomplete_price_data")
        return RegimeResult("uncertain", 0.2, bias, vol, notes)

    if ema_fast is not None and ema_slow is not None:
        sep = abs(ema_fast - ema_slow) / max(abs(ema_slow), 1e-9)
        if sep > 0.0015 and bias != "neutral":
            if vol == "high":
                regime, strength = "strong_trend", min(0.95, 0.6 + sep * 40)
            else:
                regime, strength = "weak_trend", min(0.8, 0.45 + sep * 30)
            notes.append(f"ema_sep={sep:.5f}")
        elif sep < 0.0004:
            regime, strength = "range", 0.55
            notes.append("tight_ema")

    if vol == "high" and regime in ("range", "uncertain"):
        regime, strength = "high_vol", 0.6
    if vol == "low" and regime == "range":
        regime, strength = "low_vol", 0.55

    # Structure breakout hint
    of = (structure or {}).get("order_flow") or structure.get("of")
    bos = False
    if isinstance(structure, dict):
        bos = bool(structure.get("bos") or structure.get("break_of_structure"))
        if structure.get("fvg"):
            notes.append("fvg_present")
    if bos or of in ("bullish_break", "bearish_break"):
        regime, strength = "breakout", max(strength, 0.7)
        notes.append("structure_break")

    if rsi is not None:
        if rsi >= 70:
            notes.append("rsi_overbought")
        elif rsi <= 30:
            notes.append("rsi_oversold")

    if spread is not None and atr is not None and atr > 0 and spread > atr * 0.35:
        notes.append("wide_spread")
        strength *= 0.7
        if regime != "high_vol":
            regime = "uncertain"

    return RegimeResult(regime, float(max(0.05, min(0.99, strength))), bias, vol, notes)
