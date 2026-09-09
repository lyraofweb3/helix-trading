"""Portfolio exposure and correlation heat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from helix_v1.risk_engine import CORR_GROUPS, correlated_symbols


@dataclass
class ExposureReport:
    total_lots: float
    per_symbol: dict[str, float]
    net_usd_risk_proxy: float
    correlation_heat: dict[str, list[str]]
    hot_pairs: list[tuple[str, str]]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_lots": self.total_lots,
            "per_symbol": dict(self.per_symbol),
            "net_usd_risk_proxy": self.net_usd_risk_proxy,
            "correlation_heat": {k: list(v) for k, v in self.correlation_heat.items()},
            "hot_pairs": [list(p) for p in self.hot_pairs],
            "warnings": list(self.warnings),
        }


def _lots(pos: dict[str, Any]) -> float:
    try:
        return abs(float(pos.get("lots") or pos.get("volume") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _side_sign(pos: dict[str, Any]) -> int:
    s = str(pos.get("side") or pos.get("action") or "").lower()
    if s in {"buy", "long"}:
        return 1
    if s in {"sell", "short"}:
        return -1
    return 0


def compute_exposure(positions: list[dict[str, Any]] | None) -> ExposureReport:
    positions = positions or []
    per: dict[str, float] = {}
    total = 0.0
    signed: dict[str, float] = {}
    for p in positions:
        sym = str(p.get("symbol") or "").upper()
        if not sym:
            continue
        lot = _lots(p)
        per[sym] = per.get(sym, 0.0) + lot
        total += lot
        signed[sym] = signed.get(sym, 0.0) + lot * _side_sign(p)

    heat: dict[str, list[str]] = {}
    for name, group in CORR_GROUPS.items():
        present = sorted(s for s in signed if s in group and abs(signed[s]) > 0)
        if len(present) >= 2:
            heat[name] = present

    hot_pairs: list[tuple[str, str]] = []
    syms = list(signed.keys())
    for i, a in enumerate(syms):
        corr = correlated_symbols(a)
        for b in syms[i + 1 :]:
            if b in corr:
                hot_pairs.append((a, b))

    warnings: list[str] = []
    # Classic: EURUSD + GBPUSD same direction = USD short stack
    if "EURUSD" in signed and "GBPUSD" in signed:
        if signed["EURUSD"] * signed["GBPUSD"] > 0:
            warnings.append("EURUSD+GBPUSD same direction — stacked USD exposure")

    if "USOIL" in signed and "UKOIL" in signed:
        if signed["USOIL"] * signed["UKOIL"] > 0:
            warnings.append("USOIL+UKOIL same direction — energy heat")

    # Proxy risk: sum abs lots (not dollar-perfect)
    net_proxy = sum(abs(v) for v in signed.values())

    return ExposureReport(
        total_lots=total,
        per_symbol=per,
        net_usd_risk_proxy=net_proxy,
        correlation_heat=heat,
        hot_pairs=hot_pairs,
        warnings=warnings,
    )


def would_increase_heat(symbol: str, positions: list[dict[str, Any]] | None) -> bool:
    open_syms = {str(p.get("symbol") or "").upper() for p in (positions or [])}
    return bool(correlated_symbols(symbol) & open_syms)


def analyze(positions):
    return compute_exposure(positions)
