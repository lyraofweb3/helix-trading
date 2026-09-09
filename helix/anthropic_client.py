"""Anthropic Messages API client for HELIX trading decisions (tertiary provider)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from helix.config import (
    ANTHROPIC_BASE_URL,
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_MODEL,
    ANTHROPIC_TIMEOUT_SEC,
    ANTHROPIC_VERSION,
    get_anthropic_api_key,
)
from helix.decision import SYSTEM_PROMPT, TradeDecision, extract_json

logger = logging.getLogger(__name__)


class AnthropicClient:
    """Thin Messages API wrapper. Mirrors XAIClient/OpenAIClient.analyze API."""

    def __init__(
        self,
        base_url: str = ANTHROPIC_BASE_URL,
        model: str = ANTHROPIC_MODEL,
        max_tokens: int = ANTHROPIC_MAX_TOKENS,
        timeout: float = ANTHROPIC_TIMEOUT_SEC,
        anthropic_version: str = ANTHROPIC_VERSION,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.anthropic_version = anthropic_version

    def analyze(
        self,
        market_snapshot: dict[str, Any],
        headlines: list[dict[str, Any]],
    ) -> TradeDecision:
        """Ask Claude for a structured buy|sell|hold decision via Messages API."""
        api_key = get_anthropic_api_key()  # KeyError if missing — never log value

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
            "max_tokens": self.max_tokens,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": json.dumps(user_payload)},
            ],
        }

        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.anthropic_version,
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        try:
            content = data["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("unexpected Anthropic response shape") from exc

        parsed = extract_json(content)
        return TradeDecision.model_validate(parsed)
