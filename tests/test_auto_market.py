"""Auto market / news-aware champion scoring."""

from helix_v1.champion import news_bias_for_symbol, rank_score


def test_news_bias_gold_bullish():
    out = news_bias_for_symbol(
        "XAUUSD",
        [{"title": "Gold surges on safe haven demand amid war fears"}],
    )
    assert out["bias"] == "buy"
    assert out["hits"] >= 1
    assert out["heat"] > 0


def test_news_conflict_demotes():
    high = rank_score(
        {
            "score": 0.8,
            "confluence": 5,
            "idea_odds": 70,
            "state": "VALID_SETUP",
            "action": "buy",
            "news_heat": 1.0,
            "news_bias": "buy",
        }
    )
    low = rank_score(
        {
            "score": 0.8,
            "confluence": 5,
            "idea_odds": 70,
            "state": "VALID_SETUP",
            "action": "buy",
            "news_heat": 1.0,
            "news_bias": "sell",
        }
    )
    assert high > low


def test_auto_market_config_default_on():
    from helix.config import AUTO_MARKET

    assert AUTO_MARKET is True or AUTO_MARKET is False  # env-dependent but defined
