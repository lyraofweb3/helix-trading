"""Shared trade-decision schema and prompt for HELIX LLM clients."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

SYSTEM_PROMPT = """You are HELIX, an expert forex decision assistant.
Rules:
- Be conservative. Prefer action "hold" when the picture is unclear or news is conflicting.
- Never suggest martingale, doubling down, or averaging into losers.
- Respect risk: small size mindset, always imply a stop; never "no stop".
- Forex majors only unless the snapshot names another symbol.
- Output ONLY valid JSON matching the schema — no markdown fences, no prose outside JSON.
Schema:
{
  "action": "buy" | "sell" | "hold",
  "symbol": "EURUSD" or other major,
  "confidence": number 0.0-1.0,
  "rationale": "short reason",
  "stop_hint": "optional SL distance/level hint or null",
  "take_hint": "optional TP distance/level hint or null"
}
If holding, still set symbol to the primary pair you considered.
"""


class TradeDecision(BaseModel):
    action: str
    symbol: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    stop_hint: str | None = None
    take_hint: str | None = None

    @field_validator("action")
    @classmethod
    def _action_ok(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"buy", "sell", "hold"}:
            raise ValueError(f"invalid action: {v}")
        return v

    @field_validator("symbol")
    @classmethod
    def _symbol_ok(cls, v: str) -> str:
        return v.strip().upper()


def extract_json(text: str) -> dict[str, Any]:
    """Parse JSON from model text; tolerate optional markdown fences."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        return json.loads(m.group(1).strip())
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group(0))
    raise ValueError("model response did not contain JSON")


# Back-compat alias used by older call sites
_extract_json = extract_json
