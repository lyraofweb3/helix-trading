# HELIX Forex Playbook

**Owner:** HELIX (synthesized operating doctrine)  
**Style:** Original HELIX wording — not a copy of any PDF or paid course.  
**Companion files:** `SOURCES.md`, `DECISION_RULES.json`, `USER_PDF_NOTES.md`

This playbook is a decision framework for bias, timing, risk, and when to stand down. It does not promise profitability.

---

## 1. Risk management (non-negotiable)

### 1.1 Position sizing
- Risk a **fixed fraction of equity** per idea (default **≤ 1%** of account equity to the stop).
- Size from: `lots ≈ (equity × risk%) / (stop_distance_in_pips × pip_value_per_lot)`.
- Wider stops → smaller size. Never widen the stop to “fit” a preferred lot size.
- Recalculate from **current equity** after material wins/losses (fixed fractional).
- Cap **correlated heat**: multiple positions that move together count toward one risk budget (e.g. total open risk ≤ ~2–3% unless explicitly overridden).

### 1.2 Daily / weekly loss caps
- Hard **daily loss cap** (default **2–3%** of starting-day equity). Hit it → flat and **no new trades** until next session day.
- Optional weekly review pause after a larger drawdown (e.g. ~5–6%); reduce size or stop until plan review.
- No “revenge” size increases after losses.

### 1.3 No martingale / no recovery averaging
- **Forbidden:** doubling size after a loss, pyramiding into losers to “average down,” or removing stops to wait it out.
- One planned risk unit per setup; losers are closed at the stop.

### 1.4 News blackout (high-impact)
- Before any entry, check a live **economic calendar** for the pair’s currencies (and USD when relevant).
- **Blackout:** no new entries inside a buffer around high-impact events (typical HELIX default: **±30–60 minutes** around red-folder prints — rates, CPI, NFP-class employment, major central-bank decisions). Widen buffer for FOMC/ECB-style events if spreads/volatility are historically violent.
- Flat or tightly managed only if already in a trade and event risk was accepted in the plan; prefer not to hold naked through unknown outcomes unless the playbook instance explicitly allows it.
- Spreads and slippage spike at the print — assume stops can gap.

---

## 2. Multi-timeframe bias

| Role | Timeframe | Question answered |
|------|-----------|-------------------|
| Bias (primary) | **D1** | Dominant direction & major swings |
| Bias (refine) | **H4** | Structure inside the daily story; pullback vs reversal |
| Timing | **H1** | Entry trigger, stop placement, local invalidation |

**Rules**
- Trade **with** D1/H4 bias; use H1 only to time pullbacks or continuations — not to invent a contrary narrative.
- If D1 and H4 conflict (e.g. D1 up, H4 impulsive down with no exhaustion), **HOLD** until alignment or a clear H4 shift.
- Prefer ~4:1–6:1 spacing between frames (D1 → H4 → H1 fits).

---

## 3. Trend structure, EMA stack, RSI

### 3.1 Structure
- **Bullish structure:** Higher Highs + Higher Lows (HH/HL).
- **Bearish structure:** Lower Highs + Lower Lows (LH/LL).
- Break of structure against the trend (e.g. loss of HL in an uptrend) → downgrade bias; wait for rebuild.

### 3.2 EMA stack (context filter)
- Use a short/mid/long EMA stack (example set: fast/mid/slow such as 9/21/50 or 21/50/200 — pick one set and stick to it).
- **Bullish stack:** price above rising slower EMAs; faster EMAs above slower.
- **Bearish stack:** mirror below.
- Mixed / flat EMAs → treat as range; prefer mean-reversion-to-levels or **HOLD**.

### 3.3 RSI extremes
- RSI (~14) **> ~70** = overbought context; **< ~30** = oversold context.
- In strong trends RSI can stay extreme — do **not** fade solely on RSI.
- Prefer RSI as: (a) pullback filter with trend (e.g. dip toward 40–50 then turn in trend direction), or (b) exhaustion warning **at a level** (PDH/PDL, range extreme, discount/premium array).
- Divergence (price vs RSI) is a caution flag, not a standalone entry.

---

## 4. Liquidity concepts (HELIX terms)

Vocabulary aligned with HELIX’s user DOL notes and public SMC education summaries — reframed for HELIX ops.

### 4.1 Order flow
- **Bullish flow:** breaks highs, rejects lows.
- **Bearish flow:** breaks lows, rejects highs.
- No clear flow → no aggressive DOL trade.

### 4.2 Draw on Liquidity (DOL)
- DOL = the liquidity pool price is expected to seek next (session high/low, PDH/PDL, PWH/PWL, equal highs/lows, range extreme, or CRT extreme).
- Always state DOL **conditional on order flow**.

### 4.3 Candle Range Theory (CRT)
Three-candle logic:
1. **Generate** — candle 1 prints CRT high & low (two liquidity banks).
2. **Purge** — candle 2 raids the short-term DOL side implied by flow.
3. **Neutralize** — if candle 2 closes **inside** candle 1’s range, retarget the opposite CRT extreme (long-term DOL) and look for expansion.

Stack CRT with key levels when available.

### 4.4 Previous day / week high-low reaction rules
When price interacts with PDH/PDL or PWH/PWL:

| Reaction | HELIX lean |
|----------|------------|
| **Close above** | Continuation higher; DOL toward highs / next upside pool |
| **Close below** | Continuation lower; DOL toward lows |
| **Wick above** (reject) | Lean lower; DOL toward prior low |
| **Wick below** (reject) | Lean higher; DOL toward prior high |
| **Close inside** prior range, **bullish** regime | Often seek prior low (liquidity under) |
| **Close inside** prior range, **bearish** regime | Often seek prior high (liquidity above) |

Distinguish **close** vs **wick** — they imply opposite delivery.

### 4.5 Range dynamics
- Mark **high / low / 50% (equilibrium)**.
- First magnet often **50%**; then the extreme consistent with flow.
- Mid-range chop without CRT/SMT → **HOLD**.

### 4.6 IRL vs ERL
- **IRL (internal):** FVG / IFVG / order-block style inefficiencies inside the dealing range.
- **ERL (external):** swing highs / swing lows (stop pools outside the internal range).
- Path IRL→ERL or ERL→IRL is higher quality when **CRT and/or SMT** confirm at the IRL touch.
- At IRL with CRT + SMT: short-term DOL often the CRT extreme; longer-term DOL the ERL.

### 4.7 Premium / discount
- Relative to the active dealing range: **above 50% = premium**, **below 50% = discount**.
- Prefer **buys in discount**, **sells in premium**, aligned with HTF bias and flow.
- Counter-location entries (buy premium / sell discount) require exceptional confluence — default is skip.

### 4.8 SMT (HELIX)
- **SMT** = divergence / disagreement between **correlated pairs** (or pair vs index) at a liquidity decision point (e.g. one makes a new low, the correlated peer does not).
- Use as **confirmation** at IRL/CRT, not as a lone signal.
- If correlated markets agree on the raid, treat the sweep as cleaner; if they diverge, favor the SMT narrative only with structure + CRT.

---

## 5. Session awareness (high level)

Approximate UTC windows (verify DST):

| Session | Typical character |
|---------|-------------------|
| **Asia (Tokyo)** | Often range-building; JPY/AUD/NZD more active; can set highs/lows later raided |
| **London** | Liquidity expansion; many European pair trends start |
| **London–NY overlap** | Highest volume/tightest spreads historically; major USD data often lands here |
| **NY afternoon** | Can trend or fade; watch for thin conditions into close |
| **Off-overlap / Sydney-only stretch** | Wider spreads; avoid size or exotic pairs |

HELIX preference: execute timed entries in **London** or **London–NY overlap** unless the pair’s natural session is Asia. Do not chase thin-book spikes.

---

## 6. When to HOLD

Default to **HOLD** (no new buy/sell) when any apply:

1. **Unclear bias** — D1/H4 structure mixed; EMA stack flat; no HH/HL or LH/LL clarity.
2. **Conflicting news** — dual-currency events, or narrative vs price disagreement without a plan.
3. **Mid-range chop** — price oscillating around 50% without CRT purge/neutralize or clear flow.
4. **Event risk** — inside news blackout; spreads already blown out.
5. **Missing confluence** — want order flow + (level or CRT) + location (premium/discount) at minimum; less than that → pass.
6. **Risk budget used** — daily loss cap hit, or correlated heat maxed.
7. **SMT/CRT required but absent** for an IRL→ERL story you were waiting on.
8. **Emotional state / plan breach** — urge to revenge or martingale → HOLD and stop.

HOLD is a valid HELIX action and often the highest-EV choice.

---

## 7. Minimum checklist before BUY / SELL

1. Risk size ≤ 1%; daily cap not hit; no martingale.
2. Outside news blackout (or explicit event plan).
3. D1/H4 bias agrees with intended direction.
4. Order flow agrees.
5. Location: discount for buys / premium for sells (or accepted exception logged).
6. DOL stated; invalidation (stop) beyond structure/sweep extreme.
7. Timing TF (H1) trigger present; session acceptable.
8. Else → **HOLD**.

Machine-readable form: see `DECISION_RULES.json`.


---

## 8. Macro FX drivers (HELIX world model)

Price is not random; HELIX maps **drivers → currency bias** before entries.

### 8.1 Interest rates & differentials
- Relative **policy rates / expected path** (hikes vs cuts) dominate medium-term FX.
- Rising rate differential favoring currency A vs B → structural bid for A (carry + flows), all else equal.
- Watch: central bank speak, OIS/futures implied cuts, inflation surprises vs target.

### 8.2 Risk-on / risk-off
- **Risk-on:** AUD, NZD, EM FX, high-beta tend to bid; JPY, CHF, sometimes USD as funding/safe often soften (context-dependent).
- **Risk-off / panic:** USD, JPY, CHF bid; AUD/NZD/EM sold; gold often bid (USDXYZ nuances).
- Equity dump + VIX spike → treat risk FX longs as hostile unless structure is exceptional.

### 8.3 DXY / USD pulse
- Broad USD strength (DXY up) pressures EUR, GBP, AUD, NZD, CAD, etc.
- If DXY is impulsively trending, do not fade USD crosses lightly on LTF noise.

### 8.4 Commodity FX
- **CAD:** oil-sensitive (WTI/Brent). Oil crush → CAD soft bias; oil surge → CAD support (with US data overlay).
- **AUD/NZD:** China growth, iron ore / dairy narratives matter.
- **NOK:** oil; **JPY:** rates + risk; never treat JPY as “always safe” in rate-normalization regimes.

### 8.5 Geopolitics & fiscal
- Wars, sanctions, election shocks, debt-ceiling / fiscal crises → USD safe-haven or USD funding squeezes. Prefer **hold** until first impulse digests.

### 8.6 Correlations (stack risk carefully)
- EURUSD ↔ GBPUSD often rhyme; stacking both = 2× Europe risk.
- AUDUSD ↔ NZDUSD high correlation.
- USDJPY often tracks US yields + risk appetite.
- Never open multiple highly correlated ideas that blow daily heat.

---

## 9. Volatility regimes

- **ATR compression** (tight range, falling ATR): expect eventual expansion; fade extremes carefully; breakouts need confirmation (close + OF).
- **ATR expansion** (impulsive candles, wide spreads): trade *with* displacement; stops must respect structure; size down if stops widen.
- Session opens (London/NY) often expand; Asia often compresses into a range that London raids.

---

## 10. Session map (UTC-oriented)

Approximate (ignore DST edge cases; treat as windows, not guarantees):

| Window | UTC rough | HELIX use |
|--------|-----------|-----------|
| Asia | ~00:00–07:00 | Build range; mark Asia H/L as liquidity |
| London open / kill | ~07:00–10:00 | Raids Asia liquidity; sets daily direction often |
| London–NY overlap | ~12:00–16:00 | Highest liquidity for majors; preferred execution |
| NY afternoon | ~16:00–21:00 | Continuation or mean-reversion; watch US data |

**Judas / session fake:** early directional push that sweeps stops then reverses into true daily delivery — wait for reclaim + OF flip before chasing the first spike.

---

## 11. Confluence scoring (machine checklist)

Score +1 for each true item toward the trade direction:

1. HTF (D1/H4) bias agrees  
2. Order flow agrees (break/reject pattern)  
3. Location: discount for buys / premium for sells (or CRT neutralize setup)  
4. Clear DOL named (PDH/PDL, EQ, swing, FVG path)  
5. Session window favorable (London or London–NY for majors)  
6. News not conflicting / outside blackout  
7. EMA stack or structure BoS agrees  
8. Volatility not insane vs planned stop  

**HELIX gate:** buy/sell only if score **≥ 3** (prefer ≥ 4). Else **hold**.  
Confidence ≈ min(0.95, 0.35 + 0.1 × score) adjusted down for thin data.

---

## 12. Entry / invalidation / management

- **Invalidation** = structural failure (loss of HL for longs; loss of LH for shorts) or CRT opposite extreme beyond stop.
- Place stop beyond invalidation + small buffer (ATR fraction); size from that distance.
- Target 1: opposing IRL or EQ; Target 2: ERL / PDH-PDL / session extreme.
- Partial at T1; move stop to break-even only after structure confirms (not on noise).
- Trail only with structure (swing lows/highs), not arbitrary pip trails.

---

## 13. Psychology & circuit breakers (bot + human)

- After **2 consecutive full stop-outs** same day → hold remainder or cut size 50%.
- After daily loss cap → **hard flat**.
- No “make it back” trades. No size increase after a win streak beyond plan.
- Journal every decision: bias, OF, DOL, score, news, result.

---

## 14. What “world-class” actually means here

HELIX aims for **institutional process**, not mythical win rate:
- Risk survivability first  
- Explicit liquidity narrative  
- Multi-timeframe coherence  
- Session + macro awareness  
- Ruthless holds when edge is unclear  

There is **no** unbeatable bot. Edge = process × discipline × sample size on demo before live.

---

## 15. HELIX decision output discipline

Always state in rationale (short):
- Bias (HTF)  
- OF / location (premium-discount or CRT)  
- DOL  
- Why not hold (or why hold)  
- Risk note if relevant  

If any critical field is null/missing in snapshot → default **hold**.

---

## 16. Gold & oil (commodities)

- **XAUUSD (gold):** Treat as CFD/metal. Drivers: real yields, DXY, risk-off demand, geopolitics. Wider stops via ATR; never force FX pip math.
- **USOIL (WTI) / UKOIL (Brent):** Energy CFDs. Drivers: inventories, OPEC/geopolitics, USD. Trade only the symbol in the snapshot (do not swap WTI↔Brent mid-thesis).
- Exness symbols often use `m` suffix (`XAUUSDm`, `USOILm`) — brain outputs canonical names; EA matches suffixes.
- Same confluence ≥3 gate and risk caps as FX. Prefer hold when commodity news is one-sided and price has already spiked (chase risk).
