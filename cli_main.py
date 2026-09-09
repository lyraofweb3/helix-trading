#!/usr/bin/env python3
"""HELIX AI trading brain CLI.

Usage:
  python main.py once          # single cycle
  python main.py loop          # poll every N seconds (HELIX_POLL_INTERVAL, default 60)
  python main.py loop --seconds 30
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from helix.config import DEFAULT_SYMBOL, POLL_INTERVAL_SEC
from helix.brain import run_once


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_once(symbol: str) -> int:
    try:
        result = run_once(symbol=symbol)
    except KeyError as exc:
        key = str(exc).strip("'\"")
        if key in {"XAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"} or "API_KEY" in key:
            logging.error(
                "No usable API key. Set XAI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY "
                "in the environment or /home/box/agent-data/box-secrets.json, then retry."
            )
            return 2
        raise
    except Exception as exc:  # noqa: BLE001
        # Never print exception args that might contain headers; keep message short
        logging.error("Cycle failed: %s: %s", type(exc).__name__, exc)
        return 1

    meta = result.get("meta") or {}
    print(
        f"OK action={result.get('action')} symbol={result.get('symbol')} "
        f"confidence={result.get('confidence')} "
        f"provider={meta.get('provider')} model={meta.get('model')} "
        f"-> signals/latest.json"
    )
    return 0


def cmd_loop(symbol: str, seconds: int) -> int:
    logging.info("Looping every %ss on %s (Ctrl+C to stop)", seconds, symbol)
    while True:
        code = cmd_once(symbol)
        if code == 2:
            return 2  # missing key — no point retrying
        time.sleep(max(1, seconds))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HELIX AI trading brain")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "--symbol",
        default=DEFAULT_SYMBOL,
        help=f"Primary symbol (default {DEFAULT_SYMBOL})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("once", help="Run one news→AI→signal cycle")

    p_loop = sub.add_parser("loop", help="Poll continuously")
    p_loop.add_argument(
        "--seconds",
        type=int,
        default=POLL_INTERVAL_SEC,
        help=f"Poll interval (default {POLL_INTERVAL_SEC})",
    )

    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    if args.command == "once":
        return cmd_once(args.symbol)
    if args.command == "loop":
        return cmd_loop(args.symbol, args.seconds)
    parser.error(f"unknown command {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
