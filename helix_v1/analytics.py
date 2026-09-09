"""Journal / expectancy analytics for the HELIX dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from helix.config import JOURNAL_PATH
from helix_v1.db import get_db
from helix_v1.performance import TradeRecord, compute_metrics


def _journal_trades(limit: int = 200) -> list[TradeRecord]:
    path = JOURNAL_PATH
    if not path.is_file():
        return []
    rows: list[TradeRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Journal is signals; use confidence proxy only if pnl present
        if e.get("pnl") is None:
            continue
        rows.append(TradeRecord.from_mapping(e))
    return rows


def dashboard_analytics() -> dict[str, Any]:
    db_trades = get_db().list_trades(limit=500)
    trades = [TradeRecord.from_mapping(t) for t in db_trades]
    if not trades:
        trades = _journal_trades()
    m = compute_metrics(trades)
    # Quality score: blend expectancy + PF + DD control (0..100 display)
    pf = min(m.profit_factor, 5.0) if m.profit_factor == m.profit_factor else 0.0
    dd_pen = max(0.0, 1.0 - (m.max_drawdown_pct or 0) / 100.0)
    quality = max(0.0, min(100.0, 40 * (m.expectancy > 0) + 15 * pf + 25 * dd_pen + 20 * m.win_rate))
    return {
        "metrics": m.to_dict() if hasattr(m, "to_dict") else {
            "n_trades": m.n_trades,
            "win_rate": m.win_rate,
            "profit_factor": m.profit_factor,
            "expectancy": m.expectancy,
            "max_drawdown": m.max_drawdown,
            "max_drawdown_pct": m.max_drawdown_pct,
            "net_pnl": m.net_pnl,
        },
        "quality_score": round(quality, 1),
        "philosophy": "expectancy + profit_factor + drawdown_control",
    }
