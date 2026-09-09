"""Bar-by-bar backtester using Yahoo OHLC (helix.prices) + spread/slippage model.

Outputs equity curve, drawdown, win rate, profit factor, expectancy.
Optionally stores the run in SQLite via helix_v1.db when available.
No live LLM calls.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from helix.prices import (
    fetch_ohlc_daily,
    fetch_ohlc_h1,
    normalize_symbol,
    point_size,
    stub_spread_points,
)
from helix_v1.performance import PerformanceMetrics, TradeRecord, compute_metrics

logger = logging.getLogger(__name__)


@dataclass
class CostModel:
    """Spread + slippage in price units (derived from points)."""

    spread_points: float
    slippage_points: float = 2.0
    point: float = 0.00001

    @property
    def half_spread(self) -> float:
        return (self.spread_points * self.point) / 2.0

    @property
    def slip(self) -> float:
        return self.slippage_points * self.point

    def buy_entry(self, mid: float) -> float:
        return mid + self.half_spread + self.slip

    def sell_entry(self, mid: float) -> float:
        return mid - self.half_spread - self.slip

    def buy_exit(self, mid: float) -> float:
        # closing long → sell at bid
        return mid - self.half_spread - self.slip

    def sell_exit(self, mid: float) -> float:
        # closing short → buy at ask
        return mid + self.half_spread + self.slip


def default_cost_model(symbol: str) -> CostModel:
    sym = normalize_symbol(symbol)
    return CostModel(
        spread_points=float(stub_spread_points(sym)),
        slippage_points=2.0,
        point=point_size(sym),
    )


@dataclass
class BacktestConfig:
    symbol: str = "EURUSD"
    starting_equity: float = 10_000.0
    risk_pct: float = 0.5
    sl_atr_mult: float = 1.5
    tp_rr: float = 1.5
    atr_period: int = 14
    ema_fast: int = 21
    ema_slow: int = 50
    ema_trend: int = 200
    warmup: int = 210
    max_trades: int | None = None
    timeframe: str = "h1"  # h1 | daily
    cost: CostModel | None = None
    strategy: str = "ema_trend_pullback"


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    metrics: PerformanceMetrics
    trades: list[TradeRecord]
    bars_used: int
    params: dict[str, Any] = field(default_factory=dict)
    db_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "metrics": self.metrics.to_dict(),
            "trades": [
                {
                    "pnl": t.pnl,
                    "side": t.side,
                    "entry": t.entry,
                    "exit_price": t.exit_price,
                    "mfe": t.mfe,
                    "mae": t.mae,
                    "bars_held": t.bars_held,
                    "meta": t.meta,
                }
                for t in self.trades
            ],
            "bars_used": self.bars_used,
            "params": self.params,
            "db_id": self.db_id,
        }


def _ema_series(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period < 1 or len(values) < period:
        return out
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    out[period - 1] = ema
    for i in range(period, len(values)):
        ema = values[i] * k + ema * (1.0 - k)
        out[i] = ema
    return out


def _atr_at(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
    period: int,
) -> float | None:
    if i < period:
        return None
    trs: list[float] = []
    for j in range(i - period + 1, i + 1):
        if j == 0:
            trs.append(highs[j] - lows[j])
        else:
            trs.append(
                max(
                    highs[j] - lows[j],
                    abs(highs[j] - closes[j - 1]),
                    abs(lows[j] - closes[j - 1]),
                )
            )
    if len(trs) < period:
        return None
    return sum(trs) / len(trs)


def load_ohlc(
    symbol: str,
    timeframe: str = "h1",
    opens: Sequence[float] | None = None,
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
    closes: Sequence[float] | None = None,
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Load OHLC from args or Yahoo via helix.prices."""
    if opens is not None and highs is not None and lows is not None and closes is not None:
        return list(opens), list(highs), list(lows), list(closes)
    if timeframe == "daily":
        o, h, l, c = fetch_ohlc_daily(symbol)
    else:
        o, h, l, c = fetch_ohlc_h1(symbol)
    return list(o), list(h), list(l), list(c)


SignalFn = Callable[[int, dict[str, Any]], str | None]
# returns "buy" | "sell" | None


def _default_signal(i: int, ctx: dict[str, Any]) -> str | None:
    """EMA trend pullback: long when close>ema_trend and ema_fast crosses above ema_slow."""
    ef = ctx["ema_fast"]
    es = ctx["ema_slow"]
    et = ctx["ema_trend"]
    closes = ctx["closes"]
    if ef[i] is None or es[i] is None or et[i] is None:
        return None
    if i < 1 or ef[i - 1] is None or es[i - 1] is None:
        return None
    close = closes[i]
    # long
    if close > et[i] and ef[i - 1] <= es[i - 1] and ef[i] > es[i]:
        return "buy"
    # short
    if close < et[i] and ef[i - 1] >= es[i - 1] and ef[i] < es[i]:
        return "sell"
    return None


def run_backtest(
    cfg: BacktestConfig | None = None,
    *,
    opens: Sequence[float] | None = None,
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
    closes: Sequence[float] | None = None,
    signal_fn: SignalFn | None = None,
    store_db: bool = True,
) -> BacktestResult:
    """Bar-by-bar backtest with ATR stops, RR targets, and cost model."""
    cfg = cfg or BacktestConfig()
    sym = normalize_symbol(cfg.symbol)
    cost = cfg.cost or default_cost_model(sym)
    o, h, l, c = load_ohlc(sym, cfg.timeframe, opens, highs, lows, closes)
    n = len(c)
    if n < cfg.warmup + 5:
        raise ValueError(f"insufficient bars: {n} < warmup {cfg.warmup}+5")

    ema_f = _ema_series(c, cfg.ema_fast)
    ema_s = _ema_series(c, cfg.ema_slow)
    ema_t = _ema_series(c, cfg.ema_trend)
    sig = signal_fn or _default_signal

    equity = float(cfg.starting_equity)
    trades: list[TradeRecord] = []
    position: dict[str, Any] | None = None

    start_i = max(cfg.warmup, cfg.ema_trend)
    for i in range(start_i, n):
        atr = _atr_at(h, l, c, i, cfg.atr_period)
        mid = c[i]
        # manage open position on this bar (intra-bar high/low)
        if position is not None:
            side = position["side"]
            entry = position["entry"]
            stop = position["stop"]
            take = position["take"]
            mfe = position.get("mfe", 0.0)
            mae = position.get("mae", 0.0)
            if side == "buy":
                mfe = max(mfe, h[i] - entry)
                mae = min(mae, l[i] - entry)
                hit_sl = l[i] <= stop
                hit_tp = h[i] >= take
                exit_mid = stop if hit_sl and (not hit_tp or stop <= take) else (take if hit_tp else None)
                # if both hit same bar, assume adverse first (conservative)
                if hit_sl and hit_tp:
                    exit_mid = stop
                if exit_mid is not None:
                    exit_px = cost.buy_exit(exit_mid) if False else (
                        # for long exit use bid side of exit_mid
                        exit_mid - cost.half_spread - cost.slip
                    )
                    # risk units: pnl in price * notional factor via risk_$ / stop_distance
                    risk_cash = position["risk_cash"]
                    stop_dist = abs(entry - position["raw_stop"])
                    if stop_dist <= 0:
                        stop_dist = cost.point
                    r_mult = (exit_px - entry) / stop_dist
                    pnl = r_mult * risk_cash
                    equity += pnl
                    trades.append(
                        TradeRecord(
                            pnl=pnl,
                            side=side,
                            symbol=sym,
                            entry=entry,
                            exit_price=exit_px,
                            mfe=mfe,
                            mae=mae,
                            bars_held=i - position["entry_i"],
                            meta={"exit": "sl" if hit_sl and (not hit_tp or hit_sl) else "tp"},
                        )
                    )
                    position = None
                    if cfg.max_trades and len(trades) >= cfg.max_trades:
                        break
            else:  # sell
                mfe = max(mfe, entry - l[i])
                mae = min(mae, entry - h[i])  # adverse is price rising
                hit_sl = h[i] >= stop
                hit_tp = l[i] <= take
                if hit_sl and hit_tp:
                    exit_mid = stop
                elif hit_sl:
                    exit_mid = stop
                elif hit_tp:
                    exit_mid = take
                else:
                    exit_mid = None
                if exit_mid is not None:
                    exit_px = exit_mid + cost.half_spread + cost.slip
                    risk_cash = position["risk_cash"]
                    stop_dist = abs(position["raw_stop"] - entry)
                    if stop_dist <= 0:
                        stop_dist = cost.point
                    r_mult = (entry - exit_px) / stop_dist
                    pnl = r_mult * risk_cash
                    equity += pnl
                    trades.append(
                        TradeRecord(
                            pnl=pnl,
                            side=side,
                            symbol=sym,
                            entry=entry,
                            exit_price=exit_px,
                            mfe=mfe,
                            mae=-abs(mae) if mae > 0 else mae,
                            bars_held=i - position["entry_i"],
                            meta={"exit": "sl" if hit_sl else "tp"},
                        )
                    )
                    position = None
                    if cfg.max_trades and len(trades) >= cfg.max_trades:
                        break
                else:
                    position["mfe"] = mfe
                    position["mae"] = mae
            if position is not None and position["side"] == "buy":
                position["mfe"] = mfe
                position["mae"] = mae

        if position is not None:
            continue
        if atr is None or atr <= 0:
            continue

        ctx = {
            "ema_fast": ema_f,
            "ema_slow": ema_s,
            "ema_trend": ema_t,
            "closes": c,
            "highs": h,
            "lows": l,
            "atr": atr,
            "i": i,
        }
        action = sig(i, ctx)
        if action not in {"buy", "sell"}:
            continue

        risk_cash = equity * (cfg.risk_pct / 100.0)
        sl_dist = atr * cfg.sl_atr_mult
        if action == "buy":
            entry = cost.buy_entry(mid)
            raw_stop = entry - sl_dist
            stop = raw_stop
            take = entry + sl_dist * cfg.tp_rr
        else:
            entry = cost.sell_entry(mid)
            raw_stop = entry + sl_dist
            stop = raw_stop
            take = entry - sl_dist * cfg.tp_rr

        position = {
            "side": action,
            "entry": entry,
            "stop": stop,
            "take": take,
            "raw_stop": raw_stop,
            "risk_cash": risk_cash,
            "entry_i": i,
            "mfe": 0.0,
            "mae": 0.0,
        }

    # force flat at end at last mid
    if position is not None:
        i = n - 1
        mid = c[i]
        side = position["side"]
        entry = position["entry"]
        if side == "buy":
            exit_px = mid - cost.half_spread - cost.slip
            stop_dist = abs(entry - position["raw_stop"]) or cost.point
            r_mult = (exit_px - entry) / stop_dist
        else:
            exit_px = mid + cost.half_spread + cost.slip
            stop_dist = abs(position["raw_stop"] - entry) or cost.point
            r_mult = (entry - exit_px) / stop_dist
        pnl = r_mult * position["risk_cash"]
        trades.append(
            TradeRecord(
                pnl=pnl,
                side=side,
                symbol=sym,
                entry=entry,
                exit_price=exit_px,
                mfe=position.get("mfe"),
                mae=position.get("mae"),
                bars_held=i - position["entry_i"],
                meta={"exit": "eod"},
            )
        )

    metrics = compute_metrics(trades, starting_equity=cfg.starting_equity)
    params = {
        "risk_pct": cfg.risk_pct,
        "sl_atr_mult": cfg.sl_atr_mult,
        "tp_rr": cfg.tp_rr,
        "timeframe": cfg.timeframe,
        "spread_points": cost.spread_points,
        "slippage_points": cost.slippage_points,
        "starting_equity": cfg.starting_equity,
    }
    result = BacktestResult(
        symbol=sym,
        strategy=cfg.strategy,
        metrics=metrics,
        trades=trades,
        bars_used=n,
        params=params,
    )
    if store_db:
        result.db_id = _store_backtest(result)
    return result


def _store_backtest(result: BacktestResult) -> int | None:
    try:
        from helix_v1.db import HelixDB
    except Exception:  # noqa: BLE001
        return None
    try:
        metrics = result.metrics.to_dict()
        metrics_store = {k: v for k, v in metrics.items() if k != "equity_curve"}
        metrics_store["equity_curve_len"] = len(metrics.get("equity_curve") or [])
        db = HelixDB()
        insert = getattr(db, "insert_backtest", None)
        if callable(insert):
            try:
                return int(
                    insert(
                        symbol=result.symbol,
                        strategy=result.strategy,
                        params=result.params,
                        metrics=metrics_store,
                        notes=f"n_trades={result.metrics.n_trades}",
                    )
                )
            except TypeError:
                return int(
                    insert(
                        {
                            "symbol": result.symbol,
                            "strategy": result.strategy,
                            "params": result.params,
                            "metrics": metrics_store,
                            "notes": f"n_trades={result.metrics.n_trades}",
                        }
                    )
                )
        with db.conn() as conn:
            cur = conn.execute(
                """INSERT INTO backtests (ts, symbol, strategy, params_json, metrics_json, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    result.symbol,
                    result.strategy,
                    json.dumps(result.params),
                    json.dumps(metrics_store),
                    f"n_trades={result.metrics.n_trades}",
                ),
            )
            return int(cur.lastrowid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not store backtest: %s", type(exc).__name__)
        return None



def run_backtest_on_bars(
opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    **kwargs: Any,
) -> BacktestResult:
    """Convenience for tests — no network."""
    cfg = kwargs.pop("cfg", None) or BacktestConfig(warmup=min(50, max(30, len(closes) // 4)))
    if len(closes) < 80:
        cfg.warmup = min(cfg.warmup, max(25, len(closes) // 3))
        cfg.ema_trend = min(cfg.ema_trend, max(30, len(closes) // 2))
    return run_backtest(
        cfg,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        store_db=kwargs.pop("store_db", False),
        **kwargs,
    )
