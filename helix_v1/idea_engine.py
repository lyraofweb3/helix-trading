"""HELIX Idea Engine — native Holly-class trade ideas (odds, channels, alerts).

This is HELIX's own implementation inspired by public AI-trade-idea product
capabilities (ranked ideas, odds-of-success style scores, multi-channel alerts).
It does NOT contain or reproduce Trade Ideas / Holly proprietary source code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


CHANNELS = (
    "momentum",
    "breakout",
    "mean_reversion",
    "volatility_expansion",
    "structure_flow",
    "session_liquidity",
)


@dataclass
class TradeIdea:
    symbol: str
    side: str  # buy | sell | flat
    odds: float  # 0..100 display-style odds of idea quality (not a guarantee)
    confidence: float  # 0..1
    channel: str
    thesis: str
    entry_zone: str = ""
    invalidation: str = ""
    risk_reward: float = 1.5
    rank_score: float = 0.0
    ts: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["odds_label"] = f"{self.odds:.0f}/100 idea-quality"
        return d


def _f(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _channel_momentum(snap: dict[str, Any]) -> TradeIdea | None:
    rsi = _f(snap.get("rsi"))
    ef, es = _f(snap.get("ema_fast")), _f(snap.get("ema_slow"))
    if rsi is None or ef is None or es is None:
        return None
    sym = str(snap.get("symbol") or "EURUSD")
    if ef > es and 52 <= rsi <= 68:
        odds = 55 + min(25, (rsi - 50) * 1.2)
        return TradeIdea(sym, "buy", odds, odds / 100, "momentum",
                         "Bullish momentum channel: EMA stack + RSI continuation zone",
                         entry_zone="pullback toward EMA fast", invalidation="close below EMA slow",
                         rank_score=odds, ts=_now())
    if ef < es and 32 <= rsi <= 48:
        odds = 55 + min(25, (50 - rsi) * 1.2)
        return TradeIdea(sym, "sell", odds, odds / 100, "momentum",
                         "Bearish momentum channel: EMA stack + RSI continuation zone",
                         entry_zone="rally toward EMA fast", invalidation="close above EMA slow",
                         rank_score=odds, ts=_now())
    return None


def _channel_breakout(snap: dict[str, Any]) -> TradeIdea | None:
    struct = snap.get("structure") or {}
    last = _f(snap.get("last_close") or snap.get("bid"))
    pdh = _f(struct.get("pdh") or struct.get("prev_day_high"))
    pdl = _f(struct.get("pdl") or struct.get("prev_day_low"))
    sym = str(snap.get("symbol") or "EURUSD")
    if last is not None and pdh is not None and last > pdh:
        odds = 62.0
        return TradeIdea(sym, "buy", odds, 0.62, "breakout",
                         "Breakout channel: price clearing PDH with follow-through bias",
                         entry_zone="retest of PDH", invalidation="close back inside prior day range",
                         rank_score=odds, ts=_now())
    if last is not None and pdl is not None and last < pdl:
        odds = 62.0
        return TradeIdea(sym, "sell", odds, 0.62, "breakout",
                         "Breakout channel: price breaking PDL with follow-through bias",
                         entry_zone="retest of PDL", invalidation="close back inside prior day range",
                         rank_score=odds, ts=_now())
    if struct.get("bos") or struct.get("break_of_structure"):
        bias = "buy" if (snap.get("ema_fast") or 0) > (snap.get("ema_slow") or 0) else "sell"
        return TradeIdea(sym, bias, 58.0, 0.58, "breakout",
                         "Structure breakout channel: BoS flagged",
                         rank_score=58, ts=_now())
    return None


def _channel_mean_reversion(snap: dict[str, Any]) -> TradeIdea | None:
    rsi = _f(snap.get("rsi"))
    struct = snap.get("structure") or {}
    loc = struct.get("premium_discount") or struct.get("location")
    sym = str(snap.get("symbol") or "EURUSD")
    if rsi is not None and rsi >= 72 and loc in ("premium", "above_eq", None):
        return TradeIdea(sym, "sell", 57.0, 0.57, "mean_reversion",
                         "Mean-reversion channel: stretched RSI in premium",
                         entry_zone="fade into premium", invalidation="impulsive continuation highs",
                         rank_score=57, ts=_now())
    if rsi is not None and rsi <= 28 and loc in ("discount", "below_eq", None):
        return TradeIdea(sym, "buy", 57.0, 0.57, "mean_reversion",
                         "Mean-reversion channel: stretched RSI in discount",
                         entry_zone="buy into discount", invalidation="impulsive continuation lows",
                         rank_score=57, ts=_now())
    return None


def _channel_vol_expansion(snap: dict[str, Any]) -> TradeIdea | None:
    atr = _f(snap.get("atr_points"))
    mtf = snap.get("mtf") or {}
    sym = str(snap.get("symbol") or "EURUSD")
    if atr is None:
        return None
    # High ATR + aligned MTF favors continuation ideas
    if atr >= 80 and mtf.get("alignment") == "aligned":
        side = "buy" if mtf.get("htf_bias") == "bullish" else "sell" if mtf.get("htf_bias") == "bearish" else "flat"
        if side == "flat":
            return None
        return TradeIdea(sym, side, 64.0, 0.64, "volatility_expansion",
                         "Volatility-expansion channel: elevated ATR with MTF alignment",
                         rank_score=64, ts=_now(), meta={"atr_points": atr})
    return None


def _channel_structure(snap: dict[str, Any]) -> TradeIdea | None:
    struct = snap.get("structure") or {}
    of = struct.get("order_flow_heuristic") or struct.get("order_flow") or struct.get("of")
    loc = struct.get("premium_discount") or struct.get("location")
    sym = str(snap.get("symbol") or "EURUSD")
    if of == "bullish" and loc in ("discount", "below_eq"):
        return TradeIdea(sym, "buy", 66.0, 0.66, "structure_flow",
                         "Structure/flow channel: bullish OF in discount",
                         entry_zone="discount demand", invalidation="OF flips bearish",
                         rank_score=66, ts=_now())
    if of == "bearish" and loc in ("premium", "above_eq"):
        return TradeIdea(sym, "sell", 66.0, 0.66, "structure_flow",
                         "Structure/flow channel: bearish OF in premium",
                         entry_zone="premium supply", invalidation="OF flips bullish",
                         rank_score=66, ts=_now())
    return None


def _channel_session(snap: dict[str, Any]) -> TradeIdea | None:
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    mtf = snap.get("mtf") or {}
    sym = str(snap.get("symbol") or "EURUSD")
    # London-NY overlap favor
    if 12 <= hour < 16 and mtf.get("htf_bias") in ("bullish", "bearish"):
        side = "buy" if mtf["htf_bias"] == "bullish" else "sell"
        return TradeIdea(sym, side, 60.0, 0.60, "session_liquidity",
                         "Session channel: London–NY overlap with HTF bias",
                         rank_score=60, ts=_now(), meta={"utc_hour": hour})
    return None


_GENERATORS: list[Callable[[dict[str, Any]], TradeIdea | None]] = [
    _channel_momentum,
    _channel_breakout,
    _channel_mean_reversion,
    _channel_vol_expansion,
    _channel_structure,
    _channel_session,
]


def generate_ideas(snapshot: dict[str, Any], *, min_odds: float = 55.0) -> list[TradeIdea]:
    ideas: list[TradeIdea] = []
    for gen in _GENERATORS:
        try:
            idea = gen(snapshot)
        except Exception:  # noqa: BLE001
            idea = None
        if idea and idea.side != "flat" and idea.odds >= min_odds:
            ideas.append(idea)
    ideas.sort(key=lambda i: i.rank_score, reverse=True)
    return ideas


def best_idea(snapshot: dict[str, Any]) -> TradeIdea | None:
    ideas = generate_ideas(snapshot)
    return ideas[0] if ideas else None


def ideas_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    ideas = generate_ideas(snapshot)
    top = ideas[0] if ideas else None
    return {
        "engine": "helix_idea_engine",
        "style": "holly_class_native",  # HELIX-built; not third-party source
        "count": len(ideas),
        "top": top.to_dict() if top else None,
        "ideas": [i.to_dict() for i in ideas],
        "channels": list(CHANNELS),
        "note": "Odds are idea-quality scores for ranking — not win-rate promises.",
    }


def to_holly_compatible(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Shape compatible with holly_vote_for_symbol / HollyAIStrategy."""
    top = best_idea(snapshot)
    if not top:
        return {"available": False, "side": "flat", "confidence": 0.0, "ideas": [], "source": "helix_idea_engine"}
    return {
        "available": True,
        "side": top.side,
        "confidence": top.confidence,
        "thesis": top.thesis,
        "ideas": [top.to_dict()],
        "source": "helix_idea_engine",
        "odds": top.odds,
        "channel": top.channel,
        "provider_configured": True,
        "file_path": "native",
    }
