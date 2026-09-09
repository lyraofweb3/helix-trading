"""Fixed-fractional position sizing — no martingale."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from helix.config import RISK_PERCENT
from helix.prices import point_size


@dataclass
class SizeResult:
    lots: float
    risk_amount: float
    risk_pct: float
    stop_points: float
    lot_step: float
    capped: bool
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "lots": self.lots,
            "risk_amount": round(self.risk_amount, 4),
            "risk_pct": self.risk_pct,
            "stop_points": self.stop_points,
            "lot_step": self.lot_step,
            "capped": self.capped,
            "rationale": self.rationale,
        }


def _lot_step_for(symbol: str) -> float:
    sym = symbol.upper()
    if sym in {"XAUUSD", "GOLD"}:
        return 0.01
    if sym in {"USOIL", "UKOIL", "WTI"}:
        return 0.01
    return 0.01


def _pip_value_per_lot(symbol: str, equity_ccy: str = "USD") -> float:
    """
    Approximate $ value of 1 point move per 1.0 lot.
    FX majors: 1 lot = 100_000 units; point as in helix.prices.point_size.
    """
    sym = symbol.upper()
    pt = point_size(sym)
    if sym in {"XAUUSD", "GOLD"}:
        # 1 lot ≈ 100 oz; $0.001 move ≈ $0.10
        return 100.0 * pt / 0.001 * 0.1 if False else 10.0  # ~$1 per 0.1 point? use 1.0$/0.01
    # Standard: value per point ≈ contract * point
    # For EURUSD 1.0 lot, 0.00001 move ≈ $1
    if "JPY" in sym:
        # rough: ~$0.90–1.0 per point (0.001) per lot — use 1.0
        return 1.0
    if sym in {"USOIL", "UKOIL"}:
        return 10.0  # $10 per 0.01 on 100 bbl rough
    # 100000 * point_size ≈ $1 for 5-digit
    return 100_000.0 * pt


def round_lots_down(lots: float, step: float) -> float:
    if step <= 0:
        return 0.0
    if lots <= 0:
        return 0.0
    n = math.floor(lots / step + 1e-12)
    return round(n * step, 8)


def size_position(
    *,
    equity: float,
    symbol: str,
    stop_distance_price: float | None = None,
    stop_points: float | None = None,
    atr_points: float | None = None,
    atr_mult: float = 1.5,
    risk_pct: float = RISK_PERCENT,
    max_lots: float = 5.0,
    min_lots: float = 0.01,
    vol_scalar: float | None = None,
) -> SizeResult:
    """
    Fixed fractional: risk_amount = equity * risk_pct/100.
    lots = risk_amount / (stop_points * $/point).
    Round DOWN to lot step. Never increases after losses (no martingale).
    """
    if equity <= 0:
        return SizeResult(0.0, 0.0, risk_pct, 0.0, _lot_step_for(symbol), True, "non-positive equity")

    risk_pct = max(0.0, min(risk_pct, RISK_PERCENT if risk_pct > RISK_PERCENT else risk_pct))
    # hard clamp to configured ceiling
    from helix.config import RISK_PERCENT as CAP

    if risk_pct > CAP:
        risk_pct = CAP

    pt = point_size(symbol)
    if stop_points is None:
        if stop_distance_price is not None and pt > 0:
            stop_points = abs(stop_distance_price) / pt
        elif atr_points is not None:
            stop_points = abs(atr_points) * atr_mult
        else:
            stop_points = 50.0  # fallback

    stop_points = float(stop_points)
    if stop_points <= 0:
        return SizeResult(0.0, 0.0, risk_pct, stop_points, _lot_step_for(symbol), True, "invalid stop")

    risk_amount = equity * (risk_pct / 100.0)
    pip_val = _pip_value_per_lot(symbol)
    denom = stop_points * pip_val
    raw_lots = risk_amount / denom if denom > 0 else 0.0

    if vol_scalar is not None and vol_scalar > 0:
        # Higher vol → smaller size
        raw_lots *= min(1.0, 1.0 / vol_scalar)

    step = _lot_step_for(symbol)
    lots = round_lots_down(raw_lots, step)
    capped = False
    if lots > max_lots:
        lots = round_lots_down(max_lots, step)
        capped = True
    if 0 < lots < min_lots:
        # Too small to trade
        return SizeResult(
            0.0,
            risk_amount,
            risk_pct,
            stop_points,
            step,
            True,
            f"sized {raw_lots:.4f} below min lot {min_lots}",
        )

    return SizeResult(
        lots=lots,
        risk_amount=risk_amount,
        risk_pct=risk_pct,
        stop_points=stop_points,
        lot_step=step,
        capped=capped,
        rationale=f"fixed fractional {risk_pct}% equity / {stop_points:.1f} pts → {lots} lots",
    )



def calculate_lots(*args, **kwargs):
    """Alias for size_position (pipeline compatibility)."""
    return size_position(*args, **kwargs)
