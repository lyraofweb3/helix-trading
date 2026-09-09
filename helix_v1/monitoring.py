"""HELIX 1.0 health checks: data freshness, kill switch, mode."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from helix.config import JOURNAL_PATH, LATEST_SIGNAL_PATH, SIGNALS_DIR
from helix_v1.modes import TradingMode, current_mode
from helix_v1.risk_engine import is_kill_switch_on, kill_switch_path, set_kill_switch


def mode_file_path() -> Path:
    env = os.environ.get("HELIX_MODE_PATH", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (SIGNALS_DIR / "mode.txt").resolve()


def get_mode() -> str:
    return current_mode().value


def set_mode(mode: str) -> str:
    m = (mode or "PAPER").strip().upper()
    try:
        TradingMode(m)
    except ValueError:
        m = "PAPER"
    path = mode_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(m + "\n", encoding="utf-8")
    os.environ["HELIX_MODE"] = m
    return m


def _file_age_seconds(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        return max(0.0, datetime.now(timezone.utc).timestamp() - path.stat().st_mtime)
    except OSError:
        return None


@dataclass
class HealthReport:
    ok: bool
    mode: str
    kill_switch: bool
    signal_age_sec: float | None
    journal_age_sec: float | None
    data_fresh: bool
    checks: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "kill_switch": self.kill_switch,
            "signal_age_sec": self.signal_age_sec,
            "journal_age_sec": self.journal_age_sec,
            "data_fresh": self.data_fresh,
            "checks": self.checks,
        }


def run_health_checks(*, max_signal_age_sec: float | None = None) -> HealthReport:
    max_age = max_signal_age_sec
    if max_age is None:
        max_age = float(os.environ.get("HELIX_MAX_SIGNAL_AGE_SEC", "900") or "900")
    mode = get_mode()
    kill = is_kill_switch_on()
    sig_age = _file_age_seconds(LATEST_SIGNAL_PATH)
    j_age = _file_age_seconds(JOURNAL_PATH)
    data_fresh = sig_age is not None and sig_age <= max_age
    checks = {
        "kill_switch_path": str(kill_switch_path()),
        "mode_path": str(mode_file_path()),
        "latest_signal": str(LATEST_SIGNAL_PATH),
        "max_signal_age_sec": max_age,
        "signals_dir_exists": SIGNALS_DIR.is_dir(),
    }
    ok = (not kill) and (data_fresh or mode in {"BACKTEST", "SAFE"})
    return HealthReport(
        ok=ok,
        mode=mode,
        kill_switch=kill,
        signal_age_sec=sig_age,
        journal_age_sec=j_age,
        data_fresh=data_fresh,
        checks=checks,
    )


def health_snapshot() -> dict[str, Any]:
    """Compact status used by /api/v1/status."""
    report = run_health_checks()
    reason = None
    p = kill_switch_path()
    if report.kill_switch and p.exists() and p.is_file():
        try:
            raw = p.read_text(encoding="utf-8").strip()
            try:
                reason = json.loads(raw).get("reason")
            except json.JSONDecodeError:
                reason = raw[:200] or "kill_switch"
        except OSError:
            reason = "kill_switch"
    out = report.to_dict()
    out.update(
        {
            "halt_reason": reason,
            "poll_seconds": int(os.environ.get("HELIX_POLL_SECONDS", "0") or 0),
            "ts": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
        }
    )
    return out


__all__ = [
    "HealthReport",
    "get_mode",
    "set_mode",
    "run_health_checks",
    "health_snapshot",
    "set_kill_switch",
    "is_kill_switch_on",
    "kill_switch_path",
]
