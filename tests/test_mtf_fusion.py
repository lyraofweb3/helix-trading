
from helix_v1.regime import detect_regime
from helix_v1.signal_fusion import fuse_signals
from helix_v1.strategies import run_all


def test_mtf_flags_in_confluence():
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
    }
    r = detect_regime(snap)
    sigs = run_all(snap, snap["structure"], r)
    f = fuse_signals(sigs, snap, snap["structure"], r)
    assert "mtf_aligned" in f.confluence_flags
    assert f.confluence_flags["mtf_aligned"] is True
