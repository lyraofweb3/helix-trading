from helix_v1.backtest import CostModel
from helix_v1.performance import compute_metrics, TradeRecord


def test_cost_model_buy_worse_than_mid():
    c = CostModel(spread_points=10, slippage_points=2, point=0.00001)
    mid = 1.10000
    assert c.buy_entry(mid) > mid
    assert c.sell_entry(mid) < mid
    assert c.buy_exit(mid) < mid


def test_expectancy_sign():
    m = compute_metrics([TradeRecord(pnl=2), TradeRecord(pnl=2), TradeRecord(pnl=-1)])
    assert m.expectancy > 0
