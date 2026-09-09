"""OpenAI chat-completions client for HELIX trading decisions (backup provider)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from helix.config import (
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_TIMEOUT_SEC,
    get_openai_api_key,
)
from helix.decision import SYSTEM_PROMPT, TradeDecision, extract_json

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Thin chat-completions wrapper. Mirrors XAIClient.analyze API."""

    def __init__(
        self,
        base_url: str = OPENAI_BASE_URL,
        model: str = OPENAI_MODEL,
        temperature: float = OPENAI_TEMPERATURE,
        timeout: float = OPENAI_TIMEOUT_SEC,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    def analyze(
        self,
        market_snapshot: dict[str, Any],
        headlines: list[dict[str, Any]],
    ) -> TradeDecision:
        """Ask OpenAI for a structured buy|sell|hold decision."""
        api_key = get_openai_api_key()  # KeyError if missing — never log value

        user_payload = {
            "market_snapshot": market_snapshot,
            "headlines": headlines,
            "instruction": (
                "Given this snapshot and headlines, return one JSON decision. "
                "Prefer hold if data is thin or conflicting."
            ),
        }
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("unexpected OpenAI response shape") from exc

        parsed = extract_json(content)
        return TradeDecision.model_validate(parsed)
