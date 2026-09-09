"""HELIX 1.0 cycle orchestrator — quant fusion first, optional LLM later."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from helix_v1.db import HelixDB, get_db
from helix_v1.execution import build_execution_plan, get_adapter
from helix_v1.explain import build_explanation
from helix_v1.modes import Mode, ModeGuard, TradingMode, current_mode
from helix_v1.portfolio import compute_exposure as analyze_portfolio
from helix_v1.regime import detect_regime
from helix_v1.risk_engine import AccountState, ProposedOrder, RiskEngine, is_kill_switch_on
from helix_v1.signal_fusion import FusionState, fuse_signals
from helix_v1.sizing import size_position
from helix_v1.strategies import run_all
from helix_v1.trade_manager import manage_open_thesis

logger = logging.getLogger(__name__)


def _account_from_env(open_positions: list[dict[str, Any]] | None = None) -> AccountState:
    bal = float(os.environ.get("HELIX_ACCOUNT_BALANCE", "50") or 50)
    eq = float(os.environ.get("HELIX_ACCOUNT_EQUITY", str(bal)) or bal)
    syms = [str(p.get("symbol") or "") for p in (open_positions or [])]
    return AccountState(
        equity=eq,
        balance=bal,
        open_positions=len(open_positions or []),
        open_symbols=syms,
        kill_switch=is_kill_switch_on() if "is_kill_switch_on" in dir() else False,
        daily_pnl_pct=float(os.environ.get("HELIX_DAILY_PNL_PCT", "0") or 0),
        weekly_pnl_pct=float(os.environ.get("HELIX_WEEKLY_PNL_PCT", "0") or 0),
        drawdown_pct=float(os.environ.get("HELIX_DRAWDOWN_PCT", "0") or 0),
    )


def run_helix_cycle(
    symbol: str,
    snapshot: dict[str, Any] | None = None,
    *,
    mode: Mode | TradingMode | str | None = None,
    headlines: list[Any] | None = None,
    open_position: dict[str, Any] | None = None,
    open_positions: list[dict[str, Any]] | None = None,
    use_llm: bool = False,
    db: HelixDB | None = None,
) -> dict[str, Any]:
    """
    Quant-first pipeline.
    LIVE broker submits only when HELIX_MODE=LIVE and risk approves.
    """
    mode_e = mode if isinstance(mode, TradingMode) else (
        TradingMode(str(mode).upper()) if mode else current_mode()
    )
    guard = ModeGuard(mode_e)
    db = db or get_db()

    if snapshot is None:
        from helix.brain import build_market_snapshot

        snapshot = build_market_snapshot(symbol)
    if headlines:
        snapshot = {**snapshot, "headlines": headlines}

    structure = snapshot.get("structure") if isinstance(snapshot.get("structure"), dict) else {}
    regime = detect_regime(snapshot)
    try:
        db.insert_regime(symbol, regime.regime, regime.strength, regime.to_dict())
    except Exception as exc:  # noqa: BLE001
        logger.warning("regime persist failed: %s", exc)

    signals = run_all(snapshot, structure, regime)
    fusion = fuse_signals(
        signals,
        snapshot,
        structure,
        regime,
        open_position=open_position,
        min_confluence=3,
    )

    positions = open_positions or ([] if not open_position else [open_position])
    portfolio = analyze_portfolio(positions)
    account = _account_from_env(positions)
    try:
        account.kill_switch = is_kill_switch_on()
    except Exception:
        pass

    atr = snapshot.get("atr_points")
    try:
        atr_f = float(atr) if atr is not None else None
    except (TypeError, ValueError):
        atr_f = None

    risk_pct = float(os.environ.get("HELIX_RISK_PERCENT", "0.5") or 0.5)
    size = size_position(
        equity=account.equity,
        symbol=symbol,
        atr_points=atr_f,
        atr_mult=1.5,
        risk_pct=risk_pct,
        max_lots=float(os.environ.get("HELIX_MAX_LOTS", "1") or 1),
        vol_scalar=1.4 if regime.volatility == "high" else None,
    )
    # Micro-account floor: $50 demos often round to 0 lots — allow 0.01 if implied risk ≤ 2%
    if size.lots <= 0 and account.equity > 0 and account.equity <= 500:
        bumped = size_position(
            equity=account.equity,
            symbol=symbol,
            atr_points=atr_f,
            atr_mult=1.5,
            risk_pct=min(2.0, max(risk_pct, 1.0)),
            max_lots=float(os.environ.get("HELIX_MAX_LOTS", "1") or 1),
            min_lots=0.01,
        )
        # Force min lot only when stop risk for 0.01 is under 2% equity
        if bumped.lots <= 0 and bumped.stop_points > 0:
            from helix_v1.sizing import _pip_value_per_lot, round_lots_down, SizeResult, _lot_step_for
            per = bumped.stop_points * _pip_value_per_lot(symbol) * 0.01
            if per <= account.equity * 0.02:
                size = SizeResult(
                    lots=0.01,
                    risk_amount=per,
                    risk_pct=(per / account.equity) * 100.0,
                    stop_points=bumped.stop_points,
                    lot_step=_lot_step_for(symbol),
                    capped=True,
                    rationale=f"micro-account floor 0.01 lots (~{per:.2f} risk)",
                )
        elif bumped.lots > 0:
            size = bumped

    manage_d = None
    action = fusion.action
    if open_position:
        advice = manage_open_thesis(open_position, fusion, regime, snapshot)
        if advice is not None:
            manage_d = advice.to_dict()
            if advice.action == "exit":
                action = "close"
            elif advice.action in {"hold", "trail", "reduce"}:
                action = "hold" if fusion.state is not FusionState.EXIT else "close"

    if fusion.state in (FusionState.NO_TRADE, FusionState.WATCH, FusionState.SETUP_FORMING):
        if action in ("buy", "sell"):
            action = "hold"

    if fusion.state in (FusionState.VALID_SETUP, FusionState.HIGH_CONFIDENCE) and fusion.action in (
        "buy",
        "sell",
    ):
        action = fusion.action

    spread = snapshot.get("spread_points")
    try:
        spread_f = float(spread) if spread is not None else None
    except (TypeError, ValueError):
        spread_f = None

    proposed = ProposedOrder(
        symbol=symbol,
        action=action,
        risk_pct=size.risk_pct,
        lots=size.lots,
        stop_distance=None,
        spread_points=spread_f,
        rr=1.5,
    )
    verdict = RiskEngine().check(account, proposed)

    if action in ("buy", "sell") and (not verdict.approved or size.lots <= 0):
        action = "hold"

    if account.kill_switch:
        action = "hold"

    plan = build_execution_plan(
        symbol=symbol,
        action=action,
        lots=size.lots if action in ("buy", "sell") else 0.0,
        snapshot=snapshot,
        confidence=fusion.helix_confidence_score,
        rationale=fusion.rationale,
        mode=mode_e,
        stop_points=size.stop_points,
        take_points=size.stop_points * 1.5 if size.stop_points else None,
        meta={
            "state": fusion.state.value,
            "confluence": fusion.confluence_count,
            "regime": regime.regime,
            "risk": verdict.to_dict(),
        },
    )

    # SAFE never sends buy/sell to adapters as live intent
    if guard.is_safe and plan.action in ("buy", "sell"):
        plan.action = "hold"
        plan.rationale = "SAFE mode — " + plan.rationale

    adapter = get_adapter(mode_e)
    # LIVE mt5 adapter asserts; PAPER/SAFE use paper
    if mode_e is TradingMode.LIVE and plan.action in ("buy", "sell", "close", "hold"):
        exec_result = adapter.submit(plan)
    elif mode_e is TradingMode.BACKTEST:
        exec_result = adapter.submit(plan)
    else:
        # paper / safe
        from helix_v1.execution import PaperAdapter

        exec_result = PaperAdapter(write_signal_file=True).submit(plan)

    explanation = build_explanation(
        snapshot=snapshot,
        regime=regime,
        fusion=fusion,
        risk=verdict.to_dict(),
        sizing=size.to_dict(),
        manage=manage_d,
    )

    try:
        db.insert_signal(
            symbol,
            fusion.state.value,
            fusion.helix_confidence_score,
            action,
            {"fusion": fusion.to_dict(), "plan": plan.to_signal_payload()},
        )
        db.insert_ai_decision(
            symbol,
            action,
            fusion.helix_confidence_score,
            plan.rationale,
            "helix_v1_quant",
            {"explanation": explanation, "use_llm": use_llm},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("persist failed: %s", exc)

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "mode": mode_e.value,
        "regime": regime.to_dict(),
        "fusion": fusion.to_dict(),
        "portfolio": portfolio.to_dict(),
        "risk": verdict.to_dict(),
        "sizing": size.to_dict(),
        "plan": plan.to_signal_payload(),
        "execution": exec_result,
        "explanation": explanation,
        "strategies": [s.to_dict() for s in signals],
        "intelligence": "HELIX quant fusion — LLM layer optional (xAI Grok → OpenAI → Anthropic)",
    }
