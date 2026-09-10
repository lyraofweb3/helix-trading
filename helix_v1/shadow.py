"""Shadow decision logging + optional Grok fetch (fail-soft, credit-safe)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def maybe_fetch_grok_decision(
    symbol: str,
    snapshot: dict[str, Any],
    headlines: list[Any] | None = None,
) -> dict[str, Any] | None:
    """Call LLM failover for a Grok (or backup) decision. Fail soft → None."""
    try:
        from helix.brain import _decide_with_failover

        decision, used_client, provider = _decide_with_failover(
            symbol,
            snapshot,
            list(headlines or snapshot.get("headlines") or []),
        )
        action = str(getattr(decision, "action", "hold") or "hold").lower()
        side = action if action in {"buy", "sell"} else "flat"
        return {
            "available": True,
            "side": side,
            "action": action,
            "confidence": float(getattr(decision, "confidence", 0.0) or 0.0),
            "rationale": str(getattr(decision, "rationale", "") or ""),
            "provider": provider,
            "model": getattr(used_client, "model", None),
            "stop_hint": getattr(decision, "stop_hint", None),
            "take_hint": getattr(decision, "take_hint", None),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Grok shadow/vote fetch failed: %s", type(exc).__name__)
        return None


def log_shadow_decision(
    *,
    symbol: str,
    quant_action: str | None = None,
    quant_confidence: float | None = None,
    quant_state: str | None = None,
    grok: dict[str, Any] | None = None,
    final_action: str | None = None,
    risk_veto: str | None = None,
    champion_score: float | None = None,
    llm_vote: bool | int | None = None,
    shadow_only: bool | int | None = None,
    payload: dict[str, Any] | None = None,
    db: Any | None = None,
) -> int | None:
    """Persist quant vs Grok comparison. Always fail-soft; table always writable."""
    try:
        from helix_v1.db import HelixDB, get_db

        database: HelixDB = db or get_db()
        grok = grok or {}
        grok_action = None
        grok_confidence = None
        grok_provider = None
        if grok.get("available"):
            grok_action = str(grok.get("action") or grok.get("side") or "") or None
            try:
                grok_confidence = float(grok.get("confidence")) if grok.get("confidence") is not None else None
            except (TypeError, ValueError):
                grok_confidence = None
            grok_provider = grok.get("provider")

        agree: int | None = None
        if quant_action and grok_action:
            qa = str(quant_action).lower()
            ga = str(grok_action).lower()
            # normalize flat/hold
            if qa in {"hold", "flat"}:
                qa = "hold"
            if ga in {"hold", "flat"}:
                ga = "hold"
            agree = 1 if qa == ga else 0

        llm_i = None if llm_vote is None else (1 if llm_vote else 0)
        shadow_i = None if shadow_only is None else (1 if shadow_only else 0)

        return database.insert_shadow_decision(
            symbol=symbol,
            quant_action=quant_action,
            quant_confidence=quant_confidence,
            quant_state=quant_state,
            grok_action=grok_action,
            grok_confidence=grok_confidence,
            grok_provider=grok_provider,
            agree=agree,
            final_action=final_action,
            risk_veto=risk_veto,
            champion_score=champion_score,
            llm_vote=llm_i,
            shadow_only=shadow_i,
            payload=payload,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("shadow_decision log failed: %s", type(exc).__name__)
        return None
