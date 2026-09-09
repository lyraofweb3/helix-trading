"""Walk-forward train / validate / OOS runner wrapping helix_v1.backtest."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from helix_v1.backtest import (
    BacktestConfig,
    BacktestResult,
    load_ohlc,
    run_backtest,
)
from helix_v1.performance import compute_metrics


@dataclass
class WalkForwardSplit:
    name: str
    start: int
    end: int  # exclusive


@dataclass
class WalkForwardResult:
    symbol: str
    splits: dict[str, BacktestResult]
    combined_oos_metrics: dict[str, Any] | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "splits": {k: v.to_dict() for k, v in self.splits.items()},
            "combined_oos_metrics": self.combined_oos_metrics,
            "notes": self.notes,
        }


def make_splits(
    n_bars: int,
    *,
    train_frac: float = 0.5,
    validate_frac: float = 0.25,
    min_bars: int = 80,
) -> list[WalkForwardSplit]:
    """Single contiguous train / validate / oos split by bar index."""
    if n_bars < min_bars:
        raise ValueError(f"need >= {min_bars} bars, got {n_bars}")
    train_end = int(n_bars * train_frac)
    val_end = int(n_bars * (train_frac + validate_frac))
    train_end = max(train_end, min_bars // 2)
    val_end = max(val_end, train_end + min_bars // 4)
    val_end = min(val_end, n_bars - min_bars // 4)
    if val_end <= train_end:
        val_end = min(n_bars - 1, train_end + max(10, n_bars // 10))
    return [
        WalkForwardSplit("train", 0, train_end),
        WalkForwardSplit("validate", train_end, val_end),
        WalkForwardSplit("oos", val_end, n_bars),
    ]


def run_walk_forward(
    symbol: str = "EURUSD",
    *,
    timeframe: str = "h1",
    cfg: BacktestConfig | None = None,
    opens: Sequence[float] | None = None,
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
    closes: Sequence[float] | None = None,
    train_frac: float = 0.5,
    validate_frac: float = 0.25,
    store_db: bool = False,
) -> WalkForwardResult:
    """Run backtest on train / validate / oos slices of the same OHLC series."""
    o, h, l, c = load_ohlc(symbol, timeframe, opens, highs, lows, closes)
    n = len(c)
    splits = make_splits(n, train_frac=train_frac, validate_frac=validate_frac)
    base = cfg or BacktestConfig(symbol=symbol, timeframe=timeframe)
    results: dict[str, BacktestResult] = {}

    for sp in splits:
        if sp.end - sp.start < 40:
            continue
        slice_cfg = BacktestConfig(
            symbol=base.symbol,
            starting_equity=base.starting_equity,
            risk_pct=base.risk_pct,
            sl_atr_mult=base.sl_atr_mult,
            tp_rr=base.tp_rr,
            atr_period=base.atr_period,
            ema_fast=base.ema_fast,
            ema_slow=base.ema_slow,
            ema_trend=min(base.ema_trend, max(30, (sp.end - sp.start) // 2)),
            warmup=min(base.warmup, max(25, (sp.end - sp.start) // 3)),
            timeframe=base.timeframe,
            cost=base.cost,
            strategy=f"{base.strategy}:{sp.name}",
        )
        try:
            results[sp.name] = run_backtest(
                slice_cfg,
                opens=o[sp.start : sp.end],
                highs=h[sp.start : sp.end],
                lows=l[sp.start : sp.end],
                closes=c[sp.start : sp.end],
                store_db=store_db,
            )
        except ValueError as exc:
            # insufficient bars after warmup — skip
            results[sp.name] = BacktestResult(
                symbol=symbol,
                strategy=slice_cfg.strategy,
                metrics=compute_metrics([]),
                trades=[],
                bars_used=sp.end - sp.start,
                params={"error": str(exc), "start": sp.start, "end": sp.end},
            )

    oos = results.get("oos")
    combined = oos.metrics.to_dict() if oos else None
    return WalkForwardResult(
        symbol=symbol,
        splits=results,
        combined_oos_metrics=combined,
        notes=f"bars={n}; splits={[ (s.name, s.start, s.end) for s in splits ]}",
    )


def rolling_walk_forward(
    symbol: str,
    *,
    window: int = 300,
    step: int = 50,
    opens: Sequence[float] | None = None,
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
    closes: Sequence[float] | None = None,
    timeframe: str = "h1",
) -> list[dict[str, Any]]:
    """Optional multi-window OOS: train on [i,i+window), test on next step bars."""
    o, h, l, c = load_ohlc(symbol, timeframe, opens, highs, lows, closes)
    n = len(c)
    out: list[dict[str, Any]] = []
    i = 0
    while i + window + step <= n:
        train_end = i + window
        test_end = train_end + step
        cfg = BacktestConfig(
            symbol=symbol,
            ema_trend=min(200, window // 2),
            warmup=min(100, window // 3),
            strategy="ema_trend_pullback:roll",
        )
        try:
            bt = run_backtest(
                cfg,
                opens=o[i:test_end],
                highs=h[i:test_end],
                lows=l[i:test_end],
                closes=c[i:test_end],
                store_db=False,
            )
            out.append(
                {
                    "train_start": i,
                    "train_end": train_end,
                    "test_end": test_end,
                    "metrics": bt.metrics.to_dict(),
                    "n_trades": bt.metrics.n_trades,
                }
            )
        except ValueError:
            pass
        i += step
    return out
