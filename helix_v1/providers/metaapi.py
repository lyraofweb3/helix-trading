"""MetaAPI cloud MT5/MT4 executor — Railway trades without a home PC.

Additive to the HELIX.mq5 file bridge. Requires:
  METAAPI_TOKEN
  METAAPI_ACCOUNT_ID
Optional:
  METAAPI_REGION (default: new-york)
  METAAPI_SYMBOL_SUFFIX (e.g. m for Exness EURUSDm)
  HELIX_EXECUTOR=metaapi|mt5|auto
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_REGION_HOSTS = {
    "new-york": "mt-client-api-v1.new-york.agiliumtrade.ai",
    "london": "mt-client-api-v1.london.agiliumtrade.ai",
    "singapore": "mt-client-api-v1.singapore.agiliumtrade.ai",
    "tokyo": "mt-client-api-v1.tokyo.agiliumtrade.ai",
}


def metaapi_configured() -> bool:
    return bool(
        os.environ.get("METAAPI_TOKEN", "").strip()
        and os.environ.get("METAAPI_ACCOUNT_ID", "").strip()
    )


def _base_url() -> str:
    region = (os.environ.get("METAAPI_REGION") or "new-york").strip().lower()
    host = _REGION_HOSTS.get(region) or _REGION_HOSTS["new-york"]
    override = os.environ.get("METAAPI_BASE_URL", "").strip()
    if override:
        return override.rstrip("/")
    return f"https://{host}"


def map_symbol(symbol: str) -> str:
    """Map HELIX symbol to broker symbol (Exness often uses lowercase m suffix)."""
    sym = symbol.strip().upper()
    suffix = os.environ.get("METAAPI_SYMBOL_SUFFIX", "").strip()
    if not suffix:
        return sym
    if sym.lower().endswith(suffix.lower()):
        base = sym[: len(sym) - len(suffix)]
        return f"{base}{suffix}"
    return f"{sym}{suffix}"


def _headers() -> dict[str, str]:
    token = os.environ["METAAPI_TOKEN"].strip()
    return {
        "auth-token": token,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def account_information(timeout: float = 30.0) -> dict[str, Any]:
    if not metaapi_configured():
        return {"ok": False, "error": "not_configured"}
    account_id = os.environ["METAAPI_ACCOUNT_ID"].strip()
    url = f"{_base_url()}/users/current/accounts/{account_id}/account-information"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, headers=_headers())
            if r.status_code >= 400:
                return {"ok": False, "status": r.status_code, "body": r.text[:500]}
            return {"ok": True, "account": r.json()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("MetaAPI account-information failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}


def place_market_order(
    *,
    symbol: str,
    side: str,
    volume: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    comment: str = "HELIX",
    timeout: float = 45.0,
) -> dict[str, Any]:
    if not metaapi_configured():
        return {"ok": False, "error": "not_configured"}
    if side not in ("buy", "sell"):
        return {"ok": False, "error": "invalid_side"}
    if volume <= 0:
        return {"ok": False, "error": "invalid_volume"}

    account_id = os.environ["METAAPI_ACCOUNT_ID"].strip()
    broker_symbol = map_symbol(symbol)
    action = "ORDER_TYPE_BUY" if side == "buy" else "ORDER_TYPE_SELL"
    body: dict[str, Any] = {
        "actionType": action,
        "symbol": broker_symbol,
        "volume": float(volume),
        "comment": comment[:30],
    }
    if stop_loss is not None:
        body["stopLoss"] = float(stop_loss)
    if take_profit is not None:
        body["takeProfit"] = float(take_profit)

    url = f"{_base_url()}/users/current/accounts/{account_id}/trade"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers=_headers(), json=body)
            text = r.text[:1000]
            try:
                data = r.json()
            except Exception:  # noqa: BLE001
                data = {"raw": text}
            if r.status_code >= 400:
                logger.error("MetaAPI trade HTTP %s: %s", r.status_code, text)
                return {"ok": False, "status": r.status_code, "body": data, "symbol": broker_symbol}
            ok_codes = {10008, 10009, 10010, 0}
            numeric = data.get("numericCode") if isinstance(data, dict) else None
            string_code = str((data.get("stringCode") if isinstance(data, dict) else "") or "")
            if numeric is not None and numeric not in ok_codes and "DONE" not in string_code:
                return {"ok": False, "status": r.status_code, "body": data, "symbol": broker_symbol}
            return {
                "ok": True,
                "symbol": broker_symbol,
                "side": side,
                "volume": volume,
                "order_id": (data.get("orderId") if isinstance(data, dict) else None),
                "response": data,
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception("MetaAPI trade failed")
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:200]}


def close_symbol_positions(symbol: str, timeout: float = 45.0) -> dict[str, Any]:
    if not metaapi_configured():
        return {"ok": False, "error": "not_configured"}
    account_id = os.environ["METAAPI_ACCOUNT_ID"].strip()
    broker_symbol = map_symbol(symbol)
    body = {"actionType": "POSITIONS_CLOSE_SYMBOL", "symbol": broker_symbol}
    url = f"{_base_url()}/users/current/accounts/{account_id}/trade"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers=_headers(), json=body)
            try:
                data = r.json()
            except Exception:  # noqa: BLE001
                data = {"raw": r.text[:500]}
            return {
                "ok": r.status_code < 400,
                "status": r.status_code,
                "body": data,
                "symbol": broker_symbol,
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}
