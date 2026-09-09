# HELIX Trading (Railway-ready)

Mobile-first **decision** layer for HELIX: FastAPI dashboard + AI brain (xAI Grok → OpenAI → Anthropic Claude) writing `signals/latest.json`. The **MT5 Expert Advisor** (`mq5/HELIX.mq5`) executes on a Windows MetaTrader 5 terminal (e.g. Exness `EURUSDm`).

```
  Phone / browser ──► FastAPI (Railway) ──► signals/latest.json
                              ▲
                     news + prices + LLM
                              │
                    Windows MT5 + HELIX.mq5  (file bridge / Common Files)
```

## Demo first — read this

- **Not** a no-loss system. Losing trades will happen.
- Run the EA on a **DEMO** account for weeks before any live money.
- This Python app **never** places broker orders — **signals only**.
- Risk defaults mirror the EA: ~0.5% risk/trade, 2% max daily loss, 1 position, 4 trades/day, min RR 1.5, no martingale.
- Prefer **hold** when data is thin or the free price feed fails.

### Honest MT5 note

**Live execution requires Windows MetaTrader 5** with the HELIX EA attached (Exness or similar, symbol like `EURUSDm`). Railway hosts only the brain/API/dashboard. Sync `latest.json` into MT5 Common Files on your PC (see EA comments / `helix/mt5_bridge.py` for Windows paths). Cloud Linux cannot run the MT5 terminal.

## Phone usage

1. Open your Railway URL on the phone (home screen bookmark works well).
2. Dark dashboard shows the latest action (`buy` / `sell` / `hold`), confidence, provider, rationale, and recent journal lines.
3. **Refresh** reloads signal + journal.
4. **Run once** triggers one brain cycle (`POST /api/run-once`). If you set `HELIX_API_TOKEN`, paste it in the token field (sent as `X-HELIX-Token`).
5. Background cycles run automatically when `HELIX_POLL_SECONDS > 0` (default `300`).

## API

| Method | Path | Notes |
|--------|------|--------|
| `GET` | `/` | Mobile dark dashboard |
| `GET` | `/health` | Liveness + poll settings |
| `GET` | `/api/signal` | Reads `$SIGNAL_DIR/latest.json` |
| `GET` | `/api/journal?n=20` | Last N lines of `journal.jsonl` |
| `POST` | `/api/run-once` | One cycle; requires `X-HELIX-Token` if `HELIX_API_TOKEN` is set |

Entrypoint: **`uvicorn app.main:app`** (module path `app.main:app`).

## Railway deploy

1. Connect this repo to Railway (Dockerfile builder — see `railway.toml`).
2. Set env vars (at least one AI key). Optionally set `HELIX_API_TOKEN`.
3. Deploy. Health check: `/health`.
4. Open the public URL on your phone.

Local Docker:

```bash
docker build -t helix .
docker run --rm -p 8080:8080 \
  -e XAI_API_KEY=... \
  -e HELIX_POLL_SECONDS=300 \
  helix
```

Local uvicorn (from repo root):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export SIGNAL_DIR=./signals HELIX_POLL_SECONDS=0
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

CLI (optional): `python cli_main.py once`

## Environment variables

| Variable | Purpose |
|----------|---------|
| `XAI_API_KEY` | Primary LLM (Grok) |
| `OPENAI_API_KEY` | Backup LLM |
| `ANTHROPIC_API_KEY` | Tertiary LLM (Claude) |
| `HELIX_API_TOKEN` | If set, required as header `X-HELIX-Token` on `POST /api/run-once` |
| `HELIX_POLL_SECONDS` | Background loop interval; `0` disables (default `300`) |
| `SIGNAL_DIR` | Signal directory (default `./signals`, container `/app/signals`) |
| `PORT` | HTTP port (Railway sets this; Dockerfile defaults `8080`) |

Optional: `HELIX_XAI_MODEL`, `HELIX_OPENAI_MODEL`, `HELIX_ANTHROPIC_MODEL`.

**Never commit real keys.** Copy `.env.example` → `.env` locally only.

## Layout

| Path | Role |
|------|------|
| `app/main.py` | FastAPI dashboard + API + background poll |
| `helix/` | Brain, news, prices, LLM clients, decision, config |
| `mq5/HELIX.mq5` | MT5 Expert Advisor (Windows) |
| `signals/` | `latest.json` + `journal.jsonl` (runtime; gitignored) |
| `Dockerfile` | Python 3.12-slim → uvicorn on `$PORT` |
| `cli_main.py` | Optional CLI `once` / `loop` |

## Safety

- Never log or commit API keys / `.env` / box-secrets.
- No live broker API from Python in this package.
- If all LLM providers fail, `/api/run-once` returns an error; the dashboard still shows the last good signal if present.
