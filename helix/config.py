"""HELIX brain configuration. Risk defaults mirror HELIX.mq5 EA inputs."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

# Optional .env load (never logs secrets)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# --- paths ---
ROOT_DIR = Path(__file__).resolve().parent.parent
# SIGNAL_DIR env overrides default ./signals (Railway-friendly)
_signal_dir = os.environ.get("SIGNAL_DIR", "").strip()
SIGNALS_DIR = Path(_signal_dir).expanduser().resolve() if _signal_dir else (ROOT_DIR / "signals")
LATEST_SIGNAL_PATH = SIGNALS_DIR / "latest.json"
JOURNAL_PATH = SIGNALS_DIR / "journal.jsonl"
BOX_SECRETS_PATH = Path("/home/box/agent-data/box-secrets.json")

# --- xAI (primary) ---
XAI_BASE_URL = "https://api.x.ai/v1"
XAI_MODEL = os.environ.get("HELIX_XAI_MODEL", "grok-4.6")  # matches xAI console / SDK samples
XAI_TEMPERATURE = 0.2
XAI_TIMEOUT_SEC = 60.0

# --- OpenAI (backup) ---
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODEL = os.environ.get("HELIX_OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = 0.2
OPENAI_TIMEOUT_SEC = 60.0

# --- Anthropic Claude (tertiary) ---
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_MODEL = os.environ.get(
    "HELIX_ANTHROPIC_MODEL",
    "claude-sonnet-4-20250514",  # or claude-3-5-sonnet-latest via HELIX_ANTHROPIC_MODEL
)
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS = 1024
ANTHROPIC_TIMEOUT_SEC = 60.0


def load_box_secrets() -> dict[str, str]:
    """
    Read secrets dict from box-secrets.json if present.
    Never logs secret values. Returns {} on missing/invalid file.
    """
    try:
        if not BOX_SECRETS_PATH.is_file():
            return {}
        data = json.loads(BOX_SECRETS_PATH.read_text(encoding="utf-8"))
        secrets = data.get("secrets", data) if isinstance(data, dict) else {}
        if not isinstance(secrets, dict):
            return {}
        # Coerce to str values; skip non-stringy entries
        out: dict[str, str] = {}
        for k, v in secrets.items():
            if isinstance(k, str) and v is not None and str(v).strip():
                out[k] = str(v)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load box-secrets.json: %s", type(exc).__name__)
        return {}


def get_xai_api_key() -> str:
    """Prefer XAI_API_KEY env, else box-secrets.json. Raises KeyError if missing."""
    val = os.environ.get("XAI_API_KEY", "").strip()
    if val:
        return val
    secrets = load_box_secrets()
    val = (secrets.get("XAI_API_KEY") or "").strip()
    if val:
        return val
    raise KeyError("XAI_API_KEY")


def get_openai_api_key() -> str:
    """Prefer OPENAI_API_KEY env, else box-secrets.json. Raises KeyError if missing."""
    val = os.environ.get("OPENAI_API_KEY", "").strip()
    if val:
        return val
    secrets = load_box_secrets()
    val = (secrets.get("OPENAI_API_KEY") or "").strip()
    if val:
        return val
    raise KeyError("OPENAI_API_KEY")


def has_openai_api_key() -> bool:
    """True if an OpenAI key is available (env or box-secrets). Does not log values."""
    try:
        get_openai_api_key()
        return True
    except KeyError:
        return False


def get_anthropic_api_key() -> str:
    """Prefer ANTHROPIC_API_KEY env, else box-secrets.json. Raises KeyError if missing."""
    val = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if val:
        return val
    secrets = load_box_secrets()
    val = (secrets.get("ANTHROPIC_API_KEY") or "").strip()
    if val:
        return val
    raise KeyError("ANTHROPIC_API_KEY")


def has_anthropic_api_key() -> bool:
    """True if an Anthropic key is available (env or box-secrets). Does not log values."""
    try:
        get_anthropic_api_key()
        return True
    except KeyError:
        return False


# --- symbols (forex first) ---
SYMBOLS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "USDCHF",
    "NZDUSD",
]

DEFAULT_SYMBOL = "EURUSD"

# --- risk (mirrors HELIX.mq5) ---
RISK_PERCENT = 0.5          # InpRiskPercent
MAX_DAILY_LOSS_PCT = 2.0    # InpMaxDailyLossPct
MAX_POSITIONS = 1           # InpMaxPositions
MAX_TRADES_PER_DAY = 4      # InpMaxTradesPerDay
MIN_RR = 1.5                # InpMinRR
SL_ATR_MULT = 1.5           # InpSL_ATR_Mult
FX_MAX_SPREAD_POINTS = 25   # InpFxMaxSpreadPoints

# --- knowledge pack ---
KNOWLEDGE_VERSION = "2026-09-09-v2-deep"

# --- loop ---
# Prefer HELIX_POLL_SECONDS (web/Railway); fall back to HELIX_POLL_INTERVAL; default 300 for web
POLL_INTERVAL_SEC = int(
    os.environ.get("HELIX_POLL_SECONDS")
    or os.environ.get("HELIX_POLL_INTERVAL")
    or "300"
)

# --- free public RSS feeds (forex / business; fail soft per feed) ---
NEWS_FEEDS = [
    {
        "name": "FXStreet",
        "url": "https://www.fxstreet.com/rss/news",
    },
    {
        "name": "Investing.com Forex",
        "url": "https://www.investing.com/rss/news_1.rss",
    },
    {
        "name": "Forexlive",
        "url": "https://www.forexlive.com/feed",
    },
    {
        "name": "FXEmpire",
        "url": "https://www.fxempire.com/api/v1/en/articles/rss/news",
    },
    {
        "name": "Federal Reserve",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
    },
]

NEWS_MAX_HEADLINES = 20
NEWS_LOOKBACK_HOURS = 24
