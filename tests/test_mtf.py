
from helix_v1.mtf import TFSnapshot, analyze_tf_bars, fuse_mtf


def test_analyze_tf_bullish_stack():
    # rising closes
    closes = [1.0 + i * 0.001 for i in range(80)]
    highs = [c + 0.0005 for c in closes]
    lows = [c - 0.0005 for c in closes]
    opens = closes[:]
    snap = analyze_tf_bars("1H", opens, highs, lows, closes)
    assert snap.available
    assert snap.bias in {"bullish", "neutral", "bearish"}


def test_fuse_mtf_aligned():
    frames = {
        "1D": TFSnapshot("1D", "bullish", 0.8),
        "4H": TFSnapshot("4H", "bullish", 0.7),
        "1H": TFSnapshot("1H", "bullish", 0.75),
        "15m": TFSnapshot("15m", "bullish", 0.6),
        "5m": TFSnapshot("5m", "bullish", 0.55),
    }
    r = fuse_mtf(frames)
    assert r.alignment == "aligned"
    assert r.htf_bias == "bullish"
    assert r.continuation_probability > r.reversal_probability


def test_fuse_mtf_conflict():
    frames = {
        "1D": TFSnapshot("1D", "bullish", 0.8),
        "4H": TFSnapshot("4H", "bullish", 0.7),
        "1H": TFSnapshot("1H", "bullish", 0.7),
        "15m": TFSnapshot("15m", "bearish", 0.7),
        "5m": TFSnapshot("5m", "bearish", 0.65),
    }
    r = fuse_mtf(frames)
    assert r.alignment == "conflicting"
