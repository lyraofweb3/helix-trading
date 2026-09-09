"""HELIX FastAPI app — mobile dashboard + signal API + optional background loop."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from helix.brain import run_once
from helix.config import DEFAULT_SYMBOL, JOURNAL_PATH, LATEST_SIGNAL_PATH, SIGNALS_DIR

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


app = FastAPI(title="HELIX", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "signal_dir": str(SIGNALS_DIR),
        "poll_seconds": POLL_SECONDS,
        "token_required": bool(HELIX_API_TOKEN),
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


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<meta name="theme-color" content="#0b0f14"/>
<title>HELIX</title>
<style>
  :root {
    --bg: #0b0f14;
    --card: #141a22;
    --border: #243041;
    --text: #e8eef7;
    --muted: #8b9bb0;
    --accent: #5b9dff;
    --buy: #3dd68c;
    --sell: #ff6b7a;
    --hold: #f0c14a;
    --danger: #ff6b7a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text); min-height: 100dvh;
    padding: 16px; padding-bottom: calc(16px + env(safe-area-inset-bottom));
  }
  header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
  h1 { font-size: 1.25rem; margin: 0; letter-spacing: 0.08em; }
  .badge { font-size: 0.7rem; color: var(--muted); border: 1px solid var(--border); border-radius: 999px; padding: 4px 10px; }
  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 16px;
    padding: 16px; margin-bottom: 12px;
  }
  .action {
    font-size: 2rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
  }
  .action.buy { color: var(--buy); }
  .action.sell { color: var(--sell); }
  .action.hold { color: var(--hold); }
  .meta { color: var(--muted); font-size: 0.85rem; margin-top: 6px; line-height: 1.4; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
  button {
    flex: 1; min-width: 120px; border: none; border-radius: 12px; padding: 14px 16px;
    font-size: 1rem; font-weight: 600; background: var(--accent); color: #041018; cursor: pointer;
  }
  button.secondary { background: transparent; color: var(--text); border: 1px solid var(--border); }
  button:disabled { opacity: 0.5; cursor: wait; }
  .token-row { display: flex; gap: 8px; margin-top: 8px; }
  input[type=password], input[type=text] {
    flex: 1; background: #0b0f14; border: 1px solid var(--border); border-radius: 10px;
    color: var(--text); padding: 12px; font-size: 0.95rem;
  }
  .journal-item {
    border-top: 1px solid var(--border); padding: 10px 0; font-size: 0.9rem;
  }
  .journal-item:first-child { border-top: none; }
  .err { color: var(--danger); font-size: 0.85rem; margin-top: 8px; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; background: #1c2736; color: var(--muted); }
</style>
</head>
<body>
  <header>
    <h1>HELIX</h1>
    <span class="badge" id="health">…</span>
  </header>

  <section class="card" id="signal-card">
    <div class="action hold" id="action">—</div>
    <div class="meta" id="sig-meta">Loading signal…</div>
    <p id="rationale" class="meta"></p>
    <div class="row">
      <button id="btn-refresh" class="secondary" type="button">Refresh</button>
      <button id="btn-run" type="button">Run once</button>
    </div>
    <div class="token-row">
      <input id="token" type="password" placeholder="X-HELIX-Token (if set)" autocomplete="off"/>
    </div>
    <div class="err" id="err"></div>
  </section>

  <section class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <strong>Journal</strong>
      <span class="pill" id="journal-count">0</span>
    </div>
    <div id="journal"></div>
  </section>

<script>
const $ = (id) => document.getElementById(id);
const errEl = $("err");

function setErr(msg) { errEl.textContent = msg || ""; }

function paintSignal(s) {
  if (!s) {
    $("action").textContent = "—";
    $("action").className = "action hold";
    $("sig-meta").textContent = "No signal yet";
    $("rationale").textContent = "";
    return;
  }
  const a = (s.action || "hold").toLowerCase();
  $("action").textContent = a;
  $("action").className = "action " + (["buy","sell","hold"].includes(a) ? a : "hold");
  const conf = s.confidence != null ? Number(s.confidence).toFixed(2) : "?";
  const provider = (s.meta && s.meta.provider) || "?";
  const model = (s.meta && s.meta.model) || "";
  $("sig-meta").textContent = `${s.symbol || "?"} · conf ${conf} · ${provider}${model ? " / " + model : ""} · ${s.ts || ""}`;
  $("rationale").textContent = s.rationale || "";
}

async function loadHealth() {
  try {
    const r = await fetch("/health");
    const j = await r.json();
    $("health").textContent = j.ok ? `poll ${j.poll_seconds}s` : "down";
  } catch (e) {
    $("health").textContent = "offline";
  }
}

async function loadSignal() {
  setErr("");
  try {
    const r = await fetch("/api/signal");
    const j = await r.json();
    if (!r.ok) { paintSignal(null); return; }
    paintSignal(j.signal);
  } catch (e) {
    setErr("Failed to load signal");
  }
}

async function loadJournal() {
  try {
    const r = await fetch("/api/journal?n=15");
    const j = await r.json();
    const entries = (j.entries || []).slice().reverse();
    $("journal-count").textContent = String(entries.length);
    $("journal").innerHTML = entries.map(e => {
      const a = (e.action || "?").toUpperCase();
      const conf = e.confidence != null ? Number(e.confidence).toFixed(2) : "";
      return `<div class="journal-item"><strong>${a}</strong> ${e.symbol || ""} <span class="pill">${conf}</span><div class="meta">${e.ts || ""} · ${(e.meta && e.meta.provider) || ""}</div><div class="meta">${(e.rationale || "").slice(0,160)}</div></div>`;
    }).join("") || `<div class="meta">Empty</div>`;
  } catch (e) {
    $("journal").innerHTML = `<div class="err">Journal load failed</div>`;
  }
}

async function runOnce() {
  setErr("");
  const btn = $("btn-run");
  btn.disabled = true;
  try {
    const headers = { "Content-Type": "application/json" };
    const tok = $("token").value.trim();
    if (tok) headers["X-HELIX-Token"] = tok;
    const r = await fetch("/api/run-once", { method: "POST", headers });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      setErr(j.detail || ("HTTP " + r.status));
      return;
    }
    paintSignal(j.signal);
    await loadJournal();
  } catch (e) {
    setErr("Run failed");
  } finally {
    btn.disabled = false;
  }
}

$("btn-refresh").onclick = () => { loadSignal(); loadJournal(); loadHealth(); };
$("btn-run").onclick = runOnce;
loadHealth(); loadSignal(); loadJournal();
setInterval(() => { loadSignal(); loadJournal(); }, 60000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)
