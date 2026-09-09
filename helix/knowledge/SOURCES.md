# SOURCES — Public education & reference materials for HELIX

This list documents **public, reputable** materials used to synthesize HELIX’s playbook. HELIX wording in `PLAYBOOK.md` and `DECISION_RULES.json` is original synthesis — not a verbatim copy of any course, PDF, or paid curriculum.

**Policy:** No scraping of paid ICT/SMC courses, no pirate mirrors, no long copyrighted excerpts. Concepts are summarized at educational depth only.

---

## Risk management & position sizing

| Source | URL / ID | What we used |
|--------|----------|--------------|
| BabyPips — Position sizing / risk | https://www.babypips.com/trading/position-sizing-trading-risk-management | Fixed-fractional risk % of equity; size from stop distance & pip value; ATR awareness for volatility-adjusted size |
| Investopedia — Martingale in forex | https://www.investopedia.com/articles/forex/06/martingale.asp | Why doubling after losses is ruinous; HELIX **forbids** martingale / recovery averaging |
| Practitioner education (daily loss caps) | Public articles summarizing 1% per-trade / ~2–3% daily stop norms | Circuit-breaker idea: hit daily loss → stop trading for the session |

## Multi-timeframe bias, trend, indicators

| Source | URL / ID | What we used |
|--------|----------|--------------|
| BabyPips School (concepts) | babypips.com school lessons (MTF, trend, S/R — public free school) | Top-down bias; HH/HL vs LH/LL structure language |
| Investopedia — RSI | https://www.investopedia.com/terms/r/rsi.asp | RSI as momentum oscillator; ~70/30 extremes; false signals in strong trends |
| Investopedia — RSI in FX | https://www.investopedia.com/ask/answers/012015/how-do-i-use-relative-strength-index-rsi-create-forex-trading-strategy.asp | Extremes as context, not automatic entries |
| Elder / Shannon MTF tradition (via public explainers) | Public multi-timeframe guides citing Triple Screen / top-down | HTF = direction; LTF = timing (HELIX maps to D1/H4 bias, H1 timing) |

## Sessions & calendars

| Source | URL / ID | What we used |
|--------|----------|--------------|
| Investopedia — FX trading hours / sessions | https://www.investopedia.com/articles/forex/08/forex-trading-schedule-trading-times.asp | Asia / London / NY; London–NY overlap as highest activity window |
| Investopedia — Economic calendar | https://www.investopedia.com/terms/e/economic-calendar.asp | High-impact releases move FX; plan around scheduled events |
| Central bank calendars (conceptual) | Fed, ECB, BoE, BoJ official calendars | News blackout around rate decisions, CPI, NFP-class prints — check live calendar, do not hardcode times |

## Market structure facts (macro, not setups)

| Source | URL / ID | What we used |
|--------|----------|--------------|
| BIS Triennial Survey 2025 (FX turnover) | https://www.bis.org/statistics/rpfx25_fx.htm | FX OTC ~$9.6T/day (Apr 2025); USD dominance; concentration in UK/US/SG/HK desks — context for liquidity/session importance |
| IMF / BIS commentary on FX & hedging | BIS Quarterly Review pieces linked from Triennial | Volatility spikes around policy surprises; hedging flows matter |

## Liquidity / ICT-style concepts (public summaries only)

| Source | Notes |
|--------|-------|
| User-attached DOL PDF (local) | Paraphrased in `USER_PDF_NOTES.md` — HELIX’s primary liquidity vocabulary source for this pack |
| Public SMC/ICT educational blogs & explainers | High-level only: FVG as three-candle imbalance, premium/discount vs dealing-range midpoint, liquidity sweeps of swing H/L, SMT as correlated-pair divergence — **not** copied from paid Inner Circle materials |

Public conceptual anchors (non-paywalled explainers used for vocabulary cross-check only):
- Liquidity sweep / stop-run as run beyond obvious highs/lows then reversal
- Premium = upper half of dealing range; discount = lower half
- IRL ≈ inefficiencies (FVG/OB); ERL ≈ external swing liquidity

## Academic / practitioner risk framing

- Fixed fractional position sizing and ruin probability (Van Tharp–style public discussion of % risk per trade).
- Daily loss limits as behavioral circuit breakers (prop-firm / retail education consensus ~2–3% day stop when risking ~1% per trade).

---

## Limitations (read carefully)

1. **Not a trading system guarantee.** Public education + user notes ≠ edge proof. Past structure does not predict future P&L.
2. **ICT/SMC terminology is contested.** HELIX uses HELIX-owned labels grounded in the user PDF + public summaries; proprietary paid course rules are intentionally excluded.
3. **BabyPips / some sites block automated fetchers.** Citations rely on known public URLs and search summaries; operators should open pages in a browser to verify latest wording.
4. **Session clock times shift with DST.** Always convert with a live session map; UTC offsets in playbooks are approximate.
5. **Economic calendars change.** Blackout windows must be computed from a live calendar feed, not static lists.
6. **BIS figures are snapshots** (April survey months) and subject to revision; use for context, not trade signals.
7. **User PDF is informal education material** (PowerPoint deck). Treat as user preference vocabulary, not regulatory or academic authority.
8. **No broker-specific lot math, swap, or leverage advice.** HELIX must use account equity, contract specs, and broker margin rules at runtime.

---

## How HELIX should cite internally

- Prefer: “Per HELIX playbook (risk § / liquidity §)” over naming influencers.
- When explaining to the user: distinguish **user PDF notes** vs **public risk/session facts**.
