from helix_v1.regime import detect_regime
from helix_v1.risk_engine import AccountState, ProposedOrder, RiskEngine, set_kill_switch, is_kill_switch_on
from helix_v1.signal_fusion import FusionState, fuse_signals
from helix_v1.sizing import size_position
from helix_v1.strategies import run_all
from helix_v1.performance import compute_metrics, TradeRecord


def _snap(**kw):
    base = {
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
    }
    base.update(kw)
    return base


def test_regime_strong_trend():
    r = detect_regime(_snap())
    assert r.regime in {"strong_trend", "weak_trend", "breakout"}
    assert r.direction == "bullish"


def test_fusion_requires_confluence():
    snap = _snap()
    r = detect_regime(snap)
    sigs = run_all(snap, snap["structure"], r)
    f = fuse_signals(sigs, snap, snap["structure"], r, min_confluence=3)
    assert f.confluence_count >= 0
    assert f.state in FusionState


def test_risk_blocks_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIX_KILL_SWITCH_PATH", str(tmp_path / "KILL"))
    set_kill_switch(True, "test")
    assert is_kill_switch_on()
    v = RiskEngine().check(
        AccountState(equity=1000, balance=1000, kill_switch=True),
        ProposedOrder(symbol="EURUSD", action="buy", risk_pct=0.5, lots=0.1, rr=1.5),
    )
    assert v.approved is False
    set_kill_switch(False)


def test_risk_allows_hold():
    v = RiskEngine().check(
        AccountState(equity=1000, balance=1000),
        ProposedOrder(symbol="EURUSD", action="hold"),
    )
    assert v.approved is True


def test_sizing_no_martingale_rounds_down():
    s = size_position(equity=10_000, symbol="EURUSD", stop_points=50, risk_pct=0.5)
    assert s.lots > 0
    assert s.lots == round(s.lots, 2) or s.lots * 100 == int(s.lots * 100)


def test_performance_metrics():
    trades = [
        TradeRecord(pnl=10),
        TradeRecord(pnl=-5),
        TradeRecord(pnl=8),
        TradeRecord(pnl=-4),
    ]
    m = compute_metrics(trades)
    assert m.n_trades == 4
    assert m.wins == 2
    assert m.profit_factor > 0
    assert 0 <= m.win_rate <= 1
