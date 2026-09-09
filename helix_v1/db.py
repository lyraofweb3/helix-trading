"""SQLite persistence for HELIX 1.0."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT,
  strategy TEXT,
  regime TEXT,
  confidence REAL,
  entry REAL,
  exit REAL,
  sl REAL,
  tp REAL,
  lots REAL,
  pnl REAL,
  mode TEXT,
  meta_json TEXT
);
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  symbol TEXT NOT NULL,
  order_type TEXT,
  side TEXT,
  lots REAL,
  price REAL,
  status TEXT,
  mode TEXT,
  meta_json TEXT
);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  symbol TEXT NOT NULL,
  state TEXT,
  score REAL,
  action TEXT,
  payload_json TEXT
);
CREATE TABLE IF NOT EXISTS ai_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  symbol TEXT NOT NULL,
  action TEXT,
  confidence REAL,
  rationale TEXT,
  provider TEXT,
  payload_json TEXT
);
CREATE TABLE IF NOT EXISTS regimes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  symbol TEXT NOT NULL,
  regime TEXT,
  strength REAL,
  payload_json TEXT
);
CREATE TABLE IF NOT EXISTS news_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  title TEXT,
  source TEXT,
  impact TEXT,
  payload_json TEXT
);
CREATE TABLE IF NOT EXISTS backtests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  symbol TEXT,
  params_json TEXT,
  metrics_json TEXT
);
CREATE TABLE IF NOT EXISTS system_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  level TEXT,
  kind TEXT,
  message TEXT,
  payload_json TEXT
);
CREATE TABLE IF NOT EXISTS performance_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  win_rate REAL,
  profit_factor REAL,
  expectancy REAL,
  max_dd REAL,
  payload_json TEXT
);
CREATE TABLE IF NOT EXISTS learning_suggestions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  strategy TEXT,
  regime TEXT,
  suggestion TEXT,
  applied INTEGER DEFAULT 0,
  payload_json TEXT
);
"""


def default_db_path() -> Path:
    env = os.environ.get("HELIX_DB_PATH", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    signal = os.environ.get("SIGNAL_DIR", "").strip()
    if signal:
        return Path(signal).expanduser().resolve().parent / "helix.db"
    return Path(__file__).resolve().parent.parent / "data" / "helix.db"


class HelixDB:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = self._connect()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def insert_signal(self, symbol: str, state: str, score: float, action: str, payload: dict[str, Any]) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO signals (ts, symbol, state, score, action, payload_json) VALUES (?,?,?,?,?,?)",
                (self._now(), symbol, state, score, action, json.dumps(payload)),
            )
            return int(cur.lastrowid)

    def insert_ai_decision(self, symbol: str, action: str, confidence: float, rationale: str, provider: str, payload: dict[str, Any]) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO ai_decisions (ts, symbol, action, confidence, rationale, provider, payload_json) VALUES (?,?,?,?,?,?,?)",
                (self._now(), symbol, action, confidence, rationale, provider, json.dumps(payload)),
            )
            return int(cur.lastrowid)

    def insert_regime(self, symbol: str, regime: str, strength: float, payload: dict[str, Any]) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO regimes (ts, symbol, regime, strength, payload_json) VALUES (?,?,?,?,?)",
                (self._now(), symbol, regime, strength, json.dumps(payload)),
            )
            return int(cur.lastrowid)

    def insert_trade(self, row: dict[str, Any]) -> int:
        with self.conn() as c:
            cur = c.execute(
                """INSERT INTO trades (ts, symbol, side, strategy, regime, confidence, entry, exit, sl, tp, lots, pnl, mode, meta_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row.get("ts") or self._now(),
                    row["symbol"],
                    row.get("side"),
                    row.get("strategy"),
                    row.get("regime"),
                    row.get("confidence"),
                    row.get("entry"),
                    row.get("exit"),
                    row.get("sl"),
                    row.get("tp"),
                    row.get("lots"),
                    row.get("pnl"),
                    row.get("mode"),
                    json.dumps(row.get("meta") or {}),
                ),
            )
            return int(cur.lastrowid)

    def insert_order(self, row: dict[str, Any]) -> int:
        with self.conn() as c:
            cur = c.execute(
                """INSERT INTO orders (ts, symbol, order_type, side, lots, price, status, mode, meta_json)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    self._now(),
                    row["symbol"],
                    row.get("order_type"),
                    row.get("side"),
                    row.get("lots"),
                    row.get("price"),
                    row.get("status", "pending"),
                    row.get("mode"),
                    json.dumps(row.get("meta") or {}),
                ),
            )
            return int(cur.lastrowid)

    def insert_system_event(self, level: str, kind: str, message: str, payload: dict[str, Any] | None = None) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO system_events (ts, level, kind, message, payload_json) VALUES (?,?,?,?,?)",
                (self._now(), level, kind, message, json.dumps(payload or {})),
            )
            return int(cur.lastrowid)

    def insert_backtest(self, symbol: str, params: dict[str, Any], metrics: dict[str, Any]) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO backtests (ts, symbol, params_json, metrics_json) VALUES (?,?,?,?)",
                (self._now(), symbol, json.dumps(params), json.dumps(metrics)),
            )
            return int(cur.lastrowid)

    def insert_performance(self, metrics: dict[str, Any]) -> int:
        with self.conn() as c:
            cur = c.execute(
                """INSERT INTO performance_snapshots (ts, win_rate, profit_factor, expectancy, max_dd, payload_json)
                   VALUES (?,?,?,?,?,?)""",
                (
                    self._now(),
                    metrics.get("win_rate"),
                    metrics.get("profit_factor"),
                    metrics.get("expectancy"),
                    metrics.get("max_dd"),
                    json.dumps(metrics),
                ),
            )
            return int(cur.lastrowid)

    def latest_signal(self, symbol: str | None = None) -> dict[str, Any] | None:
        with self.conn() as c:
            if symbol:
                row = c.execute(
                    "SELECT * FROM signals WHERE symbol=? ORDER BY id DESC LIMIT 1", (symbol,)
                ).fetchone()
            else:
                row = c.execute("SELECT * FROM signals ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def list_trades(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]



# ---- module-level helpers (execution / adapters) ----
_DB: HelixDB | None = None


def get_db() -> HelixDB:
    global _DB
    if _DB is None:
        _DB = HelixDB()
    return _DB


def insert_order(
    *,
    symbol: str,
    action: str,
    lots: float | None = None,
    price: float | None = None,
    stop: float | None = None,
    take: float | None = None,
    status: str = "pending",
    mode: str | None = None,
    reason: str | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    meta = dict(meta or {})
    if reason:
        meta["reason"] = reason
    if stop is not None:
        meta["stop"] = stop
    if take is not None:
        meta["take"] = take
    return get_db().insert_order(
        {
            "symbol": symbol,
            "order_type": "market",
            "side": action,
            "lots": lots,
            "price": price,
            "status": status,
            "mode": mode,
            "meta": meta,
        }
    )


def insert_trade(
    *,
    symbol: str,
    side: str,
    lots: float | None = None,
    entry: float | None = None,
    exit: float | None = None,
    stop: float | None = None,
    take: float | None = None,
    mode: str | None = None,
    status: str | None = None,
    thesis: str | None = None,
    pnl: float | None = None,
    strategy: str | None = None,
    regime: str | None = None,
    confidence: float | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    meta = dict(meta or {})
    if status:
        meta["status"] = status
    if thesis:
        meta["thesis"] = thesis
    return get_db().insert_trade(
        {
            "symbol": symbol,
            "side": side,
            "strategy": strategy,
            "regime": regime,
            "confidence": confidence,
            "entry": entry,
            "exit": exit,
            "sl": stop,
            "tp": take,
            "lots": lots,
            "pnl": pnl,
            "mode": mode,
            "meta": meta,
        }
    )
