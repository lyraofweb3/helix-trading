"""Record strategy×regime outcomes and suggest weights (never auto-apply to live)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_LEARNING_SCHEMA = """
CREATE TABLE IF NOT EXISTS learning_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    strategy TEXT NOT NULL,
    regime TEXT NOT NULL,
    symbol TEXT,
    pnl REAL,
    win INTEGER,
    meta_json TEXT
);
CREATE TABLE IF NOT EXISTS learning_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    suggestions_json TEXT NOT NULL,
    applied INTEGER DEFAULT 0,
    notes TEXT
);
"""


def _db(path: Any = None):
    from helix_v1.db import HelixDB

    return HelixDB(path) if path else HelixDB()


def ensure_learning_schema(db_path: Any = None) -> bool:
    try:
        db = _db(db_path)
        with db.conn() as conn:
            conn.executescript(_LEARNING_SCHEMA)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("learning schema failed: %s", type(exc).__name__)
        return False


@dataclass
class Outcome:
    strategy: str
    regime: str
    pnl: float
    symbol: str = ""
    win: bool | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def record_outcome(
    strategy: str,
    regime: str,
    pnl: float,
    *,
    symbol: str = "",
    win: bool | None = None,
    meta: dict[str, Any] | None = None,
    db_path: Any = None,
) -> int | None:
    if not ensure_learning_schema(db_path):
        return None
    win_i = (1 if win else 0) if win is not None else (1 if pnl > 0 else (0 if pnl < 0 else -1))
    try:
        db = _db(db_path)
        with db.conn() as conn:
            cur = conn.execute(
                """INSERT INTO learning_outcomes
                   (ts, strategy, regime, symbol, pnl, win, meta_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    strategy,
                    regime,
                    symbol,
                    float(pnl),
                    win_i,
                    json.dumps(meta or {}),
                ),
            )
            return int(cur.lastrowid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_outcome failed: %s", type(exc).__name__)
        return None


def load_outcomes(db_path: Any = None, limit: int = 5000) -> list[dict[str, Any]]:
    if not ensure_learning_schema(db_path):
        return []
    db = _db(db_path)
    with db.conn() as conn:
        rows = conn.execute(
            """SELECT strategy, regime, symbol, pnl, win, meta_json, ts
               FROM learning_outcomes ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [
        {
            "strategy": r["strategy"],
            "regime": r["regime"],
            "symbol": r["symbol"],
            "pnl": r["pnl"],
            "win": r["win"],
            "meta_json": r["meta_json"],
            "ts": r["ts"],
        }
        for r in rows
    ]


@dataclass
class WeightSuggestion:
    by_regime: dict[str, dict[str, float]]
    global_weights: dict[str, float]
    sample_sizes: dict[str, int]
    notes: str = "Suggestions only — do not auto-apply to live."

    def to_dict(self) -> dict[str, Any]:
        return {
            "by_regime": self.by_regime,
            "global_weights": self.global_weights,
            "sample_sizes": self.sample_sizes,
            "notes": self.notes,
            "auto_apply": False,
        }


def suggest_weights(
    outcomes: list[dict[str, Any]] | None = None,
    *,
    db_path: Any = None,
    min_samples: int = 5,
) -> WeightSuggestion:
    rows = outcomes if outcomes is not None else load_outcomes(db_path)
    global_pnls: dict[str, list[float]] = defaultdict(list)
    regime_pnls: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        strat = str(r.get("strategy") or "unknown")
        reg = str(r.get("regime") or "uncertain")
        pnl = float(r.get("pnl") or 0.0)
        global_pnls[strat].append(pnl)
        regime_pnls[reg][strat].append(pnl)

    def _weights(bucket: dict[str, list[float]]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for k, vals in bucket.items():
            if len(vals) < min_samples:
                continue
            avg = sum(vals) / len(vals)
            scores[k] = max(avg, 0.0) + 0.05
        total = sum(scores.values()) or 1.0
        return {k: round(v / total, 4) for k, v in scores.items()}

    by_regime = {reg: w for reg, strats in regime_pnls.items() if (w := _weights(strats))}
    return WeightSuggestion(
        by_regime=by_regime,
        global_weights=_weights(global_pnls),
        sample_sizes={k: len(v) for k, v in global_pnls.items()},
    )


def write_suggestions(
    suggestion: WeightSuggestion | None = None,
    *,
    db_path: Any = None,
    notes: str = "",
) -> int | None:
    sug = suggestion or suggest_weights(db_path=db_path)
    if not ensure_learning_schema(db_path):
        return None
    try:
        db = _db(db_path)
        with db.conn() as conn:
            cur = conn.execute(
                """INSERT INTO learning_suggestions (ts, suggestions_json, applied, notes)
                   VALUES (?, ?, 0, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(sug.to_dict()),
                    notes or sug.notes,
                ),
            )
            return int(cur.lastrowid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("write_suggestions failed: %s", type(exc).__name__)
        return None
