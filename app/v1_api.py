"""HELIX 1.0 API routes."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from helix.config import DEFAULT_SYMBOL
from helix_v1.modes import current_mode
from helix_v1.monitoring import health_snapshot
from helix_v1.risk_engine import is_kill_switch_on, set_kill_switch

router = APIRouter(prefix="/api/v1", tags=["helix-v1"])

HELIX_API_TOKEN = os.environ.get("HELIX_API_TOKEN", "").strip()


def _check_token(x_helix_token: str | None) -> None:
    if not HELIX_API_TOKEN:
        return
    if not x_helix_token or x_helix_token != HELIX_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing X-HELIX-Token")


@router.get("/status")
def v1_status() -> dict[str, Any]:
    h = health_snapshot()
    return {
        "ok": h.get("ok", True),
        "version": "1.0.0",
        "mode": current_mode().value,
        "kill_switch": is_kill_switch_on(),
        "health": h,
        "intelligence": "HELIX quant + optional LLM (xAI Grok → OpenAI → Anthropic)",
    }


@router.get("/regime/{symbol}")
def v1_regime(symbol: str) -> dict[str, Any]:
    from helix.brain import build_market_snapshot
    from helix_v1.regime import detect_regime

    snap = build_market_snapshot(symbol.upper())
    regime = detect_regime(snap)
    return {"ok": True, "symbol": symbol.upper(), "regime": regime.to_dict(), "snapshot_note": snap.get("note")}


@router.get("/scan")
def v1_scan(symbols: str | None = Query(None, description="Comma-separated symbols")) -> dict[str, Any]:
    from helix_v1.scanner import DEFAULT_UNIVERSE, scan_market

    syms = [s.strip().upper() for s in symbols.split(",")] if symbols else DEFAULT_UNIVERSE
    # Use lightweight synthetic scan from live snapshots when possible — may hit Yahoo
    rows = scan_market(syms)
    return {"ok": True, "count": len(rows), "opportunities": rows, "results": rows}


@router.get("/performance")
def v1_performance() -> dict[str, Any]:
    from helix_v1.db import get_db
    from helix_v1.performance import compute_metrics

    trades = get_db().list_trades(limit=500)
    metrics = compute_metrics(trades).to_dict() if hasattr(compute_metrics(trades), "to_dict") else None
    if metrics is None:
        m = compute_metrics(trades)
        metrics = {
            "n_trades": m.n_trades,
            "win_rate": m.win_rate,
            "profit_factor": m.profit_factor,
            "expectancy": m.expectancy,
            "max_drawdown": m.max_drawdown,
            "net_pnl": m.net_pnl,
        }
    return {"ok": True, "metrics": metrics, "n": len(trades)}


@router.get("/explain/latest")
def v1_explain_latest(symbol: str | None = None) -> Any:
    import json
    from helix_v1.db import get_db

    row = get_db().latest_signal(symbol)
    if not row:
        raise HTTPException(status_code=404, detail="no signal")
    payload = row.get("payload_json")
    try:
        data = json.loads(payload) if isinstance(payload, str) else (payload or {})
    except json.JSONDecodeError:
        data = {"raw": payload}
    return {"ok": True, "signal": dict(row), "payload": data}


@router.get("/mode")
def v1_mode() -> dict[str, Any]:
    return {"ok": True, "mode": current_mode().value, "env": os.environ.get("HELIX_MODE", "PAPER")}


@router.post("/kill-switch")
def v1_kill_switch(
    body: dict[str, Any] | None = None,
    x_helix_token: str | None = Header(default=None, alias="X-HELIX-Token"),
) -> dict[str, Any]:
    _check_token(x_helix_token)
    body = body or {}
    active = bool(body.get("active", True))
    reason = str(body.get("reason") or ("halt" if active else "resume"))
    result = set_kill_switch(active, reason)
    return {"ok": True, "kill_switch": result}


@router.post("/cycle")
def v1_cycle(
    symbol: str = Query(DEFAULT_SYMBOL),
    x_helix_token: str | None = Header(default=None, alias="X-HELIX-Token"),
) -> dict[str, Any]:
    """Run one HELIX 1.0 quant cycle (no LLM unless HELIX_V1_LLM=1)."""
    _check_token(x_helix_token)
    from helix_v1.pipeline import run_helix_cycle

    use_llm = os.environ.get("HELIX_V1_LLM", "").strip() in {"1", "true", "yes"}
    out = run_helix_cycle(symbol.upper(), use_llm=use_llm)
    return {"ok": True, "result": out}


@router.get("/analytics")
def v1_analytics() -> dict[str, Any]:
    from helix_v1.analytics import dashboard_analytics
    return {"ok": True, **dashboard_analytics()}


@router.get("/mtf/{symbol}")
def v1_mtf(symbol: str) -> dict[str, Any]:
    import os
    from helix_v1.mtf import build_mtf
    offline = os.environ.get("HELIX_MTF_OFFLINE", "").strip() in {"1", "true", "yes"}
    mtf = build_mtf(symbol.upper(), live=not offline)
    return {"ok": True, "symbol": symbol.upper(), "mtf": mtf.to_dict()}


@router.get("/holly/status")
def v1_holly_status(symbol: str = Query("EURUSD")) -> dict[str, Any]:
    from helix_v1.providers.holly import ApiHollyProvider, holly_vote_for_symbol, ideas_path

    vote = holly_vote_for_symbol(symbol.upper())
    return {
        "ok": True,
        "provider": "trade_ideas_holly",
        "api_configured": ApiHollyProvider().configured,
        "ideas_path": str(ideas_path()),
        "vote": vote,
        "mt5_path": "signals/latest.json → HELIX.mq5 EA",
    }


@router.get("/holly/ideas")
def v1_holly_ideas(symbol: str | None = None) -> dict[str, Any]:
    from helix_v1.providers.holly import collect_holly_ideas

    ideas = collect_holly_ideas(symbol.upper() if symbol else None)
    return {"ok": True, "count": len(ideas), "ideas": [i.to_dict() for i in ideas]}


@router.post("/holly/ingest")
def v1_holly_ingest(
    body: dict[str, Any] | list[Any] | None = None,
    x_helix_token: str | None = Header(default=None, alias="X-HELIX-Token"),
) -> dict[str, Any]:
    """Ingest Trade Ideas / Holly alerts (webhook or manual JSON)."""
    _check_token(x_helix_token)
    from helix_v1.providers.holly import ingest_payload

    incoming = ingest_payload(body or {})
    return {
        "ok": True,
        "ingested": len(incoming),
        "ideas": [i.to_dict() for i in incoming],
        "note": "Holly ideas fuse into HELIX quant → risk → MT5 EA; Holly never trades alone.",
    }
