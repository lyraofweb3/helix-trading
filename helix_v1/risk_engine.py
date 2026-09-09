"""Hard risk limits — independent of AI. Must approve before execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from helix.config import (
    FX_MAX_SPREAD_POINTS,
    MAX_DAILY_LOSS_PCT,
    MAX_POSITIONS,
    MAX_TRADES_PER_DAY,
    MIN_RR,
    RISK_PERCENT,
)


@dataclass
class AccountState:
    equity: float
    balance: float
    daily_pnl_pct: float = 0.0
    weekly_pnl_pct: float = 0.0
    drawdown_pct: float = 0.0
    open_positions: int = 0
    trades_today: int = 0
    kill_switch: bool = False
    open_symbols: list[str] = field(default_factory=list)
    currency: str = "USD"
    free_margin: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> AccountState:
        d = d or {}
        return cls(
            equity=float(d.get("equity", d.get("balance", 10_000.0))),
            balance=float(d.get("balance", d.get("equity", 10_000.0))),
            daily_pnl_pct=float(d.get("daily_pnl_pct", 0.0)),
            weekly_pnl_pct=float(d.get("weekly_pnl_pct", 0.0)),
            drawdown_pct=float(d.get("drawdown_pct", 0.0)),
            open_positions=int(d.get("open_positions", 0)),
            trades_today=int(d.get("trades_today", 0)),
            kill_switch=bool(d.get("kill_switch", False)),
            open_symbols=list(d.get("open_symbols") or []),
            currency=str(d.get("currency", "USD")),
        )


@dataclass
class ProposedOrder:
    symbol: str
    action: str  # buy | sell | close | hold
    risk_pct: float | None = None
    lots: float | None = None
    stop_distance: float | None = None
    take_distance: float | None = None
    spread_points: float | None = None
    slippage_points: float | None = None
    correlated_open: list[str] = field(default_factory=list)
    rr: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProposedOrder:
        return cls(
            symbol=str(d.get("symbol", "")).upper(),
            action=str(d.get("action", "hold")).lower(),
            risk_pct=float(d["risk_pct"]) if d.get("risk_pct") is not None else None,
            lots=float(d["lots"]) if d.get("lots") is not None else None,
            stop_distance=float(d["stop_distance"]) if d.get("stop_distance") is not None else None,
            take_distance=float(d["take_distance"]) if d.get("take_distance") is not None else None,
            spread_points=float(d["spread_points"]) if d.get("spread_points") is not None else None,
            slippage_points=float(d["slippage_points"]) if d.get("slippage_points") is not None else None,
            correlated_open=list(d.get("correlated_open") or []),
            rr=float(d["rr"]) if d.get("rr") is not None else None,
        )


@dataclass
class RiskVerdict:
    approved: bool
    reasons: list[str] = field(default_factory=list)
    adjusted_risk_pct: float | None = None
    code: str = "OK"

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "reasons": list(self.reasons),
            "adjusted_risk_pct": self.adjusted_risk_pct,
            "code": self.code,
        }


# Simple FX correlation buckets (heat)
CORR_GROUPS: dict[str, set[str]] = {
    "usd_long": {"USDJPY", "USDCHF", "USDCAD"},
    "usd_short_eu": {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"},
    "eur_block": {"EURUSD", "EURGBP", "EURJPY"},
    "gbp_block": {"GBPUSD", "EURGBP", "GBPJPY"},
    "metals": {"XAUUSD", "GOLD"},
    "oil": {"USOIL", "UKOIL", "WTI"},
}


def correlated_symbols(symbol: str) -> set[str]:
    sym = symbol.upper()
    out: set[str] = set()
    for group in CORR_GROUPS.values():
        if sym in group:
            out |= group
    out.discard(sym)
    return out


@dataclass
class RiskLimits:
    risk_percent: float = RISK_PERCENT
    max_daily_loss_pct: float = MAX_DAILY_LOSS_PCT
    max_weekly_loss_pct: float = 5.0
    max_drawdown_pct: float = 10.0
    max_positions: int = MAX_POSITIONS
    max_trades_per_day: int = MAX_TRADES_PER_DAY
    max_correlated: int = 1
    max_spread_points: float = float(FX_MAX_SPREAD_POINTS)
    max_slippage_points: float = 30.0
    min_rr: float = MIN_RR


class RiskEngine:
    """Deterministic risk gate — never consults LLMs."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def check(self, account: AccountState | dict[str, Any], proposed: ProposedOrder | dict[str, Any]) -> RiskVerdict:
        acct = account if isinstance(account, AccountState) else AccountState.from_dict(account)
        prop = proposed if isinstance(proposed, ProposedOrder) else ProposedOrder.from_dict(proposed)
        reasons: list[str] = []

        action = prop.action
        if action in {"hold", "close"}:
            # close always allowed unless kill forbids everything discretionary
            if action == "close":
                return RiskVerdict(True, ["close allowed"], code="OK_CLOSE")
            return RiskVerdict(True, ["hold — no risk"], code="OK_HOLD")

        if action not in {"buy", "sell"}:
            return RiskVerdict(False, [f"unknown action {action}"], code="BAD_ACTION")

        if acct.kill_switch:
            return RiskVerdict(False, ["kill_switch active"], code="KILL")

        if acct.equity <= 0 or acct.balance <= 0:
            return RiskVerdict(False, ["non-positive equity/balance"], code="EQUITY")

        if abs(acct.daily_pnl_pct) >= self.limits.max_daily_loss_pct and acct.daily_pnl_pct < 0:
            return RiskVerdict(
                False,
                [f"daily loss {acct.daily_pnl_pct:.2f}% >= cap {self.limits.max_daily_loss_pct}%"],
                code="DAILY_LOSS",
            )

        if acct.weekly_pnl_pct <= -abs(self.limits.max_weekly_loss_pct):
            return RiskVerdict(
                False,
                [f"weekly loss {acct.weekly_pnl_pct:.2f}% >= cap {self.limits.max_weekly_loss_pct}%"],
                code="WEEKLY_LOSS",
            )

        if acct.drawdown_pct >= self.limits.max_drawdown_pct:
            return RiskVerdict(
                False,
                [f"drawdown {acct.drawdown_pct:.2f}% >= max {self.limits.max_drawdown_pct}%"],
                code="MAX_DD",
            )

        if acct.open_positions >= self.limits.max_positions:
            return RiskVerdict(
                False,
                [f"open positions {acct.open_positions} >= max {self.limits.max_positions}"],
                code="MAX_POS",
            )

        if acct.trades_today >= self.limits.max_trades_per_day:
            return RiskVerdict(
                False,
                [f"trades today {acct.trades_today} >= max {self.limits.max_trades_per_day}"],
                code="MAX_TRADES",
            )

        risk_pct = prop.risk_pct if prop.risk_pct is not None else self.limits.risk_percent
        if risk_pct > self.limits.risk_percent + 1e-9:
            reasons.append(
                f"risk_pct {risk_pct} > limit {self.limits.risk_percent} — will clamp"
            )
            risk_pct = self.limits.risk_percent

        if prop.spread_points is not None and prop.spread_points > self.limits.max_spread_points:
            return RiskVerdict(
                False,
                [f"spread {prop.spread_points} > max {self.limits.max_spread_points}"],
                code="SPREAD",
            )

        if prop.slippage_points is not None and prop.slippage_points > self.limits.max_slippage_points:
            return RiskVerdict(
                False,
                [f"slippage {prop.slippage_points} > max {self.limits.max_slippage_points}"],
                code="SLIPPAGE",
            )

        if prop.rr is not None and prop.rr < self.limits.min_rr:
            return RiskVerdict(
                False,
                [f"RR {prop.rr} < min {self.limits.min_rr}"],
                code="MIN_RR",
            )

        # Correlated heat
        corr = correlated_symbols(prop.symbol)
        open_set = set(s.upper() for s in acct.open_symbols) | set(
            s.upper() for s in prop.correlated_open
        )
        heat = len(corr & open_set)
        if heat >= self.limits.max_correlated:
            return RiskVerdict(
                False,
                [f"correlated heat {heat} with {sorted(corr & open_set)}"],
                code="CORR",
            )

        if prop.stop_distance is not None and prop.stop_distance <= 0:
            return RiskVerdict(False, ["stop_distance must be > 0"], code="STOP")

        return RiskVerdict(
            True,
            reasons or ["all hard limits passed"],
            adjusted_risk_pct=risk_pct,
            code="OK",
        )



# --- kill switch + pipeline compatibility shims ---
import os
from pathlib import Path as _Path

from helix.config import SIGNALS_DIR as _SIGNALS_DIR


def kill_switch_path() -> _Path:
    env = os.environ.get("HELIX_KILL_SWITCH_PATH", "").strip()
    if env:
        return _Path(env).expanduser().resolve()
    return (_SIGNALS_DIR / "KILL_SWITCH").resolve()


def is_kill_switch_on() -> bool:
    p = kill_switch_path()
    if not p.exists():
        return False
    if p.is_dir():
        return True
    try:
        text = p.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return True
    if text in {"0", "false", "off", "no"}:
        return False
    return True


def set_kill_switch(active: bool, reason: str = "manual") -> dict:
    p = kill_switch_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if active:
        import json
        from datetime import datetime, timezone
        p.write_text(
            json.dumps({"active": True, "reason": reason, "ts": datetime.now(timezone.utc).isoformat()}, indent=2)
            + "\n",
            encoding="utf-8",
        )
    elif p.exists():
        try:
            p.unlink()
        except OSError:
            p.write_text("false\n", encoding="utf-8")
    return {"active": is_kill_switch_on(), "path": str(p), "reason": reason}


def default_limits() -> RiskLimits:
    return RiskLimits()


ProposedTrade = ProposedOrder


def check(account, proposed, limits: RiskLimits | None = None) -> RiskVerdict:
    return RiskEngine(limits).check(account, proposed)
