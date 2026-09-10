"""Quant baseline + Grok fusion vote + shadow_decisions (unit, no network)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helix_v1.db import HelixDB
from helix_v1.regime import detect_regime
from helix_v1.signal_fusion import fuse_signals
from helix_v1.strategies.base import StrategySignal


def _bull_snap(**extra):
    snap = {
        "symbol": "EURUSD",
        "ema_fast": 1.105,
        "ema_slow": 1.10,
        "ema_trend": 1.098,
        "ema21": 1.104,
        "ema50": 1.10,
        "rsi": 48,
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
    }
    snap.update(extra)
    return snap


def test_fusion_grok_agree_boosts_confluence_and_score():
    snap = _bull_snap()
    regime = detect_regime(snap)
    # Strong buy strategy votes so preferred is buy
    signals = [
        StrategySignal(name="trend", direction="buy", score=0.9, confidence=0.9, reasons=["t"]),
        StrategySignal(name="momentum", direction="buy", score=0.8, confidence=0.85, reasons=["m"]),
        StrategySignal(name="session", direction="buy", score=0.7, confidence=0.8, reasons=["s"]),
    ]
    base = fuse_signals(signals, snap, snap["structure"], regime)
    assert base.action in {"buy", "hold"}  # may be hold if confluence gate, but flags matter

    snap_g = {
        **snap,
        "grok": {
            "available": True,
            "side": "buy",
            "confidence": 0.8,
            "vote": True,
            "provider": "xai",
        },
    }
    with_grok = fuse_signals(signals, snap_g, snap_g["structure"], regime)

    assert "grok_agree" in with_grok.confluence_flags
    assert with_grok.confluence_flags["grok_agree"] is True
    assert any(v.get("name") == "grok" for v in with_grok.votes)
    # Score path should be at least as high when grok agrees
    assert with_grok.helix_confidence_score >= base.helix_confidence_score - 1e-9
    # Confluence count should include grok_agree
    assert with_grok.confluence_count >= base.confluence_count


def test_fusion_shadow_only_vote_false_does_not_boost():
    snap = _bull_snap(
        grok={
            "available": True,
            "side": "buy",
            "confidence": 0.9,
            "vote": False,
            "shadow_only": True,
        }
    )
    regime = detect_regime(snap)
    signals = [
        StrategySignal(name="trend", direction="buy", score=0.9, confidence=0.9, reasons=[]),
    ]
    f = fuse_signals(signals, snap, snap["structure"], regime)
    assert f.confluence_flags.get("grok_agree") is False
    assert not any(v.get("name") == "grok" for v in f.votes)


def test_insert_shadow_decision_roundtrip(tmp_path: Path):
    db = HelixDB(tmp_path / "shadow_test.db")
    row_id = db.insert_shadow_decision(
        symbol="EURUSD",
        quant_action="buy",
        quant_confidence=0.72,
        quant_state="VALID_SETUP",
        grok_action="buy",
        grok_confidence=0.81,
        grok_provider="xai",
        agree=1,
        final_action="buy",
        risk_veto=None,
        champion_score=0.66,
        llm_vote=0,
        shadow_only=1,
        payload={"note": "unit"},
    )
    assert row_id >= 1
    with db.conn() as c:
        row = c.execute(
            "SELECT * FROM shadow_decisions WHERE id=?", (row_id,)
        ).fetchone()
    assert row is not None
    d = dict(row)
    assert d["symbol"] == "EURUSD"
    assert d["quant_action"] == "buy"
    assert d["grok_action"] == "buy"
    assert d["agree"] == 1
    assert d["shadow_only"] == 1
    assert d["llm_vote"] == 0
    assert "unit" in (d["payload_json"] or "")


def test_champion_cycle_llm_off_no_write_signal_override(monkeypatch):
    """HELIX_V1_LLM=0 → brain=quant; plan unchanged; no sole-decider override."""
    monkeypatch.setenv("HELIX_V1_LLM", "0")
    monkeypatch.setenv("HELIX_GROK_SHADOW", "0")

    fixed_plan = {
        "action": "buy",
        "symbol": "EURUSD",
        "confidence": 0.7,
        "rationale": "quant only",
        "meta": {"state": "VALID_SETUP", "risk": {"approved": True}},
    }
    fixed_result = {
        "plan": fixed_plan,
        "fusion": {"state": "VALID_SETUP", "HELIX_CONFIDENCE_SCORE": 0.7},
        "grok": None,
        "brain": "quant",
    }

    top = {
        "symbol": "EURUSD",
        "champion_score": 0.9,
        "confluence": 5,
        "state": "VALID_SETUP",
        "action": "buy",
        "score": 0.8,
        "idea_odds": 70,
    }

    decide_calls: list = []

    def boom_decide(*_a, **_k):
        decide_calls.append(True)
        raise AssertionError("_decide_with_failover must not be sole decider when LLM off")

    with (
        patch("helix_v1.champion.champion_scan", return_value=[top]),
        patch("helix_v1.champion.run_helix_cycle", return_value=fixed_result) as mock_cycle,
        patch("helix.brain._decide_with_failover", side_effect=boom_decide),
        patch("helix.brain.write_signal", side_effect=AssertionError("write_signal override forbidden")),
        patch("helix_v1.shadow.log_shadow_decision", return_value=1),
    ):
        from helix_v1.champion import run_champion_cycle

        out = run_champion_cycle(
            symbols=["EURUSD"],
            min_champion_score=0.5,
            min_confluence=3,
            require_valid_state=True,
        )

    assert out["acted"] is True
    assert out["brain"] == "quant"
    assert out["auto_market"] is True
    assert out["champion"] is True
    assert out["plan"] == fixed_plan
    assert out["plan"]["action"] == "buy"
    assert out["plan"]["rationale"] == "quant only"
    # Pipeline called with use_llm=False
    assert mock_cycle.called
    kwargs = mock_cycle.call_args.kwargs
    assert kwargs.get("use_llm") is False
    assert decide_calls == []


def test_log_shadow_decision_fail_soft(tmp_path: Path):
    from helix_v1.shadow import log_shadow_decision

    db = HelixDB(tmp_path / "shadow2.db")
    rid = log_shadow_decision(
        symbol="XAUUSD",
        quant_action="sell",
        quant_confidence=0.55,
        quant_state="WATCH",
        grok={"available": True, "action": "buy", "side": "buy", "confidence": 0.4, "provider": "openai"},
        final_action="hold",
        llm_vote=False,
        shadow_only=True,
        db=db,
    )
    assert rid is not None
    with db.conn() as c:
        row = dict(c.execute("SELECT agree, grok_action FROM shadow_decisions WHERE id=?", (rid,)).fetchone())
    assert row["agree"] == 0
    assert row["grok_action"] == "buy"
