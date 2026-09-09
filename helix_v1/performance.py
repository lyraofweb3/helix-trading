"""Trade-list performance metrics for HELIX 1.0.

MFE/MAE fields are optional placeholders when not present on trades.
Pure functions — no network, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


@dataclass
class TradeRecord:
    """Minimal closed-trade shape used by metrics."""

    pnl: float
    side: str = "buy"
    symbol: str = ""
    entry: float | None = None
    exit_price: float | None = None
    mfe: float | None = None  # max favorable excursion (price or R)
    mae: float | None = None  # max adverse excursion
    bars_held: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "TradeRecord":
        return cls(
            pnl=float(m.get("pnl") or 0.0),
            side=str(m.get("side") or m.get("action") or "buy"),
            symbol=str(m.get("symbol") or ""),
            entry=_opt_float(m.get("entry")),
            exit_price=_opt_float(m.get("exit_price") or m.get("exit")),
            mfe=_opt_float(m.get("mfe")),
            mae=_opt_float(m.get("mae")),
            bars_held=int(m["bars_held"]) if m.get("bars_held") is not None else None,
            meta=dict(m.get("meta") or {}),
        )


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_trades(trades: Sequence[TradeRecord | Mapping[str, Any]]) -> list[TradeRecord]:
    out: list[TradeRecord] = []
    for t in trades:
        if isinstance(t, TradeRecord):
            out.append(t)
        else:
            out.append(TradeRecord.from_mapping(t))
    return out


@dataclass
class PerformanceMetrics:
    n_trades: int
    wins: int
    losses: int
    scratches: int
    win_rate: float
    gross_profit: float
    gross_loss: float  # positive magnitude of losses
    net_pnl: float
    profit_factor: float
    expectancy: float
    avg_win: float
    avg_loss: float  # negative or zero
    max_drawdown: float
    max_drawdown_pct: float
    avg_mfe: float | None
    avg_mae: float | None
    equity_curve: list[float]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_trades": self.n_trades,
            "wins": self.wins,
            "losses": self.losses,
            "scratches": self.scratches,
            "win_rate": self.win_rate,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "net_pnl": self.net_pnl,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "avg_mfe": self.avg_mfe,
            "avg_mae": self.avg_mae,
            "equity_curve": list(self.equity_curve),
            "notes": self.notes,
        }


def equity_curve_from_pnls(
    pnls: Iterable[float],
    starting_equity: float = 10_000.0,
) -> list[float]:
    eq = float(starting_equity)
    curve = [eq]
    for p in pnls:
        eq += float(p)
        curve.append(eq)
    return curve


def max_drawdown(equity_curve: Sequence[float]) -> tuple[float, float]:
    """Return (max_drawdown_abs, max_drawdown_pct) from peak.

    drawdown_abs is peak - trough (positive). pct is abs/peak * 100.
    """
    if not equity_curve:
        return 0.0, 0.0
    peak = float(equity_curve[0])
    max_dd = 0.0
    max_dd_pct = 0.0
    for eq in equity_curve:
        e = float(eq)
        if e > peak:
            peak = e
        dd = peak - e
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
    return max_dd, max_dd_pct


def compute_metrics(
    trades: Sequence[TradeRecord | Mapping[str, Any]],
    *,
    starting_equity: float = 10_000.0,
) -> PerformanceMetrics:
    """Compute win rate, profit factor, expectancy, drawdown, MFE/MAE avgs."""
    recs = _as_trades(trades)
    pnls = [r.pnl for r in recs]
    wins_l = [p for p in pnls if p > 0]
    losses_l = [p for p in pnls if p < 0]
    scratches = sum(1 for p in pnls if p == 0)
    n = len(recs)
    gross_profit = sum(wins_l)
    gross_loss = abs(sum(losses_l))
    net = sum(pnls)
    if gross_loss > 0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0:
        pf = float("inf")
    else:
        pf = 0.0
    expectancy = (net / n) if n else 0.0
    win_rate = (len(wins_l) / n) if n else 0.0
    avg_win = (sum(wins_l) / len(wins_l)) if wins_l else 0.0
    avg_loss = (sum(losses_l) / len(losses_l)) if losses_l else 0.0

    mfes = [r.mfe for r in recs if r.mfe is not None]
    maes = [r.mae for r in recs if r.mae is not None]
    avg_mfe = (sum(mfes) / len(mfes)) if mfes else None
    avg_mae = (sum(maes) / len(maes)) if maes else None

    curve = equity_curve_from_pnls(pnls, starting_equity=starting_equity)
    dd, dd_pct = max_drawdown(curve)
    notes = ""
    if avg_mfe is None and avg_mae is None:
        notes = "MFE/MAE not present on trades — placeholders omitted."

    return PerformanceMetrics(
        n_trades=n,
        wins=len(wins_l),
        losses=len(losses_l),
        scratches=scratches,
        win_rate=win_rate,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pnl=net,
        profit_factor=pf if pf != float("inf") else 999.0,
        expectancy=expectancy,
        avg_win=avg_win,
        avg_loss=avg_loss,
        max_drawdown=dd,
        max_drawdown_pct=dd_pct,
        avg_mfe=avg_mfe,
        avg_mae=avg_mae,
        equity_curve=curve,
        notes=notes,
    )
