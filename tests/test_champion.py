
from helix_v1.champion import rank_score, enrich_scan_row


def test_rank_score_prefers_valid_buy():
    weak = {"score": 0.4, "confluence": 2, "idea_odds": 50, "state": "WATCH", "action": "hold"}
    strong = {
        "score": 0.8,
        "confluence": 5,
        "idea_odds": 70,
        "state": "VALID_SETUP",
        "action": "buy",
        "regime": {"regime": "strong_trend"},
    }
    assert rank_score(strong) > rank_score(weak)


def test_enrich_adds_champion_score():
    row = {
        "symbol": "EURUSD",
        "score": 0.7,
        "confluence": 4,
        "state": "VALID_SETUP",
        "action": "buy",
        "regime": {"regime": "strong_trend"},
    }
    snap = {
        "symbol": "EURUSD",
        "ema_fast": 1.105,
        "ema_slow": 1.10,
        "rsi": 58,
        "atr_points": 90,
        "last_close": 1.104,
        "structure": {"order_flow_heuristic": "bullish", "premium_discount": "discount", "pdh": 1.10},
        "mtf": {"alignment": "aligned", "htf_bias": "bullish"},
    }
    out = enrich_scan_row(row, snap)
    assert "champion_score" in out
    assert out["champion_score"] > 0
