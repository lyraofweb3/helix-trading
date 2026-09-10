"""HELIX 1.0 FastAPI — premium dark dashboard + signal API + v1 platform routes."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from helix.brain import run_once
from helix.config import DEFAULT_SYMBOL, JOURNAL_PATH, LATEST_SIGNAL_PATH, SIGNALS_DIR, SYMBOLS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("helix.app")

HELIX_API_TOKEN = os.environ.get("HELIX_API_TOKEN", "").strip()
POLL_SECONDS = int(os.environ.get("HELIX_POLL_SECONDS", "300") or "300")


def _check_token(x_helix_token: str | None) -> None:
    if not HELIX_API_TOKEN:
        return
    if not x_helix_token or x_helix_token != HELIX_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing X-HELIX-Token")


def _read_latest_signal() -> dict[str, Any] | None:
    if not LATEST_SIGNAL_PATH.is_file():
        return None
    try:
        return json.loads(LATEST_SIGNAL_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


async def _poll_loop(stop: asyncio.Event) -> None:
    logger.info("Background poll every %ss → %s", POLL_SECONDS, SIGNALS_DIR)
    while not stop.is_set():
        try:
            await asyncio.to_thread(run_once, DEFAULT_SYMBOL)
        except Exception as exc:  # noqa: BLE001
            logger.error("Background cycle failed: %s: %s", type(exc).__name__, exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(1, POLL_SECONDS))
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    stop = asyncio.Event()
    task: asyncio.Task | None = None
    if POLL_SECONDS > 0:
        task = asyncio.create_task(_poll_loop(stop))
        logger.info("Started background loop (HELIX_POLL_SECONDS=%s)", POLL_SECONDS)
    else:
        logger.info("Background loop disabled (HELIX_POLL_SECONDS=0)")
    yield
    stop.set()
    if task is not None:
        await task


app = FastAPI(title="HELIX", version="1.0.0", lifespan=lifespan)


# ── legacy routes (kept) ──────────────────────────────────────────────


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "signal_dir": str(SIGNALS_DIR),
        "poll_seconds": POLL_SECONDS,
        "token_required": bool(HELIX_API_TOKEN),
        "version": "1.0.0",
    }


@app.get("/api/signal")
def api_signal() -> JSONResponse:
    path = LATEST_SIGNAL_PATH
    if not path.is_file():
        return JSONResponse({"ok": False, "error": "no signal yet", "path": str(path)}, status_code=404)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"bad signal file: {type(exc).__name__}") from exc
    return JSONResponse({"ok": True, "signal": data})


@app.get("/api/journal")
def api_journal(n: int = Query(20, ge=1, le=500)) -> dict[str, Any]:
    path = JOURNAL_PATH
    if not path.is_file():
        return {"ok": True, "entries": [], "n": n}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"bad journal: {type(exc).__name__}") from exc
    entries: list[Any] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append({"raw": line})
    return {"ok": True, "entries": entries, "n": n}


@app.post("/api/run-once")
async def api_run_once(
    x_helix_token: str | None = Header(default=None, alias="X-HELIX-Token"),
) -> dict[str, Any]:
    _check_token(x_helix_token)
    try:
        result = await asyncio.to_thread(run_once, DEFAULT_SYMBOL)
    except KeyError as exc:
        key = str(exc).strip("'\"")
        raise HTTPException(
            status_code=503,
            detail=f"Missing API key ({key}). Set XAI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("run-once failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    return {"ok": True, "signal": result}


# ── HELIX 1.0 /api/v1/* ───────────────────────────────────────────────


@app.get("/api/v1/status")
def api_v1_status() -> dict[str, Any]:
    from helix_v1.monitoring import health_snapshot

    snap = health_snapshot()
    snap["ok_legacy_health"] = True
    snap["symbols"] = list(SYMBOLS)
    snap["default_symbol"] = DEFAULT_SYMBOL
    snap["account"] = {
        "balance": float(os.environ.get("HELIX_ACCOUNT_BALANCE", "50") or 50),
        "equity": float(
            os.environ.get(
                "HELIX_ACCOUNT_EQUITY",
                os.environ.get("HELIX_ACCOUNT_BALANCE", "50") or 50,
            )
            or 50
        ),
        "currency": os.environ.get("HELIX_ACCOUNT_CURRENCY", "USD"),
    }
    return {"ok": True, **snap}


@app.get("/api/v1/regime/{symbol}")
def api_v1_regime(symbol: str) -> dict[str, Any]:
    from helix.prices import fetch_snapshot
    from helix_v1.regime import detect_regime

    sym = symbol.strip().upper()
    try:
        snapshot = fetch_snapshot(sym)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"price fetch failed: {type(exc).__name__}") from exc
    regime = detect_regime(snapshot)
    return {
        "ok": True,
        "symbol": sym,
        "regime": regime.to_dict(),
        "price": {
            "last_close": snapshot.get("last_close"),
            "bid": snapshot.get("bid"),
            "ask": snapshot.get("ask"),
            "atr_points": snapshot.get("atr_points"),
            "rsi": snapshot.get("rsi"),
            "note": snapshot.get("note"),
        },
    }


@app.get("/api/v1/scan")
def api_v1_scan(
    symbols: str | None = Query(None, description="Comma-separated symbols; default universe"),
    offline: bool = Query(False, description="If true, skip network (empty unless cached)"),
) -> dict[str, Any]:
    from helix_v1.scanner import DEFAULT_UNIVERSE, scan_market

    syms = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    if offline:
        return {
            "ok": True,
            "offline": True,
            "results": [],
            "note": "offline=1 skips live Yahoo fetch; pass snapshots via internal tools",
            "universe": syms or list(DEFAULT_UNIVERSE),
        }
    try:
        rows = scan_market(syms)
    except Exception as exc:  # noqa: BLE001
        logger.error("scan failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    return {"ok": True, "count": len(rows), "results": rows}


@app.get("/api/v1/performance")
def api_v1_performance() -> dict[str, Any]:
    from helix_v1.performance import compute_metrics

    trades: list[dict[str, Any]] = []
    try:
        from helix_v1.db import get_db

        db = get_db()
        # best-effort: HelixDB may expose recent trades
        fetcher = getattr(db, "recent_trades", None) or getattr(db, "list_trades", None)
        if callable(fetcher):
            trades = list(fetcher(limit=200) or [])  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.info("performance db skip: %s", type(exc).__name__)

    # Fallback: derive scratch metrics from journal buy/sell lines (pnl unknown → empty)
    metrics = compute_metrics(
        [
            t
            for t in trades
            if isinstance(t, dict) and t.get("pnl") is not None
        ]
    )
    return {
        "ok": True,
        "metrics": metrics.to_dict(),
        "n_source_trades": len(trades),
        "note": "MFE/MAE optional; live broker PnL not wired — DB trades when present.",
    }


@app.get("/api/v1/explain/latest")
def api_v1_explain_latest(symbol: str | None = Query(None)) -> dict[str, Any]:
    signal = _read_latest_signal()
    sym = (symbol or (signal or {}).get("symbol") or DEFAULT_SYMBOL).strip().upper()

    explanation: dict[str, Any] | None = None
    try:
        from helix.prices import fetch_snapshot
        from helix_v1.explain import build_explanation
        from helix_v1.regime import detect_regime
        from helix_v1.signal_fusion import fuse_signals
        from helix_v1.strategies import run_all

        snap = fetch_snapshot(sym)
        snap["symbol"] = sym
        structure = snap.get("structure") if isinstance(snap.get("structure"), dict) else {}
        regime = detect_regime(snap)
        signals = run_all(snap, structure, regime)
        fusion = fuse_signals(signals, snap, structure, regime)
        explanation = build_explanation(
            snapshot=snap,
            regime=regime,
            fusion=fusion,
            ai_rationale=(signal or {}).get("rationale"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("explain failed: %s", exc)
        explanation = {
            "WHY": (signal or {}).get("rationale") or f"explain unavailable: {type(exc).__name__}",
            "CONTEXT": {"symbol": sym, "signal": signal},
            "CONFIRMATIONS": {},
            "RISK": {},
            "INVALIDATION": [],
            "EXIT": "N/A",
        }

    return {"ok": True, "symbol": sym, "signal": signal, "explanation": explanation}


@app.get("/api/v1/mode")
def api_v1_mode_get() -> dict[str, Any]:
    from helix_v1.monitoring import get_mode

    return {"ok": True, "mode": get_mode()}


@app.post("/api/v1/mode")
def api_v1_mode_set(
    payload: dict[str, Any] = Body(default_factory=dict),
    x_helix_token: str | None = Header(default=None, alias="X-HELIX-Token"),
) -> dict[str, Any]:
    _check_token(x_helix_token)
    from helix_v1.monitoring import get_mode, set_mode

    mode = str(payload.get("mode") or "").strip()
    if not mode:
        raise HTTPException(status_code=400, detail="body.mode required")
    new_mode = set_mode(mode)
    return {"ok": True, "mode": new_mode, "previous": get_mode()}


@app.post("/api/v1/kill-switch")
def api_v1_kill_switch(
    payload: dict[str, Any] = Body(default_factory=dict),
    x_helix_token: str | None = Header(default=None, alias="X-HELIX-Token"),
) -> dict[str, Any]:
    _check_token(x_helix_token)
    from helix_v1.risk_engine import is_kill_switch_on, set_kill_switch

    active = payload.get("active")
    if active is None:
        active = True
    reason = str(payload.get("reason") or "dashboard")
    result = set_kill_switch(bool(active), reason=reason)
    return {"ok": True, "kill_switch": is_kill_switch_on(), **result}


# Mount full HELIX v1 router (champion/auto/cycle/holly/mtf/…).
# Routes already defined above on `app` keep precedence; this adds the missing ones.
from app.v1_api import router as helix_v1_router

app.include_router(helix_v1_router)


# ── Dashboard HTML ────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<meta name="theme-color" content="#070b12"/>
<title>HELIX 1.0</title>
<style>
  :root {
    --bg: #070b12;
    --bg2: #0c121c;
    --card: #121a26;
    --card2: #162032;
    --border: #243247;
    --text: #e8eef7;
    --muted: #8b9bb0;
    --accent: #5b9dff;
    --accent2: #7c5cff;
    --buy: #3dd68c;
    --sell: #ff6b7a;
    --hold: #f0c14a;
    --danger: #ff6b7a;
    --ok: #3dd68c;
    --shadow: 0 10px 40px rgba(0,0,0,.35);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background:
      radial-gradient(1200px 600px at 10% -10%, rgba(91,157,255,.18), transparent 55%),
      radial-gradient(900px 500px at 100% 0%, rgba(124,92,255,.14), transparent 50%),
      var(--bg);
    color: var(--text);
    min-height: 100dvh;
    padding: 16px;
    padding-bottom: calc(20px + env(safe-area-inset-bottom));
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; margin-bottom: 16px; flex-wrap: wrap;
  }
  .brand { display: flex; align-items: baseline; gap: 10px; }
  h1 {
    font-size: 1.35rem; margin: 0; letter-spacing: 0.14em; font-weight: 700;
    background: linear-gradient(90deg, #fff, #9ec1ff);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .badge {
    font-size: 0.7rem; color: var(--muted); border: 1px solid var(--border);
    border-radius: 999px; padding: 4px 10px; background: rgba(255,255,255,.03);
  }
  .badge.ok { color: var(--ok); border-color: rgba(61,214,140,.35); }
  .badge.bad { color: var(--danger); border-color: rgba(255,107,122,.4); }
  .grid {
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: 12px;
  }
  .card {
    background: linear-gradient(180deg, var(--card), var(--card2));
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 16px;
    box-shadow: var(--shadow);
    grid-column: span 12;
  }
  @media (min-width: 720px) {
    .span6 { grid-column: span 6; }
    .span4 { grid-column: span 4; }
    .span8 { grid-column: span 8; }
  }
  .sec-title {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px; gap: 8px;
  }
  .sec-title strong { font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
  .action {
    font-size: 2.1rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.06em;
  }
  .action.buy { color: var(--buy); }
  .action.sell { color: var(--sell); }
  .action.hold, .action.close { color: var(--hold); }
  .meta { color: var(--muted); font-size: 0.85rem; line-height: 1.45; }
  .kv { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px; }
  .kv div {
    background: rgba(0,0,0,.22); border: 1px solid var(--border);
    border-radius: 12px; padding: 10px;
  }
  .kv .lbl { font-size: .7rem; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
  .kv .val { font-size: 1.05rem; font-weight: 650; margin-top: 4px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  button {
    flex: 1; min-width: 110px; border: none; border-radius: 12px; padding: 12px 14px;
    font-size: .95rem; font-weight: 650; background: linear-gradient(135deg, var(--accent), var(--accent2));
    color: #041018; cursor: pointer;
  }
  button.secondary { background: transparent; color: var(--text); border: 1px solid var(--border); }
  button.danger { background: linear-gradient(135deg, #ff6b7a, #ff8f5b); color: #1a0508; }
  button:disabled { opacity: .5; cursor: wait; }
  input[type=password], input[type=text], select {
    width: 100%; background: #0b0f14; border: 1px solid var(--border); border-radius: 10px;
    color: var(--text); padding: 11px; font-size: 0.95rem; margin-top: 8px;
  }
  .pill {
    display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem;
    background: #1c2736; color: var(--muted); margin-right: 4px;
  }
  .pill.buy { color: var(--buy); background: rgba(61,214,140,.12); }
  .pill.sell { color: var(--sell); background: rgba(255,107,122,.12); }
  .err { color: var(--danger); font-size: 0.85rem; margin-top: 8px; min-height: 1.1em; }
  .scan-row, .journal-item {
    border-top: 1px solid var(--border); padding: 10px 0; font-size: 0.9rem;
  }
  .scan-row:first-child, .journal-item:first-child { border-top: none; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .82rem; }
  pre.explain {
    white-space: pre-wrap; word-break: break-word; background: rgba(0,0,0,.25);
    border: 1px solid var(--border); border-radius: 12px; padding: 12px;
    font-size: .78rem; color: #c9d6e8; max-height: 280px; overflow: auto; margin: 0;
  }
</style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>HELIX 1.0</h1>
      <span class="badge" id="mode-badge">MODE …</span>
    </div>
    <span class="badge" id="health-badge">status …</span>
  </header>

  <div class="grid">
    <section class="card span4" id="sec-account">
      <div class="sec-title"><strong>Account</strong><span class="pill" id="acc-ccy">USD</span></div>
      <div class="kv">
        <div><div class="lbl">Balance</div><div class="val" id="acc-bal">—</div></div>
        <div><div class="lbl">Equity</div><div class="val" id="acc-eq">—</div></div>
        <div><div class="lbl">Mode</div><div class="val" id="acc-mode">—</div></div>
        <div><div class="lbl">Style</div><div class="val" id="acc-style">—</div></div>
        <div><div class="lbl">Kill switch</div><div class="val" id="acc-kill">—</div></div>
        <div><div class="lbl">Cloud exec</div><div class="val" id="acc-exec">—</div></div>
      </div>
    </section>

    <section class="card span8" id="sec-ai">
      <div class="sec-title"><strong>AI / Signal</strong><span class="pill" id="ai-provider">—</span></div>
      <div class="action hold" id="action">—</div>
      <div class="meta" id="sig-meta">Loading signal…</div>
      <p id="rationale" class="meta"></p>
      <div class="row">
        <button id="btn-refresh" class="secondary" type="button">Refresh</button>
        <button id="btn-champion" type="button">Auto Market</button>
      <button id="btn-run" class="secondary" type="button">Run once</button>
        <button id="btn-scan" class="secondary" type="button">Scan ranks</button>
      </div>
      <input id="token" type="password" placeholder="X-HELIX-Token (if set)" autocomplete="off"/>
      <div class="err" id="err"></div>
    </section>

    <section class="card span6" id="sec-market">
      <div class="sec-title"><strong>Market / Scan</strong><span class="pill" id="scan-count">0</span></div>
      <div id="scan-list" class="meta">HELIX auto-picks the best market (FX / gold / silver / oil) from scan + news. Tap Auto Market or Run once.</div>
    </section>

    <section class="card span6" id="sec-regime">
      <div class="sec-title"><strong>Regime</strong><span class="pill" id="regime-sym">—</span></div>
      <div class="kv">
        <div><div class="lbl">Regime</div><div class="val" id="reg-name">—</div></div>
        <div><div class="lbl">Strength</div><div class="val" id="reg-str">—</div></div>
        <div><div class="lbl">Bias</div><div class="val" id="reg-bias">—</div></div>
        <div><div class="lbl">Vol</div><div class="val" id="reg-vol">—</div></div>
      </div>
      <div class="meta" id="reg-notes" style="margin-top:8px"></div>
    </section>

    <section class="card span6" id="sec-mtf">
      <div class="sec-title"><strong>Multi-Timeframe</strong><span class="pill" id="mtf-align-pill">—</span></div>
      <div class="kv">
        <div><div class="lbl">HTF bias</div><div class="val" id="mtf-htf">—</div></div>
        <div><div class="lbl">Entry bias</div><div class="val" id="mtf-entry">—</div></div>
        <div><div class="lbl">Alignment</div><div class="val" id="mtf-align">—</div></div>
        <div><div class="lbl">Continuation</div><div class="val" id="mtf-cont">—</div></div>
        <div><div class="lbl">Reversal</div><div class="val" id="mtf-rev">—</div></div>
        <div><div class="lbl">Score</div><div class="val" id="mtf-score">—</div></div>
      </div>
      <div class="meta" id="mtf-notes" style="margin-top:8px"></div>
    </section>

    <section class="card span6" id="sec-holly">
      <div class="sec-title"><strong>Trade Ideas · Holly AI</strong><span class="pill" id="holly-pill">—</span></div>
      <div class="kv">
        <div><div class="lbl">Vote</div><div class="val" id="holly-side">—</div></div>
        <div><div class="lbl">Confidence</div><div class="val" id="holly-conf">—</div></div>
        <div><div class="lbl">API key</div><div class="val" id="holly-api">—</div></div>
        <div><div class="lbl">MT5 EA</div><div class="val" id="holly-mt5">HELIX.mq5</div></div>
      </div>
      <div class="meta" id="holly-thesis" style="margin-top:8px"></div>
      <div class="row">
        <button id="btn-holly" class="secondary" type="button">Refresh Holly</button>
      </div>
    </section>

    <section class="card span6" id="sec-positions">
      <div class="sec-title"><strong>Positions</strong><span class="pill">signal bridge</span></div>
      <div class="meta" id="pos-box">No live broker positions in this app — MT5 EA reads signals/latest.json.</div>
    </section>

    <section class="card span6" id="sec-perf">
      <div class="sec-title"><strong>Performance</strong></div>
      <div class="kv">
        <div><div class="lbl">Trades</div><div class="val" id="pf-n">—</div></div>
        <div><div class="lbl">Win rate</div><div class="val" id="pf-wr">—</div></div>
        <div><div class="lbl">Profit factor</div><div class="val" id="pf-pf">—</div></div>
        <div><div class="lbl">Expectancy</div><div class="val" id="pf-exp">—</div></div>
        <div><div class="lbl">Max DD</div><div class="val" id="pf-dd">—</div></div>
        <div><div class="lbl">Net PnL</div><div class="val" id="pf-net">—</div></div>
        <div><div class="lbl">Quality</div><div class="val" id="pf-quality">—</div></div>
      </div>
      <div class="meta" id="pf-note" style="margin-top:8px"></div>
    </section>

    <section class="card span6" id="sec-explain">
      <div class="sec-title"><strong>Explain (latest)</strong></div>
      <pre class="explain" id="explain-box">—</pre>
    </section>

    <section class="card span6" id="sec-system">
      <div class="sec-title"><strong>System</strong></div>
      <div class="kv">
        <div><div class="lbl">Data fresh</div><div class="val" id="sys-fresh">—</div></div>
        <div><div class="lbl">Signal age</div><div class="val" id="sys-age">—</div></div>
        <div><div class="lbl">Poll</div><div class="val" id="sys-poll">—</div></div>
        <div><div class="lbl">Halt</div><div class="val" id="sys-halt">—</div></div>
      </div>
      <div class="row">
        <select id="mode-select">
          <option value="PAPER">PAPER</option>
          <option value="SAFE">SAFE</option>
          <option value="BACKTEST">BACKTEST</option>
          <option value="LIVE">LIVE</option>
        </select>
      </div>
      <div class="row">
        <button id="btn-mode" class="secondary" type="button">Set mode</button>
        <button id="btn-kill" class="danger" type="button">Kill switch ON</button>
        <button id="btn-unkill" class="secondary" type="button">Disarm</button>
      </div>
      <div class="sec-title" style="margin-top:14px"><strong>Journal</strong><span class="pill" id="journal-count">0</span></div>
      <div id="journal"></div>
    </section>
  </div>

<script>
const $ = (id) => document.getElementById(id);
const errEl = $("err");
function setErr(msg) { errEl.textContent = msg || ""; }
function tokenHeaders() {
  const headers = { "Content-Type": "application/json" };
  const tok = $("token").value.trim();
  if (tok) headers["X-HELIX-Token"] = tok;
  return headers;
}
function fmt(n, d=2) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(d);
}
function paintSignal(s) {
  if (!s) {
    $("action").textContent = "—";
    $("action").className = "action hold";
    $("sig-meta").textContent = "No signal yet";
    $("rationale").textContent = "";
    $("ai-provider").textContent = "—";
    $("pos-box").textContent = "No live broker positions in this app — MT5 EA reads signals/latest.json.";
    return;
  }
  const a = (s.action || "hold").toLowerCase();
  $("action").textContent = a;
  $("action").className = "action " + (["buy","sell","hold","close"].includes(a) ? a : "hold");
  const conf = s.confidence != null ? Number(s.confidence).toFixed(2) : "?";
  const provider = (s.meta && s.meta.provider) || "?";
  const model = (s.meta && s.meta.model) || "";
  $("ai-provider").textContent = provider;
  $("sig-meta").textContent = `${s.symbol || "?"} · conf ${conf} · ${provider}${model ? " / " + model : ""} · ${s.ts || ""}`;
  $("rationale").textContent = s.rationale || "";
  $("pos-box").innerHTML = `<div><span class="pill ${a}">${a.toUpperCase()}</span> ${s.symbol || ""}</div>
    <div class="meta" style="margin-top:6px">SL hint: ${s.stop_hint || "—"} · TP hint: ${s.take_hint || "—"}</div>
    <div class="meta">Python never places broker orders. EA executes on Windows MT5.</div>`;
  if (s.symbol) loadRegime(s.symbol);
}

async function loadStatus() {
  try {
    const r = await fetch("/api/v1/status");
    const j = await r.json();
    const ok = j.ok && !j.kill_switch;
    $("health-badge").textContent = ok ? `ok · poll ${j.poll_seconds}s` : (j.kill_switch ? "KILL SWITCH" : "degraded");
    $("health-badge").className = "badge " + (ok ? "ok" : "bad");
    $("mode-badge").textContent = "MODE " + (j.mode || "?");
    $("acc-bal").textContent = fmt(j.account && j.account.balance, 2);
    $("acc-eq").textContent = fmt(j.account && j.account.equity, 2);
    $("acc-ccy").textContent = (j.account && j.account.currency) || "USD";
    $("acc-mode").textContent = j.mode || "—";
    if ($("acc-style")) $("acc-style").textContent = j.trade_style || "swing";
    $("acc-kill").textContent = j.kill_switch ? "ON" : "off";
    if ($("acc-exec")) $("acc-exec").textContent = (j.metaapi_configured ? "MetaAPI" : (j.executor || "mt5/file"));
    $("acc-kill").style.color = j.kill_switch ? "var(--danger)" : "var(--ok)";
    $("sys-fresh").textContent = j.data_fresh ? "yes" : "stale/none";
    $("sys-age").textContent = j.signal_age_sec != null ? fmt(j.signal_age_sec, 0) + "s" : "—";
    $("sys-poll").textContent = (j.poll_seconds != null ? j.poll_seconds : "?") + "s";
    $("sys-halt").textContent = j.halt_reason || (j.kill_switch ? "kill_switch" : "—");
    if (j.mode) $("mode-select").value = j.mode;
  } catch (e) {
    $("health-badge").textContent = "offline";
    $("health-badge").className = "badge bad";
  }
}

async function loadSignal() {
  setErr("");
  try {
    const r = await fetch("/api/signal");
    const j = await r.json();
    if (!r.ok) { paintSignal(null); return; }
    paintSignal(j.signal);
  } catch (e) { setErr("Failed to load signal"); }
}

async function loadJournal() {
  try {
    const r = await fetch("/api/journal?n=12");
    const j = await r.json();
    const entries = (j.entries || []).slice().reverse();
    $("journal-count").textContent = String(entries.length);
    $("journal").innerHTML = entries.map(e => {
      const a = (e.action || "?").toUpperCase();
      const conf = e.confidence != null ? Number(e.confidence).toFixed(2) : "";
      return `<div class="journal-item"><strong>${a}</strong> ${e.symbol || ""} <span class="pill">${conf}</span>
        <div class="meta">${e.ts || ""} · ${(e.meta && e.meta.provider) || ""}</div>
        <div class="meta">${(e.rationale || "").slice(0,140)}</div></div>`;
    }).join("") || `<div class="meta">Empty</div>`;
  } catch (e) {
    $("journal").innerHTML = `<div class="err">Journal load failed</div>`;
  }
}

async function loadRegime(symbol) {
  try {
    const r = await fetch("/api/v1/regime/" + encodeURIComponent(symbol));
    const j = await r.json();
    if (!r.ok) return;
    const rg = j.regime || {};
    $("regime-sym").textContent = j.symbol || symbol;
    $("reg-name").textContent = rg.regime || "—";
    $("reg-str").textContent = fmt(rg.strength, 2);
    $("reg-bias").textContent = rg.trend_bias || rg.direction || "—";
    $("reg-vol").textContent = rg.volatility || "—";
    $("reg-notes").textContent = (rg.notes || []).join(" · ");
  } catch (e) {}
}

async function loadPerformance() {
  try {
    let j;
    try {
      const r = await fetch("/api/v1/analytics");
      j = await r.json();
    } catch (e0) {
      const r = await fetch("/api/v1/performance");
      j = await r.json();
    }
    const m = j.metrics || {};
    $("pf-n").textContent = m.n_trades != null ? m.n_trades : "—";
    $("pf-wr").textContent = m.win_rate != null ? (100 * m.win_rate).toFixed(1) + "%" : "—";
    $("pf-pf").textContent = fmt(m.profit_factor, 2);
    $("pf-exp").textContent = fmt(m.expectancy, 2);
    $("pf-dd").textContent = fmt(m.max_drawdown_pct, 2) + "%";
    $("pf-net").textContent = fmt(m.net_pnl, 2);
    if ($("pf-quality")) $("pf-quality").textContent = j.quality_score != null ? j.quality_score : "—";
    $("pf-note").textContent = j.philosophy || m.notes || j.note || "";
  } catch (e) {}
}

async function loadHolly(symbol) {
  symbol = symbol || "EURUSD";
  try {
    const r = await fetch("/api/v1/holly/status?symbol=" + encodeURIComponent(symbol));
    const j = await r.json();
    const v = j.vote || {};
    $("holly-side").textContent = v.available ? (v.side || "flat") : "no idea";
    $("holly-conf").textContent = v.confidence != null ? fmt(v.confidence, 2) : "—";
    $("holly-api").textContent = j.api_configured ? "configured" : "file/webhook";
    $("holly-pill").textContent = v.available ? "live" : "idle";
    $("holly-thesis").textContent = v.thesis || j.mt5_path || "";
  } catch (e) {
    $("holly-side").textContent = "n/a";
  }
}

async function loadMtf(symbol) {

  symbol = symbol || "EURUSD";
  try {
    const r = await fetch("/api/v1/mtf/" + encodeURIComponent(symbol));
    const j = await r.json();
    if (!r.ok) return;
    const m = j.mtf || {};
    $("mtf-htf").textContent = m.htf_bias || "—";
    $("mtf-entry").textContent = m.entry_bias || "—";
    $("mtf-align").textContent = m.alignment || "—";
    $("mtf-align-pill").textContent = m.alignment || "—";
    $("mtf-cont").textContent = fmt(m.continuation_probability, 2);
    $("mtf-rev").textContent = fmt(m.reversal_probability, 2);
    $("mtf-score").textContent = fmt(m.alignment_score, 2);
    $("mtf-notes").textContent = (m.notes || []).join(" · ");
  } catch (e) {}
}

async function loadExplain() {
  try {
    const r = await fetch("/api/v1/explain/latest");
    const j = await r.json();
    $("explain-box").textContent = JSON.stringify(j.explanation || j, null, 2);
  } catch (e) {
    $("explain-box").textContent = "explain load failed";
  }
}

async function runScan() {
  setErr("");
  $("scan-list").textContent = "Scanning…";
  try {
    const r = await fetch("/api/v1/scan");
    const j = await r.json();
    if (!r.ok) { setErr(j.detail || "scan failed"); return; }
    const rows = j.opportunities || j.results || [];
    $("scan-count").textContent = String(rows.length);
    $("scan-list").innerHTML = rows.map(row => {
      const a = (row.action || "hold").toLowerCase();
      return `<div class="scan-row">
        <strong>${row.symbol}</strong>
        <span class="pill ${a}">${a}</span>
        <span class="pill">${row.state || ""}</span>
        <span class="pill">score ${fmt(row.score, 2)}</span>
        <div class="meta">${(row.rationale || "").slice(0,160)}</div>
      </div>`;
    }).join("") || `<div class="meta">No results</div>`;
    if (rows[0] && rows[0].symbol) { loadRegime(rows[0].symbol); loadMtf(rows[0].symbol); }
  } catch (e) {
    setErr("Scan failed");
    $("scan-list").textContent = "Scan failed";
  }
}


async function runChampion() {
  setErr("");
  const btn = $("btn-champion");
  if (btn) btn.disabled = true;
  try {
    const r = await fetch("/api/v1/champion/cycle", { method: "POST", headers: tokenHeaders ? tokenHeaders() : headers() });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { setErr(j.detail || ("HTTP " + r.status)); return; }
    const plan = (j.plan) || ((j.result||{}).plan) || {};
    if (typeof paintSignal === "function") paintSignal(plan);
    const top = j.picked || j.top || (j.ranked||[])[0];
    if (top && $("scan-list")) {
      const news = top.news_bias ? ` · news ${top.news_bias}` : "";
      $("scan-list").innerHTML = `<div class="meta"><strong>Auto Market:</strong> ${top.symbol} score ${Number(top.champion_score||0).toFixed(2)} · ${top.state||""} · ${top.action||""}${news}</div>` + ($("scan-list").innerHTML||"");
    }
    if (typeof loadJournal === "function") await loadJournal();
    if (typeof loadPerformance === "function") await loadPerformance();
  } catch (e) { setErr("Champion cycle failed"); }
  finally { if (btn) btn.disabled = false; }
}

async function runOnce() {
  setErr("");
  const btn = $("btn-run");
  btn.disabled = true;
  try {
    const r = await fetch("/api/run-once", { method: "POST", headers: tokenHeaders() });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { setErr(j.detail || ("HTTP " + r.status)); return; }
    paintSignal(j.signal);
    await Promise.all([loadJournal(), loadExplain(), loadStatus()]);
  } catch (e) {
    setErr("Run failed");
  } finally {
    btn.disabled = false;
  }
}

async function setMode() {
  setErr("");
  try {
    const r = await fetch("/api/v1/mode", {
      method: "POST",
      headers: tokenHeaders(),
      body: JSON.stringify({ mode: $("mode-select").value }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { setErr(j.detail || "mode failed"); return; }
    await loadStatus();
  } catch (e) { setErr("mode failed"); }
}

async function kill(active) {
  setErr("");
  try {
    const r = await fetch("/api/v1/kill-switch", {
      method: "POST",
      headers: tokenHeaders(),
      body: JSON.stringify({ active, reason: active ? "dashboard" : "disarm" }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { setErr(j.detail || "kill-switch failed"); return; }
    await loadStatus();
  } catch (e) { setErr("kill-switch failed"); }
}

function refreshAll() {
  if ($("btn-holly")) $("btn-holly").onclick = () => loadHolly("EURUSD");
if ($("btn-champion")) $("btn-champion").onclick = runChampion;
loadStatus(); loadSignal(); loadJournal(); loadPerformance(); loadExplain(); loadMtf('EURUSD'); loadHolly('EURUSD');
}

$("btn-refresh").onclick = refreshAll;
$("btn-run").onclick = runOnce;
$("btn-scan").onclick = runScan;
$("btn-mode").onclick = setMode;
$("btn-kill").onclick = () => kill(true);
$("btn-unkill").onclick = () => kill(false);
refreshAll();
setInterval(refreshAll, 60000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)
