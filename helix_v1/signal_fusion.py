"""Fuse strategy votes + playbook confluence into HELIX confidence / state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from helix_v1.regime import RegimeResult
from helix_v1.strategies.base import StrategySignal


class FusionState(str, Enum):
    NO_TRADE = "NO_TRADE"
    WATCH = "WATCH"
    SETUP_FORMING = "SETUP_FORMING"
    VALID_SETUP = "VALID_SETUP"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    POSITION_MGMT = "POSITION_MGMT"
    EXIT = "EXIT"


# Playbook-style confluence checklist keys (score ≥3 required for VALID+)
CONFLUENCE_KEYS = (
    "htf_bias",
    "order_flow",
    "location",  # discount buy / premium sell
    "clear_dol",
    "session_ok",
    "news_clear",
    "ema_structure",
    "atr_regime_ok",
    "mtf_aligned",
    "mtf_htf_bias",
    "holly_agree",  # Trade Ideas Holly AI agrees with side
    "npfx_rsi_ok",  # NetProfitFX-style RSI timing
    "npfx_ema20_50",  # EMA 20/50 agreement (uses ema21/50 when present)
)


@dataclass
class FusionResult:
    state: FusionState
    action: str  # buy | sell | hold | close
    helix_confidence_score: float  # 0..1  HELIX_CONFIDENCE_SCORE
    confluence_count: int
    confluence_flags: dict[str, bool]
    buy_score: float
    sell_score: float
    votes: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "action": self.action,
            "HELIX_CONFIDENCE_SCORE": round(self.helix_confidence_score, 4),
            "confluence_count": self.confluence_count,
            "confluence_flags": dict(self.confluence_flags),
            "buy_score": round(self.buy_score, 4),
            "sell_score": round(self.sell_score, 4),
            "votes": list(self.votes),
            "rationale": self.rationale,
        }


def _confluence_flags(
    snapshot: dict[str, Any],
    structure: dict[str, Any] | None,
    regime: RegimeResult,
    side: str,
) -> dict[str, bool]:
    struct = structure or snapshot.get("structure") or {}
    of = struct.get("order_flow_heuristic")
    zone = struct.get("premium_discount")
    rsi = snapshot.get("rsi")
    atr = snapshot.get("atr_points")
    headlines = snapshot.get("headlines") or []

    bias = getattr(regime, "direction", None) or getattr(regime, "trend_bias", "neutral")
    htf = bias == ("bullish" if side == "buy" else "bearish") or regime.regime in {
        "strong_trend",
        "weak_trend",
        "breakout",
    }
    of_ok = (side == "buy" and of == "bullish") or (side == "sell" and of == "bearish")
    loc_ok = (side == "buy" and zone == "discount") or (side == "sell" and zone == "premium")
    dol = bool(struct.get("pdh") or struct.get("pdl") or (struct.get("fvg_hint") or {}).get("present"))
    # Session: prefer not off-hours — rough via as_of handled in session strategy; here true if price present
    session_ok = snapshot.get("last_close") is not None and snapshot.get("bid") is not None
    news_clear = True
    if isinstance(headlines, list) and len(headlines) > 8:
        # Many headlines may imply event risk — soft flag only if conflict markers present
        blob = " ".join(
            str((h.get("title") if isinstance(h, dict) else h) or "") for h in headlines
        ).lower()
        if "fed" in blob and ("decision" in blob or "fomc" in blob):
            news_clear = False
    ema_ok = False
    ef, es = snapshot.get("ema_fast"), snapshot.get("ema_slow")
    try:
        if ef is not None and es is not None:
            ema_ok = (side == "buy" and float(ef) >= float(es)) or (
                side == "sell" and float(ef) <= float(es)
            )
    except (TypeError, ValueError):
        ema_ok = False
    atr_ok = atr is None or (isinstance(atr, (int, float)) and 5 < float(atr) < 500)
    if regime.regime == "high_vol":
        atr_ok = False

    mtf = snapshot.get("mtf") or {}
    mtf_aligned = str(mtf.get("alignment") or "") == "aligned"
    mtf_htf = str(mtf.get("htf_bias") or "")
    mtf_htf_ok = (side == "buy" and mtf_htf == "bullish") or (side == "sell" and mtf_htf == "bearish")

    # NPFX paraphrased: RSI timing + EMA20/50 (HELIX ema21/ema50 or ema_fast/slow)
    npfx_rsi = False
    try:
        if rsi is not None:
            rv = float(rsi)
            if side == "buy" and 30 <= rv <= 55:
                npfx_rsi = True
            elif side == "sell" and 45 <= rv <= 70:
                npfx_rsi = True
    except (TypeError, ValueError):
        npfx_rsi = False
    npfx_ema = False
    e21 = snapshot.get("ema21", snapshot.get("ema_fast"))
    e50 = snapshot.get("ema50", snapshot.get("ema_slow"))
    last = snapshot.get("last_close")
    try:
        if e21 is not None and e50 is not None and last is not None:
            if side == "buy" and float(last) >= float(e21) and float(e21) >= float(e50) * 0.999:
                npfx_ema = True
            elif side == "sell" and float(last) <= float(e21) and float(e21) <= float(e50) * 1.001:
                npfx_ema = True
    except (TypeError, ValueError):
        npfx_ema = False

    return {
        "htf_bias": bool(htf and bias != "neutral"),
        "order_flow": bool(of_ok),
        "location": bool(loc_ok),
        "clear_dol": bool(dol),
        "session_ok": bool(session_ok),
        "news_clear": bool(news_clear),
        "ema_structure": bool(ema_ok),
        "atr_regime_ok": bool(atr_ok),
        "mtf_aligned": bool(mtf_aligned),
        "mtf_htf_bias": bool(mtf_htf_ok),
        "holly_agree": bool(
            (snapshot.get("holly") or {}).get("available")
            and str((snapshot.get("holly") or {}).get("side") or "") == side
            and float((snapshot.get("holly") or {}).get("confidence") or 0) >= 0.35
        ),
        "npfx_rsi_ok": bool(npfx_rsi),
        "npfx_ema20_50": bool(npfx_ema),
    }


def fuse_signals(
    signals: list[StrategySignal],
    snapshot: dict[str, Any],
    structure: dict[str, Any] | None,
    regime: RegimeResult,
    *,
    open_position: dict[str, Any] | None = None,
    min_confluence: int = 3,
) -> FusionResult:
    """
    Aggregate strategy votes → HELIX_CONFIDENCE_SCORE and FusionState.

    Playbook rule: buy/sell only if confluence_count ≥ min_confluence (default 3).
    """
    buy = 0.0
    sell = 0.0
    votes: list[dict[str, Any]] = []
    for s in signals:
        votes.append(s.to_dict())
        if s.side == "buy":
            buy += max(0.0, min(1.0, s.strength))
        elif s.side == "sell":
            sell += max(0.0, min(1.0, s.strength))

    n = max(len(signals), 1)
    buy_n = buy / n
    sell_n = sell / n

    # Position management / exit path
    if open_position:
        side_open = str(open_position.get("side") or open_position.get("action") or "").lower()
        if side_open in {"buy", "long"} and sell_n > buy_n + 0.15 and regime.regime in {
            "range",
            "uncertain",
            "high_vol",
        }:
            return FusionResult(
                state=FusionState.EXIT,
                action="close",
                helix_confidence_score=min(0.9, 0.5 + sell_n),
                confluence_count=0,
                confluence_flags={},
                buy_score=buy_n,
                sell_score=sell_n,
                votes=votes,
                rationale="open long thesis weakened — recommend exit",
            )
        if side_open in {"sell", "short"} and buy_n > sell_n + 0.15 and regime.regime in {
            "range",
            "uncertain",
            "high_vol",
        }:
            return FusionResult(
                state=FusionState.EXIT,
                action="close",
                helix_confidence_score=min(0.9, 0.5 + buy_n),
                confluence_count=0,
                confluence_flags={},
                buy_score=buy_n,
                sell_score=sell_n,
                votes=votes,
                rationale="open short thesis weakened — recommend exit",
            )
        if abs(buy_n - sell_n) < 0.1:
            return FusionResult(
                state=FusionState.POSITION_MGMT,
                action="hold",
                helix_confidence_score=0.45,
                confluence_count=0,
                confluence_flags={},
                buy_score=buy_n,
                sell_score=sell_n,
                votes=votes,
                rationale="manage open position — no flip",
            )

    preferred = "buy" if buy_n >= sell_n else "sell"
    edge = abs(buy_n - sell_n)
    if edge < 0.05 or max(buy_n, sell_n) < 0.08:
        preferred = "hold"

    flags = (
        _confluence_flags(snapshot, structure, regime, preferred)
        if preferred in {"buy", "sell"}
        else {k: False for k in CONFLUENCE_KEYS}
    )
    conf_count = sum(1 for v in flags.values() if v)

    # Confidence ≈ 0.35 + 0.1 * confluence (playbook) blended with vote edge
    raw = 0.35 + 0.1 * conf_count + 0.25 * edge + 0.2 * max(buy_n, sell_n)
    score = max(0.0, min(1.0, raw))
    # MTF alignment boost (additive HELIX 1.0+)
    mtf = snapshot.get("mtf") or {}
    if mtf.get("alignment") == "aligned" and preferred in {"buy", "sell"}:
        score = min(1.0, score + 0.08 * float(mtf.get("alignment_score") or 0.5))
    elif mtf.get("alignment") == "conflicting":
        score = max(0.0, score * 0.75)
    # Holly agree boost (Trade Ideas) — additive, never solo entry
    holly = snapshot.get("holly") or {}
    if (
        holly.get("available")
        and preferred in {"buy", "sell"}
        and holly.get("side") == preferred
        and float(holly.get("confidence") or 0) >= 0.35
    ):
        score = min(1.0, score + 0.06 * float(holly.get("confidence") or 0.5))

    if preferred == "hold":
        state = FusionState.WATCH if max(buy_n, sell_n) > 0.12 else FusionState.NO_TRADE
        return FusionResult(
            state=state,
            action="hold",
            helix_confidence_score=score * 0.6,
            confluence_count=conf_count,
            confluence_flags=flags,
            buy_score=buy_n,
            sell_score=sell_n,
            votes=votes,
            rationale="votes mixed or weak — hold",
        )

    if conf_count < min_confluence:
        state = FusionState.SETUP_FORMING if conf_count >= 2 else FusionState.WATCH
        return FusionResult(
            state=state,
            action="hold",
            helix_confidence_score=score * 0.75,
            confluence_count=conf_count,
            confluence_flags=flags,
            buy_score=buy_n,
            sell_score=sell_n,
            votes=votes,
            rationale=f"confluence {conf_count}<{min_confluence} — no entry yet ({preferred} bias)",
        )

    if conf_count >= 5 and score >= 0.75 and edge >= 0.12:
        state = FusionState.HIGH_CONFIDENCE
    else:
        state = FusionState.VALID_SETUP

    return FusionResult(
        state=state,
        action=preferred,
        helix_confidence_score=score,
        confluence_count=conf_count,
        confluence_flags=flags,
        buy_score=buy_n,
        sell_score=sell_n,
        votes=votes,
        rationale=f"{state.value}: {preferred} conf={conf_count} score={score:.2f}",
    )


# Compat aliases for pipeline / scanner
HelixState = FusionState


def fuse(*args, **kwargs):
    """Call fuse_signals with positional or scanner-style keywords."""
    if args:
        return fuse_signals(*args, **kwargs)
    signals = kwargs.pop("signals", None) or kwargs.pop("strategy_signals", None) or []
    snapshot = kwargs.pop("snapshot", {}) or {}
    structure = kwargs.pop("structure", None)
    if structure is None and isinstance(snapshot, dict):
        structure = snapshot.get("structure")
    regime = kwargs.pop("regime")
    return fuse_signals(list(signals), snapshot, structure, regime, **kwargs)


@property  # type: ignore[misc]
def _fr_direction(self):
    return self.action


@property  # type: ignore[misc]
def _fr_score(self):
    return self.helix_confidence_score


@property  # type: ignore[misc]
def _fr_reasons(self):
    return [self.rationale] if self.rationale else []


if not hasattr(FusionResult, "direction"):
    FusionResult.direction = _fr_direction  # type: ignore[attr-defined]
if not hasattr(FusionResult, "score"):
    FusionResult.score = _fr_score  # type: ignore[attr-defined]
if not hasattr(FusionResult, "reasons"):
    FusionResult.reasons = _fr_reasons  # type: ignore[attr-defined]
