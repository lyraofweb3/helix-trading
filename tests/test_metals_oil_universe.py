from helix.config import SYMBOLS
from helix.prices import normalize_symbol, yahoo_ticker, point_size


def test_universe_has_gold_silver_oil():
    for s in ("XAUUSD", "XAGUSD", "USOIL"):
        assert s in SYMBOLS


def test_normalize_exness_suffixes():
    assert normalize_symbol("XAUUSDm") == "XAUUSD"
    assert normalize_symbol("XAGUSDm") == "XAGUSD"
    assert normalize_symbol("USOILm") == "USOIL"
    assert normalize_symbol("SILVER") == "XAGUSD"


def test_yahoo_tickers():
    assert yahoo_ticker("XAUUSD") == "GC=F"
    assert yahoo_ticker("XAGUSD") == "SI=F"
    assert yahoo_ticker("USOIL") == "CL=F"


def test_point_sizes():
    assert point_size("XAGUSD") == 0.001
