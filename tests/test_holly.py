
import json
from pathlib import Path

from helix_v1.providers.holly import (
    HollyIdea,
    ingest_payload,
    parse_idea,
    holly_vote_for_symbol,
)
from helix_v1.strategies.holly_ai import HollyAIStrategy
from helix_v1.regime import detect_regime
from helix_v1.signal_fusion import fuse_signals
from helix_v1.strategies import run_all


def test_parse_idea_aliases():
    idea = parse_idea({"ticker": "eurusd", "Type": "long", "odds": 72, "Alert": "Holly bounce"})
    assert idea is not None
    assert idea.symbol == "EURUSD"
    assert idea.side == "buy"
    assert 0.7 <= idea.confidence <= 0.75


def test_ingest_and_vote(tmp_path, monkeypatch):
    p = tmp_path / "holly.json"
    monkeypatch.setenv("HELIX_HOLLY_IDEAS_PATH", str(p))
    incoming = ingest_payload({"symbol": "EURUSD", "side": "buy", "confidence": 0.7, "thesis": "test"})
    assert len(incoming) == 1
    vote = holly_vote_for_symbol("EURUSD")
    assert vote["available"] is True
    assert vote["side"] == "buy"


def test_holly_strategy_vote():
    s = HollyAIStrategy()
    out = s.evaluate({"holly": {"available": True, "side": "sell", "confidence": 0.8, "thesis": "x"}}, None, None)
    assert out.direction == "sell"
    assert out.confidence > 0.4


def test_holly_in_fusion_confluence(tmp_path, monkeypatch):
    p = tmp_path / "holly.json"
    monkeypatch.setenv("HELIX_HOLLY_IDEAS_PATH", str(p))
    ingest_payload({"symbol": "EURUSD", "side": "buy", "confidence": 0.7, "thesis": "holly"})
    snap = {
        "symbol": "EURUSD",
        "ema_fast": 1.105,
        "ema_slow": 1.10,
        "ema_trend": 1.098,
        "rsi": 58,
        "atr_points": 40,
        "last_close": 1.104,
        "bid": 1.104,
        "ask": 1.1042,
        "spread_points": 10,
        "structure": {
            "order_flow_heuristic": "bullish",
            "premium_discount": "discount",
            "pdh": 1.11,
            "pdl": 1.09,
            "fvg_hint": {"present": True},
        },
        "mtf": {"alignment": "aligned", "htf_bias": "bullish", "alignment_score": 0.8},
        "holly": {"available": True, "side": "buy", "confidence": 0.7, "thesis": "holly"},
    }
    r = detect_regime(snap)
    sigs = run_all(snap, snap["structure"], r)
    assert any(s.name == "holly_ai" for s in sigs)
    f = fuse_signals(sigs, snap, snap["structure"], r)
    assert f.confluence_flags.get("holly_agree") is True
