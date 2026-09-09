# HELIX 1.0

Modular AI-native Forex & Futures stack on top of the existing HELIX brain + MT5 EA.

## Intelligence note

The master build brief named “Lytel 3.4”. HELIX 1.0 implements that role as the **HELIX Intelligence Layer**:

1. **Quant path (default for `HELIX_V1=1`)** — regime → strategies → signal fusion → hard risk → sizing → execution adapters  
2. **LLM path (optional)** — xAI Grok (`grok-4.6`) → OpenAI → Anthropic Claude (existing failover)

No separate Lytel model is required.

## Package layout (`helix_v1/`)

| Module | Role |
|--------|------|
| `modes` | BACKTEST / PAPER / LIVE / SAFE |
| `db` | SQLite trades, orders, signals, regimes, backtests, audit |
| `regime` | Market regime classifier |
| `strategies/*` | Trend, momentum, breakout, reversal, SMC structure, session, news |
| `signal_fusion` | HELIX confidence score + state machine (NO_TRADE is first-class) |
| `risk_engine` | Hard capital protection + kill switch (AI cannot override) |
| `sizing` | Fixed-fractional lots, no martingale |
| `execution` | Paper / MT5 bridge / backtest adapters |
| `pipeline` | Full cycle orchestrator |
| `backtest` / `walk_forward` | Historical lab |
| `performance` / `learning` | Metrics + non-auto-applied suggestions |
| `scanner` | Multi-symbol ranking |
| `monitoring` | Health + halt reason |

## Modes

```bash
export HELIX_MODE=PAPER   # default
export HELIX_V1=1         # brain uses quant pipeline instead of LLM
export HELIX_POLL_SECONDS=0  # keep auto LLM burn off unless you intend it
```

- **PAPER** — DB + signal file, no live broker assert  
- **SAFE** — forces hold on buy/sell intents  
- **LIVE** — MT5 bridge adapter (EA still executes on Windows MT5)  
- **BACKTEST** — offline bar engine

## API

- `GET /health` — includes v1 health  
- `GET /api/v1/status`  
- `GET /api/v1/regime/{symbol}`  
- `GET /api/v1/scan`  
- `GET /api/v1/performance`  
- `GET /api/v1/explain/latest`  
- `GET /api/v1/mode`  
- `POST /api/v1/kill-switch` — body `{"active": true, "reason": "..."}` (token if set)  
- `POST /api/v1/cycle?symbol=EURUSD` — one quant cycle  

Dashboard: `GET /`

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
PYTHONPATH=. .venv/bin/pytest -q
```

## Risk philosophy

Expectancy + drawdown control over win-rate theater. The previously discussed 74:26 figure is a **benchmark to track**, not a guarantee.

## Trade Ideas (Holly AI) × MetaTrader EA

HELIX fuses **Trade Ideas Holly AI** ideas with the existing **MetaTrader HELIX.mq5** execution path:

1. Ingest Holly alerts via `POST /api/v1/holly/ingest` or `data/holly_ideas.json`
2. Optional live API when `HOLLY_API_URL` + `TRADE_IDEAS_API_KEY` / `HOLLY_API_KEY` are set
3. Holly becomes one strategy vote + `holly_agree` confluence flag
4. HELIX risk engine still gates every order
5. Approved plans write `signals/latest.json` for **HELIX.mq5** on MT5

Holly never trades alone. Quant + risk + EA remain in control.


## Auto Market (default)

Set `HELIX_AUTO_MARKET=1` (default). Brain cycles scan FX + gold + oil + news and only act on the top-ranked setup.

- Override single symbol: `HELIX_AUTO_MARKET=0` or `HELIX_FORCE_SYMBOL=EURUSD`
- Attach HELIX EA on charts for symbols you allow (EURUSDm, XAUUSDm, USOILm, …). EA only executes when `latest.json` symbol matches the chart.


## Anytime readiness (demo → live)

- `HELIX_MAX_TRADES_PER_DAY=3` — hard daily cap (brain + risk + EA).
- `HELIX_AUTO_MARKET=1` + `HELIX_POLL_SECONDS=300` — scan every 5 minutes; **only enter when gates clear**.
- No fixed trade clock: EA `InpUseSessionFilter=false` (weekends still blocked).
- Keep `HELIX_V1_LLM=0` so poll does not burn xAI credits; Auto Market uses quant + news.


## Trade style: swing vs scalp

| Env | Value | Behavior |
|-----|-------|----------|
| `HELIX_TRADE_STYLE` | `swing` (default) | H1 timing, D1/H4 bias — original path |
| `HELIX_TRADE_STYLE` | `scalp` | M5 execution + M15 bias, tighter RR/SL |

Both styles work on **demo and live**, with Auto Market + max 3 trades/day. Set on Railway; EA `InpTradeStyle` should match (0=swing, 1=scalp).
