"""Trading modes and hard mode guards."""

from __future__ import annotations

import os
from enum import Enum


class TradingMode(str, Enum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"
    SAFE = "SAFE"


# Alias used by execution.py
Mode = TradingMode


def current_mode() -> TradingMode:
    raw = (os.environ.get("HELIX_MODE") or "PAPER").strip().upper()
    try:
        return TradingMode(raw)
    except ValueError:
        return TradingMode.PAPER


class ModeGuard:
    """Blocks live order paths unless mode is LIVE and kill switch is off."""

    def __init__(self, mode: TradingMode | Mode | str | None = None) -> None:
        if mode is None:
            self.mode = current_mode()
        elif isinstance(mode, TradingMode):
            self.mode = mode
        else:
            try:
                self.mode = TradingMode(str(mode).strip().upper())
            except ValueError:
                self.mode = TradingMode.PAPER

    @property
    def allows_broker_orders(self) -> bool:
        return self.mode is TradingMode.LIVE

    @property
    def allows_paper_fills(self) -> bool:
        return self.mode in (TradingMode.PAPER, TradingMode.LIVE, TradingMode.SAFE)

    @property
    def is_safe(self) -> bool:
        return self.mode is TradingMode.SAFE

    def assert_can_send_live(self) -> None:
        if not self.allows_broker_orders:
            raise PermissionError(f"Live orders blocked in mode={self.mode.value}")

    def assert_can_submit_live(self) -> None:
        """Used by Mt5BridgeAdapter — only LIVE may hit broker path."""
        self.assert_can_send_live()

    def choose_adapter_name(self) -> str:
        if self.mode is TradingMode.LIVE:
            return "mt5"
        if self.mode is TradingMode.BACKTEST:
            return "backtest"
        return "paper"
