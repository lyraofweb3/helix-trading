# HELIX synthesis — NetProfitFX free-course themes (paraphrased)

Source used for *ideas only*: public free NetProfitFX PDF course (Netty / NetProfitFX).  
This file is HELIX’s own rewrite for the brain/EA — not a reprint of the PDF.  
Promo tools (NetCopier, paid signal groups, advertised weekly %) are **not** part of HELIX.

## Operating path
1. Learn rules → practice on **demo** → only then real capital you can afford to lose.
2. Keep evolving; markets change. Losing trades are normal — edge is process + expectancy.
3. Your chart is the final judge; group opinions are secondary.

## Markets HELIX cares about
- **FX** 24h/5d — pairs are two currencies in conflict (base vs quote).
- **Gold / oil** — dollar, geopolitics, inventories matter.
- Session stack (Paris-ish clock in the course): Sydney → Tokyo → London → New York.  
  **London–NY overlap** = highest volume (prefer entries there when style allows).  
  HELIX “anytime readiness” still applies; overlap is a *boost*, not a hard clock.

## Units & sizing (conceptual)
- Pip = standard FX move unit (4th decimal; JPY 2nd/3rd). Protect capital first.
- Lot tiers: micro / mini / standard — larger size = larger $ per pip.
- Course suggests ≤ **3%** risk/trade; HELIX default stays tighter (**0.5%**) via `HELIX_RISK_PERCENT` / EA — never raise casually on small accounts.

## Order types (EA already supports market + SL/TP management)
- Market, buy/sell stop, buy/sell limit.
- **Take profit** at structure / measured move — not random pips.
- **Stop loss** beyond invalidation (S/R, trendline, Fib). Avoid ultra-tight stops that get hunted; avoid absurdly wide stops that wreck R:R.
- Prefer SL *behind* institutional structure, not on the obvious swing everyone sees.
- **Trailing stop** / **breakeven** once trade has room — don’t BE so early the first breath stops you out. HELIX EA trail/BE/partials map here.

## Styles (maps to `HELIX_TRADE_STYLE`)
| Style | Timeframes (course) | HELIX |
|-------|---------------------|-------|
| Swing | D1 / H4 / H1 | `swing` (default) |
| Day | H1 / M30 / M15 | swing + stricter same-day management |
| Scalp | M15 / M5 / M1 | `scalp` (M5 exec + M15 bias) |

Scalping needs low spread, fast cuts, high focus — HELIX caps **max 3 trades/day** even in scalp.

## News discipline
- Use an economic calendar (e.g. Investing.com). Mark **high-impact** events.
- Prefer **no new entries within ~3 hours** of major releases for that pair’s currencies (HELIX news gate / blackout).

## Price action vocabulary (for confluence, not lone triggers)
- Candles: body/wicks; large body = pressure; doji / hammer / shooting star / engulfing / morning–evening star → wait for **next-candle confirmation**.
- Trend: HH/HL bull, LH/LL bear; range = faster mean-reversion / wait for break.
- Trendlines (~45°), channels, S/R zones (not single lines), **role reversal** when broken.
- Institutional levels: session H/L, prior day/week/month H/L, **round numbers**, Fib **38.2 / 50 / 61.8 / 78.6**.
- Impulse vs correction (retracement) — prefer entries that respect HTF impulse.
- Patterns: double top/bottom, head & shoulders, flags, ascending/descending/symmetric triangles — trade **break + close beyond** pattern; pullbacks optional; combine with other confluence.

## Indicator stack (course preference — HELIX already has EMA/RSI)
- Don’t overload charts. Course focus: **RSI** + **EMA ~20/50** (HELIX also uses 21/50/200).
- RSI: oversold lean long, overbought lean short; neutrality zone as dynamic S/R in trend.
- Longer TF RSI > shorter TF.

## Six-step “launch a good trade” checklist → HELIX confluence
Only act when most of these align (HELIX already wants confluence ≥3):
1. **HTF bias** clear (bull → buy discounts; bear → sell premiums).
2. Price at meaningful **S/R** (session, PDH/PDL, round, Fib, channel).
3. **RSI** supportive on timing TF (H1 swing / M5–M15 scalp).
4. **EMA 20/50** structure agrees (pullback or cross confirmation).
5. **Candle / break** confirmation (engulf, hammer confirm, pattern break close).
6. **No high-impact news** in the next ~3h for that market.

If gates fail → **hold**. Patience is part of money management.

## Money management & psychology (non-negotiable)
- Always hard SL.
- Risk small fixed % of equity (HELIX 0.5% default).
- Prefer **reward ≥ 2× risk** when structure allows (scalp may use ~1.2–1.5 with tighter stops).
- No revenge trading / “make it back” loops.
- Emotions out of sizing; stick to the plan.
- Losses are tuition; aim for positive expectancy, not 100% wins.
- Demo until process is stable — then live.

## What HELIX deliberately does *not* copy
- Third-party trade-copier products or paid Telegram signal rooms.
- Any advertised weekly ROI / “guaranteed” win rates from marketing pages.
