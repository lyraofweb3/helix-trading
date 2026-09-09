"""Copy HELIX brain signals into MetaTrader 5 Files folder (Windows).

The EA (HELIX.mq5) reads:
  InpSignalFile default = HELIX\\signals\\latest.json
from either:
  - Terminal Common Files  (FILE_COMMON)  ← preferred
  - Per-terminal MQL5\\Files

Typical Windows paths
---------------------
Common (shared by all terminals on this Windows user):
  %APPDATA%\\MetaQuotes\\Terminal\\Common\\Files\\HELIX\\signals\\latest.json

Per-terminal (Terminal ID is a 32-hex folder under Terminal\\):
  %APPDATA%\\MetaQuotes\\Terminal\\<TERMINAL_ID>\\MQL5\\Files\\HELIX\\signals\\latest.json

How to find TERMINAL_ID
-----------------------
1. Open MT5 → File → Open Data Folder
2. The path ends with ...\\Terminal\\<TERMINAL_ID>\\
3. Or list:  %APPDATA%\\MetaQuotes\\Terminal\\  (ignore Common and Community)

Usage
-----
  # One-shot copy into Common Files (default):
  python -m helix.mt5_bridge

  # Watch brain output and re-copy whenever latest.json changes:
  python -m helix.mt5_bridge --watch

  # Explicit paths:
  python -m helix.mt5_bridge --src signals/latest.json --dest-common
  python -m helix.mt5_bridge --terminal-id 0123456789ABCDEF0123456789ABCDEF

Environment
-----------
  HELIX_MT5_COMMON_FILES  Override Common\\Files directory
  HELIX_MT5_TERMINAL_ID   Default terminal id for --terminal-id mode
  HELIX_SIGNAL_SRC        Override source latest.json path

This module does NOT call any broker or LLM API. It only copies a JSON file.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path


def _repo_signal_default() -> Path:
    # helix/mt5_bridge.py → helix-brain/signals/latest.json
    return Path(__file__).resolve().parent.parent / "signals" / "latest.json"


def _appdata() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata)
    # Non-Windows fallback for docs/tests (will not be a real MT5 path)
    return Path.home() / "AppData" / "Roaming"


def common_files_dir() -> Path:
    override = os.environ.get("HELIX_MT5_COMMON_FILES")
    if override:
        return Path(override)
    return _appdata() / "MetaQuotes" / "Terminal" / "Common" / "Files"


def terminal_files_dir(terminal_id: str) -> Path:
    tid = terminal_id.strip()
    return _appdata() / "MetaQuotes" / "Terminal" / tid / "MQL5" / "Files"


def signal_rel_path() -> Path:
    # Must match EA default InpSignalFile (backslash → Path parts)
    return Path("HELIX") / "signals" / "latest.json"


def dest_path(*, use_common: bool, terminal_id: str | None) -> Path:
    if use_common:
        return common_files_dir() / signal_rel_path()
    if not terminal_id:
        raise ValueError("terminal_id required when not using Common Files")
    return terminal_files_dir(terminal_id) / signal_rel_path()


def copy_signal(
    src: Path,
    dest: Path,
    *,
    dry_run: bool = False,
) -> Path:
    if not src.is_file():
        raise FileNotFoundError(f"source signal not found: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"DRY-RUN would copy\n  {src}\n→ {dest}")
        return dest
    # Copy then replace for mostly-atomic update on Windows
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    shutil.copy2(src, tmp)
    tmp.replace(dest)
    print(f"Copied {src} → {dest}")
    return dest


def list_terminal_ids() -> list[str]:
    root = _appdata() / "MetaQuotes" / "Terminal"
    if not root.is_dir():
        return []
    skip = {"Common", "Community"}
    out: list[str] = []
    for p in sorted(root.iterdir()):
        if p.is_dir() and p.name not in skip and len(p.name) >= 16:
            out.append(p.name)
    return out


def watch_loop(src: Path, dest: Path, poll_sec: float) -> None:
    print(f"Watching {src} every {poll_sec}s → {dest} (Ctrl+C to stop)")
    last_mtime: float | None = None
    while True:
        try:
            if src.is_file():
                m = src.stat().st_mtime
                if last_mtime is None or m > last_mtime:
                    copy_signal(src, dest)
                    last_mtime = m
        except OSError as exc:
            print(f"watch error: {exc}", file=sys.stderr)
        time.sleep(max(0.5, poll_sec))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync helix-brain signals/latest.json into MT5 Files for HELIX.mq5"
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=Path(os.environ.get("HELIX_SIGNAL_SRC", str(_repo_signal_default()))),
        help="Source latest.json (default: repo signals/latest.json)",
    )
    parser.add_argument(
        "--terminal-id",
        default=os.environ.get("HELIX_MT5_TERMINAL_ID"),
        help="If set, write under Terminal\\<ID>\\MQL5\\Files; else Common\\Files",
    )
    parser.add_argument(
        "--list-terminals",
        action="store_true",
        help="Print detected Terminal IDs under %%APPDATA%%\\MetaQuotes\\Terminal",
    )
    parser.add_argument("--watch", action="store_true", help="Re-copy when source mtime changes")
    parser.add_argument("--poll", type=float, default=2.0, help="Watch poll seconds (default 2)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.list_terminals:
        ids = list_terminal_ids()
        if not ids:
            print("No Terminal folders found (is MT5 installed on this Windows user?)")
            print(f"Looked in: {_appdata() / 'MetaQuotes' / 'Terminal'}")
            return 1
        for tid in ids:
            print(tid)
        return 0

    use_common = not bool(args.terminal_id)
    try:
        dest = dest_path(use_common=use_common, terminal_id=args.terminal_id)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.watch:
        if args.dry_run:
            copy_signal(args.src, dest, dry_run=True)
            return 0
        try:
            watch_loop(args.src, dest, args.poll)
        except KeyboardInterrupt:
            print("\nStopped.")
        return 0

    try:
        copy_signal(args.src, dest, dry_run=args.dry_run)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
