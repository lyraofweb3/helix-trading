"""ExecutionPlan builder + broker adapters (MT5 bridge file + paper DB)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from helix.config import JOURNAL_PATH, LATEST_SIGNAL_PATH, SIGNALS_DIR
from helix_v1 import db as helix_db
from helix_v1.modes import Mode, ModeGuard


@dataclass
class ExecutionPlan:
    symbol: str
    action: str
    lots: float
    entry: float | None = None
    stop: float | None = None
    take: float | None = None
    confidence: float = 0.0
    rationale: str = ""
    mode: str = "paper"
    stop_hint: str | None = None
    take_hint: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_signal_payload(self) -> dict[str, Any]:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": self.action,
            "symbol": self.symbol,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "stop_hint": self.stop_hint or (str(self.stop) if self.stop is not None else None),
            "take_hint": self.take_hint or (str(self.take) if self.take is not None else None),
            "lots": self.lots,
            "entry": self.entry,
            "stop": self.stop,
            "take": self.take,
            "source": "helix_v1",
            "mode": self.mode,
            "meta": self.meta,
        }


def build_execution_plan(
    *,
    symbol: str,
    action: str,
    lots: float,
    snapshot: dict[str, Any],
    confidence: float,
    rationale: str,
    mode: Mode | str,
    stop_points: float | None = None,
    take_points: float | None = None,
    min_rr: float = 1.5,
    meta: dict[str, Any] | None = None,
) -> ExecutionPlan:
    from helix.prices import point_size

    last = snapshot.get("last_close") or snapshot.get("bid") or snapshot.get("ask")
    try:
        entry = float(last) if last is not None else None
    except (TypeError, ValueError):
        entry = None

    pt = point_size(symbol)
    stop = take = None
    stop_hint = take_hint = None
    if entry is not None and stop_points and stop_points > 0:
        dist = stop_points * pt
        if action == "buy":
            stop = round(entry - dist, 5)
            take = round(entry + dist * min_rr, 5)
        elif action == "sell":
            stop = round(entry + dist, 5)
            take = round(entry - dist * min_rr, 5)
        stop_hint = f"{stop_points:.1f} pts"
        take_hint = f"{stop_points * min_rr:.1f} pts"
    mode_s = mode.value if isinstance(mode, Mode) else str(mode)
    return ExecutionPlan(
        symbol=symbol.upper(),
        action=action,
        lots=lots,
        entry=entry,
        stop=stop,
        take=take,
        confidence=confidence,
        rationale=rationale,
        mode=mode_s,
        stop_hint=stop_hint,
        take_hint=take_hint,
        meta=meta or {},
    )


@runtime_checkable
class BrokerAdapter(Protocol):
    name: str

    def submit(self, plan: ExecutionPlan) -> dict[str, Any]: ...


class Mt5BridgeAdapter:
    """Write latest.json compatible with existing HELIX.mq5 EA."""

    name = "mt5"

    def __init__(self, signal_path: Path | None = None, journal_path: Path | None = None) -> None:
        self.signal_path = signal_path or LATEST_SIGNAL_PATH
        self.journal_path = journal_path or JOURNAL_PATH

    def submit(self, plan: ExecutionPlan) -> dict[str, Any]:
        ModeGuard(plan.mode).assert_can_submit_live()
        SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
        payload = plan.to_signal_payload()
        payload["source"] = "helix_v1-mt5"
        payload.setdefault("meta", {})
        payload["meta"]["bridge"] = "mt5_ea_bridge"
        payload["meta"]["ea"] = "HELIX.mq5"
        payload["meta"]["fused_with"] = payload["meta"].get("sources") or ["helix_quant", "mt5_ea"]
        text = json.dumps(payload, ensure_ascii=False)
        self.signal_path.write_text(text + "\n", encoding="utf-8")
        with self.journal_path.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")
        helix_db.insert_order(
            symbol=plan.symbol,
            action=plan.action,
            lots=plan.lots,
            price=plan.entry,
            stop=plan.stop,
            take=plan.take,
            status="submitted_mt5",
            mode=plan.mode,
            reason=plan.rationale,
            meta=plan.meta,
        )
        return {"ok": True, "adapter": self.name, "path": str(self.signal_path), "payload": payload}


class PaperAdapter:
    """Log to SQLite (+ optional signal file) — never asserts live ModeGuard."""

    name = "paper"

    def __init__(self, write_signal_file: bool = True) -> None:
        self.write_signal_file = write_signal_file

    def submit(self, plan: ExecutionPlan) -> dict[str, Any]:
        payload = plan.to_signal_payload()
        payload["source"] = "helix_v1-paper"
        order_id = helix_db.insert_order(
            symbol=plan.symbol,
            action=plan.action,
            lots=plan.lots,
            price=plan.entry,
            stop=plan.stop,
            take=plan.take,
            status="paper",
            mode=plan.mode,
            reason=plan.rationale,
            meta=plan.meta,
        )
        if plan.action in {"buy", "sell"}:
            helix_db.insert_trade(
                symbol=plan.symbol,
                side=plan.action,
                lots=plan.lots,
                entry=plan.entry,
                stop=plan.stop,
                take=plan.take,
                mode=plan.mode,
                status="paper_open",
                thesis=plan.rationale,
                meta=plan.meta,
            )
        if self.write_signal_file:
            SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
            text = json.dumps(payload, ensure_ascii=False)
            LATEST_SIGNAL_PATH.write_text(text + "\n", encoding="utf-8")
            with JOURNAL_PATH.open("a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        return {"ok": True, "adapter": self.name, "order_id": order_id, "payload": payload}


class MetaApiAdapter:
    """Cloud MT5 via MetaAPI — no home PC required. Additive to Mt5BridgeAdapter."""

    name = "metaapi"

    def __init__(self, also_write_signal_file: bool = True) -> None:
        self.also_write_signal_file = also_write_signal_file

    def submit(self, plan: ExecutionPlan) -> dict[str, Any]:
        ModeGuard(plan.mode).assert_can_submit_live()
        from helix_v1.providers.metaapi import (
            close_symbol_positions,
            metaapi_configured,
            place_market_order,
        )

        if not metaapi_configured():
            return {"ok": False, "adapter": self.name, "error": "METAAPI_TOKEN/ACCOUNT_ID missing"}

        payload = plan.to_signal_payload()
        payload["source"] = "helix_v1-metaapi"
        payload.setdefault("meta", {})
        payload["meta"]["bridge"] = "metaapi_cloud"
        payload["meta"]["execution_path"] = "HELIX Railway → MetaAPI cloud MT5 → Exness"

        result: dict[str, Any]
        if plan.action == "close":
            result = close_symbol_positions(plan.symbol)
        elif plan.action in ("buy", "sell"):
            result = place_market_order(
                symbol=plan.symbol,
                side=plan.action,
                volume=float(plan.lots or 0.01),
                stop_loss=plan.stop,
                take_profit=plan.take,
                comment="HELIX",
            )
        else:
            # hold — still journal signal, no broker order
            result = {"ok": True, "skipped": True, "reason": "hold"}

        helix_db.insert_order(
            symbol=plan.symbol,
            action=plan.action,
            lots=plan.lots,
            price=plan.entry,
            stop=plan.stop,
            take=plan.take,
            status="metaapi_ok" if result.get("ok") else "metaapi_fail",
            mode=plan.mode,
            reason=plan.rationale,
            meta={**(plan.meta or {}), "metaapi": result},
        )
        if self.also_write_signal_file:
            SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
            text = json.dumps({**payload, "metaapi": result}, ensure_ascii=False)
            LATEST_SIGNAL_PATH.write_text(text + "\n", encoding="utf-8")
            with JOURNAL_PATH.open("a", encoding="utf-8") as fh:
                fh.write(text + "\n")
        return {"ok": bool(result.get("ok")), "adapter": self.name, "result": result, "payload": payload}


class BacktestAdapter:
    name = "backtest"

    def submit(self, plan: ExecutionPlan) -> dict[str, Any]:
        oid = helix_db.insert_order(
            symbol=plan.symbol,
            action=plan.action,
            lots=plan.lots,
            price=plan.entry,
            stop=plan.stop,
            take=plan.take,
            status="backtest",
            mode="backtest",
            reason=plan.rationale,
            meta=plan.meta,
        )
        return {"ok": True, "adapter": self.name, "order_id": oid}


def get_adapter(mode: Mode | str) -> BrokerAdapter:
    guard = ModeGuard(mode)
    name = guard.choose_adapter_name()
    if name == "metaapi":
        return MetaApiAdapter()
    if name == "mt5":
        return Mt5BridgeAdapter()
    if name == "backtest":
        return BacktestAdapter()
    return PaperAdapter()
