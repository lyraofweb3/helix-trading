from helix_v1.risk_engine import AccountState, ProposedOrder, RiskEngine, max_spread_for_symbol


def test_max_spread_commodity_wider_than_fx():
    assert max_spread_for_symbol("EURUSD") == 25
    assert max_spread_for_symbol("XAUUSD") >= 80
    assert max_spread_for_symbol("XAGUSD") >= 80
    assert max_spread_for_symbol("USOIL") >= 40
    assert max_spread_for_symbol("USOILm") >= 40


def test_oil_stub_spread_passes_gate():
    eng = RiskEngine()
    acct = AccountState(equity=50, balance=50)
    v = eng.check(
        acct,
        ProposedOrder(symbol="USOIL", action="buy", risk_pct=0.5, lots=0.01, rr=1.5, spread_points=40),
    )
    assert v.approved, v.reasons


def test_gold_stub_spread_passes_gate():
    eng = RiskEngine()
    acct = AccountState(equity=50, balance=50)
    v = eng.check(
        acct,
        ProposedOrder(symbol="XAUUSD", action="buy", risk_pct=0.5, lots=0.01, rr=1.5, spread_points=80),
    )
    assert v.approved, v.reasons


def test_fx_still_blocked_when_wide():
    eng = RiskEngine()
    acct = AccountState(equity=50, balance=50)
    v = eng.check(
        acct,
        ProposedOrder(symbol="EURUSD", action="buy", risk_pct=0.5, lots=0.01, rr=1.5, spread_points=40),
    )
    assert not v.approved
    assert v.code == "SPREAD"
