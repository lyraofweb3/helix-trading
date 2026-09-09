"""Load HELIX knowledge pack (PLAYBOOK + DECISION_RULES) for prompt injection."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
_DEFAULT_MAX_CHARS = 24_000


@lru_cache(maxsize=4)
def _load_raw(max_chars: int) -> str:
    parts: list[str] = []
    playbook = _KNOWLEDGE_DIR / "PLAYBOOK.md"
    rules = _KNOWLEDGE_DIR / "DECISION_RULES.json"

    if playbook.is_file():
        try:
            parts.append(playbook.read_text(encoding="utf-8").strip())
        except OSError as exc:
            logger.warning("Could not read PLAYBOOK.md: %s", type(exc).__name__)
    else:
        logger.warning("PLAYBOOK.md missing under %s", _KNOWLEDGE_DIR)

    if rules.is_file():
        try:
            data = json.loads(rules.read_text(encoding="utf-8"))
            summary = _summarize_rules(data)
            parts.append("---\nDECISION_RULES summary:\n" + summary)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read DECISION_RULES.json: %s", type(exc).__name__)

    npfx = _KNOWLEDGE_DIR / "NETPROFITFX_SYNTHESIS.md"
    if npfx.is_file():
        try:
            parts.append("---\nNETPROFITFX synthesis (paraphrased):\n" + npfx.read_text(encoding="utf-8")[:4000])
        except OSError as exc:
            logger.warning("Could not read NETPROFITFX_SYNTHESIS.md: %s", type(exc).__name__)

    text = "\n\n".join(parts).strip()
    if not text:
        return ""
    if len(text) > max_chars:
        return text[: max_chars - 20].rstrip() + "\n…[truncated]"
    return text


def _summarize_rules(data: dict[str, Any]) -> str:
    """Compact JSON rules into a short bullet-ish text block."""
    lines: list[str] = []
    kv = data.get("knowledge_version")
    if kv:
        lines.append(f"version={kv}")
    defaults = data.get("defaults") or {}
    if defaults:
        lines.append(
            "defaults: "
            f"max_risk_pct={defaults.get('max_risk_pct_per_trade', '?')}, "
            f"daily_loss_cap={defaults.get('daily_loss_cap_pct', '?')}, "
            f"bias_tf={defaults.get('bias_timeframes')}, "
            f"timing={defaults.get('timing_timeframe')}, "
            f"news_blackout_m={defaults.get('news_blackout_minutes')}"
        )
    risk = data.get("risk") or {}
    if risk:
        lines.append(
            "risk: "
            f"{risk.get('default_risk_percent', '?')}% default, "
            f"daily_loss≤{risk.get('max_daily_loss_pct', '?')}%, "
            f"min_rr={risk.get('min_rr', '?')}, "
            f"martingale={risk.get('martingale', False)}"
        )
    tf = data.get("timeframes") or {}
    if tf:
        lines.append(
            f"tf: bias={tf.get('bias')} timing={tf.get('timing')} "
            f"never_fight_htf={tf.get('never_fight_clear_htf')}"
        )
    of = data.get("order_flow") or {}
    if of:
        lines.append(f"OF: bullish={of.get('bullish')}; bearish={of.get('bearish')}")
    rng = data.get("range") or {}
    if rng:
        lines.append(f"range: buy={rng.get('buy_zone')} sell={rng.get('sell_zone')}")
    sessions = data.get("sessions") or {}
    if sessions:
        lines.append(f"sessions: prefer={sessions.get('prefer_for_majors')}")
    news = data.get("news") or {}
    if news:
        lines.append(f"news: {news}")
    gates = data.get("confluence_gates") or {}
    if gates:
        req = gates.get("buy_sell_requires") or gates.get("score_items") or []
        lines.append("gates: " + ", ".join(str(x) for x in req))
        if "buy_sell_requires_min_score" in gates:
            lines.append(
                f"min_score={gates.get('buy_sell_requires_min_score')} "
                f"prefer_min={gates.get('prefer_min_score')}"
            )
        lines.append(f"else: {gates.get('else_action', 'hold')}")
    macro = data.get("macro") or {}
    if macro:
        lines.append(f"macro: {macro}")
    rules = data.get("rules") or []
    if isinstance(rules, list) and rules:
        bits = []
        for r in rules[:40]:
            if isinstance(r, dict) and r.get("id"):
                bits.append(f"{r.get('id')}:{r.get('prefer_action')}")
        if bits:
            lines.append("rules: " + "; ".join(bits))
    return "\n".join(lines)


def load_playbook_excerpt(max_chars: int = _DEFAULT_MAX_CHARS) -> str:
    """
    Return PLAYBOOK.md (+ DECISION_RULES summary) truncated to ~max_chars.
    Cached in-process via lru_cache on the underlying loader.
    """
    return _load_raw(max_chars)


def knowledge_version_from_rules() -> str | None:
    path = _KNOWLEDGE_DIR / "DECISION_RULES.json"
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        v = data.get("knowledge_version")
        return str(v) if v else None
    except (OSError, json.JSONDecodeError):
        return None


def clear_knowledge_cache() -> None:
    _load_raw.cache_clear()


def load_npfx_excerpt(max_chars: int = 1800) -> str:
    """Paraphrased NetProfitFX themes for LLM/quant context."""
    path = _KNOWLEDGE_DIR / "NETPROFITFX_SYNTHESIS.md"
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return text[:max_chars]

