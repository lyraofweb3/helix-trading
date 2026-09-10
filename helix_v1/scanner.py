"""Multi-instrument opportunity scanner — ranks, does not auto-trade."""

from __future__ import annotations

import logging
from typing import Any

from helix_v1.regime import detect_regime
from helix_v1.signal_fusion import fuse_signals
from helix_v1.strategies import run_all

logger = logging.getLogger(__name__)

try:
    from helix.config import SYMBOLS as DEFAULT_UNIVERSE
except Exception:  # noqa: BLE001
    DEFAULT_UNIVERSE = [
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "AUDUSD",
        "USDCAD",
        "USDCHF",
        "NZDUSD",
        "XAUUSD",
        "XAGUSD",
        "USOIL",
        "UKOIL",
    ]


def scan_symbol(symbol: str, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    if snapshot is None:
        from helix_v1.trade_style import is_scalp
        if is_scalp():
            from helix_v1.scalp import build_scalp_snapshot
            snapshot = build_scalp_snapshot(symbol)
        else:
            from helix.brain import build_market_snapshot
            snapshot = build_market_snapshot(symbol)
    structure = snapshot.get("structure") if isinstance(snapshot.get("structure"), dict) else {}
    regime = detect_regime(snapshot)
    signals = run_all(snapshot, structure, regime)
    fusion = fuse_signals(signals, snapshot, structure, regime)
    idea_odds = 0.0
    idea_channel = ""
    try:
        from helix_v1.idea_engine import best_idea
        top = best_idea(snapshot)
        if top:
            idea_odds = float(top.odds)
            idea_channel = top.channel
    except Exception:  # noqa: BLE001
        pass
    return {
        "symbol": symbol,
        "regime": regime.to_dict(),
        "state": fusion.state.value,
        "action": fusion.action,
        "score": fusion.helix_confidence_score,
        "confluence": fusion.confluence_count,
        "rationale": fusion.rationale,
        "idea_odds": idea_odds,
        "idea_channel": idea_channel,
    }


def scan_market(
    symbols: list[str] | None = None,
    snapshots: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    symbols = symbols or DEFAULT_UNIVERSE
    rows: list[dict[str, Any]] = []
    for sym in symbols:
        try:
            snap = (snapshots or {}).get(sym)
            rows.append(scan_symbol(sym, snap))
        except Exception as exc:  # noqa: BLE001
            logger.warning("scan %s failed: %s", sym, exc)
            rows.append(
                {
                    "symbol": sym,
                    "state": "ERROR",
                    "action": "hold",
                    "score": 0.0,
                    "confluence": 0,
                    "rationale": f"{type(exc).__name__}: {exc}",
                }
            )
    rows.sort(key=lambda r: (r.get("score") or 0.0, r.get("confluence") or 0), reverse=True)
    return rows
