from helix_v1.idea_engine import generate_ideas, ideas_payload, to_holly_compatible


def _snap(**kw):
    base = {
        "symbol": "EURUSD",
        "ema_fast": 1.105,
        "ema_slow": 1.10,
        "ema_trend": 1.098,
        "rsi": 58,
        "atr_points": 90,
        "last_close": 1.104,
        "bid": 1.104,
        "structure": {
            "order_flow_heuristic": "bullish",
            "premium_discount": "discount",
            "pdh": 1.10,
            "pdl": 1.09,
        },
        "mtf": {"alignment": "aligned", "htf_bias": "bullish", "alignment_score": 0.8},
    }
    base.update(kw)
    return base


def test_generate_ranked_ideas():
    ideas = generate_ideas(_snap())
    assert len(ideas) >= 1
    assert ideas[0].odds >= ideas[-1].odds
    assert ideas[0].channel in {
        "momentum", "breakout", "mean_reversion", "volatility_expansion",
        "structure_flow", "session_liquidity",
    }


def test_holly_compatible_shape():
    v = to_holly_compatible(_snap())
    assert v["available"] is True
    assert v["side"] in {"buy", "sell"}
    assert 0 < v["confidence"] <= 1


def test_payload_has_channels():
    p = ideas_payload(_snap())
    assert p["engine"] == "helix_idea_engine"
    assert "momentum" in p["channels"]
