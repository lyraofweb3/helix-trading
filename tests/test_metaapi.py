"""MetaAPI cloud executor — mocked HTTP."""

import os

import pytest

from helix_v1.modes import ModeGuard, TradingMode
from helix_v1.providers import metaapi as ma


def test_not_configured(monkeypatch):
    monkeypatch.delenv("METAAPI_TOKEN", raising=False)
    monkeypatch.delenv("METAAPI_ACCOUNT_ID", raising=False)
    assert ma.metaapi_configured() is False
    assert ma.place_market_order(symbol="EURUSD", side="buy", volume=0.01)["error"] == "not_configured"


def test_map_symbol_suffix(monkeypatch):
    monkeypatch.setenv("METAAPI_SYMBOL_SUFFIX", "m")
    assert ma.map_symbol("EURUSD") == "EURUSDm"
    assert ma.map_symbol("EURUSDm") == "EURUSDm"


def test_live_adapter_auto_metaapi(monkeypatch):
    monkeypatch.setenv("METAAPI_TOKEN", "tok")
    monkeypatch.setenv("METAAPI_ACCOUNT_ID", "acc")
    monkeypatch.setenv("HELIX_EXECUTOR", "auto")
    assert ModeGuard(TradingMode.LIVE).choose_adapter_name() == "metaapi"


def test_live_adapter_force_mt5(monkeypatch):
    monkeypatch.setenv("METAAPI_TOKEN", "tok")
    monkeypatch.setenv("METAAPI_ACCOUNT_ID", "acc")
    monkeypatch.setenv("HELIX_EXECUTOR", "mt5")
    assert ModeGuard(TradingMode.LIVE).choose_adapter_name() == "mt5"


def test_place_order_success(monkeypatch, httpx_mock=None):
    monkeypatch.setenv("METAAPI_TOKEN", "tok")
    monkeypatch.setenv("METAAPI_ACCOUNT_ID", "acc-id")
    monkeypatch.setenv("METAAPI_REGION", "new-york")

    class FakeResp:
        status_code = 200
        text = '{"numericCode":10009,"stringCode":"TRADE_RETCODE_DONE","orderId":"1"}'

        def json(self):
            return {"numericCode": 10009, "stringCode": "TRADE_RETCODE_DONE", "orderId": "1"}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            assert "trade" in url
            assert json["actionType"] == "ORDER_TYPE_BUY"
            assert json["symbol"] == "EURUSD"
            return FakeResp()

    monkeypatch.setattr(ma.httpx, "Client", FakeClient)
    out = ma.place_market_order(symbol="EURUSD", side="buy", volume=0.01, stop_loss=1.0, take_profit=1.1)
    assert out["ok"] is True
    assert out["order_id"] == "1"
