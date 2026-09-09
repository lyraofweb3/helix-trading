//+------------------------------------------------------------------+
//| HELIX.mq5                                                        |
//| HELIX trading bot for Exness MT5 (forex & stock CFDs)            |
//| Risk-managed trend EA + optional AI brain signal consumer        |
//|                                                                  |
//| This is NOT a no-loss system. Losing trades will happen.         |
//| Test on a DEMO account for weeks before any live money.          |
//|                                                                  |
//| AI SIGNALS (helix-brain)                                         |
//|  Brain writes signals/latest.json with:                          |
//|    action (buy|sell|hold), symbol, confidence, ts, rationale,    |
//|    stop_hint, take_hint, meta.provider                           |
//|  Copy that file into MT5 Common Files:                           |
//|    Terminal\Common\Files\HELIX\signals\latest.json               |
//|  Or per-terminal:                                                |
//|    Terminal\<ID>\MQL5\Files\HELIX\signals\latest.json            |
//|  Default input InpSignalFile = "HELIX\\signals\\latest.json"     |
//|  EA tries FILE_COMMON first, then local MQL5\Files.              |
//|  Use helix-brain/helix/mt5_bridge.py to sync on Windows.         |
//|                                                                  |
//| SignalMode Auto (default):                                       |
//|  If latest.json is fresh (age <= InpMaxSignalAgeSec) AND         |
//|  confidence >= InpMinConfidence AND action is buy/sell AND       |
//|  symbol matches chart → trade AI direction (still all risk       |
//|  gates). Else if InpUseRulesFallback → EMA trend rules.          |
//|  Hold / stale / low confidence → no AI trade (rules if allowed). |
//|                                                                  |
//| Install (Exness MT5 demo recommended first):                     |
//|  1. Open MT5 logged into your Exness demo account                |
//|  2. File -> Open Data Folder -> MQL5/Experts                     |
//|  3. Copy this file there                                         |
//|  4. Restart MT5 or right-click Navigator -> Refresh              |
//|  5. Compile in MetaEditor (F7)                                   |
//|  6. Tools -> Options -> Expert Advisors                          |
//|       enable "Allow algorithmic trading"                         |
//|  7. Drag EA onto a chart:                                        |
//|       Forex: EURUSD H1                                           |
//|       Stocks: open the stock CFD symbol your broker lists        |
//|               (e.g. AAPL, #AAPL, AAPL.m — names vary) on H1      |
//|  8. Enable AutoTrading (toolbar button must be green)            |
//|                                                                  |
//| Session hours are BROKER SERVER TIME. Align InpStSession*        |
//| / InpFxSession* to your Exness server timezone (often GMT+0 or   |
//| GMT+2/3). Defaults for stocks approximate US RTH on GMT+2.       |
//+------------------------------------------------------------------+
#property copyright "Personal use"
#property version   "1.20"
#property description "HELIX — AI-signal + EMA rules EA. Hard risk caps. Always SL. DEMO FIRST."

#include <Trade/Trade.mqh>

//--- symbol mode
enum ENUM_SYMBOL_MODE
  {
   SYMBOL_MODE_AUTO  = 0,  // Auto-detect from broker symbol
   SYMBOL_MODE_FOREX = 1,  // Force forex filters
   SYMBOL_MODE_STOCK = 2   // Force stock/CFD filters
  };

//--- signal / decision mode
enum ENUM_SIGNAL_MODE
  {
   SIGNAL_MODE_AUTO       = 0,  // AI if fresh+confident, else optional rules
   SIGNAL_MODE_RULES_ONLY = 1,  // EMA trend rules only (ignore AI file)
   SIGNAL_MODE_AI_ONLY    = 2   // AI signals only (no EMA fallback)
  };

//--- risk
input group "Risk — do not raise these on a small account"
input double InpRiskPercent        = 0.5;    // Risk per trade (% of equity)
input double InpMaxDailyLossPct    = 2.0;    // Stop trading if day is down this %
input int    InpMaxPositions       = 1;      // Max open positions for this EA
input int    InpMaxTradesPerDay    = 4;      // Cap on new entries per day
input double InpMinRR              = 1.5;    // Take-profit = SL distance * this

//--- AI brain signals
input group "AI brain signals"
input ENUM_SIGNAL_MODE InpSignalMode = SIGNAL_MODE_AUTO; // Auto / RulesOnly / AIOnly
input string InpSignalFile         = "HELIX\\signals\\latest.json"; // Under Common\\Files or MQL5\\Files
input double InpMinConfidence      = 0.65;   // Min AI confidence to act (0..1)
input int    InpMaxSignalAgeSec    = 300;    // Ignore signal older than this many seconds
input bool   InpUseRulesFallback   = true;   // Auto: use EMA rules when AI unusable

//--- forex filters (used when mode = Forex or Auto→forex)
input group "Forex filters"
input int    InpFxMaxSpreadPoints  = 25;     // Max spread in points (EURUSD 5-digit: 10-20 typical)
input bool   InpFxOnlyLiquidHours  = true;   // Trade London + NY only (server time)
input int    InpFxSessionStartHour = 7;      // ~London open on many Exness servers
input int    InpFxSessionEndHour   = 20;     // After NY afternoon
input bool   InpFxSkipFridayLate   = true;   // Skip late Friday
input int    InpFxFridayCutoffHour = 18;     // Friday cutoff hour (server time)
input bool   InpFxUseATRFilter     = true;   // Enable ATR filter
input double InpFxMinATRPoints     = 30;     // Skip dead markets
input double InpFxMaxATRPoints     = 400;    // Skip chaos / news spikes

//--- stock filters (used when mode = Stock or Auto→stock)
input group "Stock filters"
input int    InpStMaxSpreadPoints  = 500;    // Max spread in points (stock CFDs often hundreds)
input bool   InpStOnlyCashSession  = true;   // Trade US cash session only (server time)
input int    InpStSessionStartHour = 14;     // Approx US RTH open on GMT+2 brokers (14:30 → use 14)
input int    InpStSessionStartMin  = 30;     // Start minute (14:30). Align to YOUR server TZ!
input int    InpStSessionEndHour   = 20;     // Approx US RTH close on GMT+2 (21:00 → often 20–21)
input int    InpStSessionEndMin    = 0;      // End minute
input bool   InpStSkipFridayLate   = true;   // Skip late Friday
input int    InpStFridayCutoffHour = 19;     // Friday cutoff hour (server time)
input bool   InpStUseATRFilter     = true;   // Enable ATR filter
input double InpStMinATRPoints     = 50;     // Skip dead stock markets (wider than FX)
input double InpStMaxATRPoints     = 5000;   // Skip chaos / earnings spikes

//--- strategy
input group "Strategy (H1 trend + pullback)"
input ENUM_TIMEFRAMES InpTrendTF   = PERIOD_H1;
input int    InpFastEMA            = 21;
input int    InpSlowEMA            = 50;
input int    InpTrendEMA           = 200;
input int    InpATRPeriod          = 14;
input double InpSL_ATR_Mult        = 1.5;    // Stop distance = ATR * this
input int    InpRSIPeriod          = 14;
input int    InpRSIBuyMax          = 55;     // Buy only if RSI not already overbought
input int    InpRSISellMin         = 45;     // Sell only if RSI not already oversold

//--- execution
input group "Execution"
input ENUM_SYMBOL_MODE InpSymbolMode = SYMBOL_MODE_AUTO; // Auto / Forex / Stock
input ulong  InpMagic              = 26090801;
input int    InpSlippagePoints     = 20;
input int    InpMaxRetries         = 3;
input string InpTradeComment       = "HELIX";

CTrade trade;

datetime g_day_start = 0;
double   g_day_start_equity = 0;
int      g_trades_today = 0;
datetime g_last_bar = 0;

int h_fast=INVALID_HANDLE, h_slow=INVALID_HANDLE, h_trend=INVALID_HANDLE;
int h_atr=INVALID_HANDLE, h_rsi=INVALID_HANDLE;

bool g_is_stock = false;   // resolved mode after Auto/manual

// Parsed AI signal (filled by TryLoadAiSignal)
struct AiSignal
  {
   bool     loaded;       // file read + parse ok
   bool     usable;       // fresh, confident, buy/sell, symbol match
   string   action;       // buy|sell|hold|""
   string   symbol;
   double   confidence;
   string   ts_raw;
   datetime ts_gmt;       // 0 if unparsed
   int      age_sec;      // -1 unknown
   string   rationale;
   string   provider;
   string   reason;       // why not usable / status
  };

//+------------------------------------------------------------------+
//| Detect stock/CFD vs forex from broker symbol metadata            |
//+------------------------------------------------------------------+
bool DetectIsStock()
  {
   if(InpSymbolMode == SYMBOL_MODE_FOREX) return false;
   if(InpSymbolMode == SYMBOL_MODE_STOCK) return true;

   // Auto: prefer calc mode, then path hints
   long calc = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_CALC_MODE);
   // Stock / CFD / Futures / Exchange stock often indicate equities-like
   // Common stock/CFD calc modes (Exness US stocks are usually CFD / CFD leverage)
   if(calc == SYMBOL_CALC_MODE_CFD ||
      calc == SYMBOL_CALC_MODE_CFDLEVERAGE ||
      calc == SYMBOL_CALC_MODE_CFDINDEX ||
      calc == SYMBOL_CALC_MODE_EXCH_STOCKS ||
      calc == SYMBOL_CALC_MODE_FUTURES ||
      calc == SYMBOL_CALC_MODE_EXCH_FUTURES)
      return true;

   if(calc == SYMBOL_CALC_MODE_FOREX ||
      calc == SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE)
      return false;

   string path = "";
   string name = _Symbol;
   StringToLower(name);
   if(SymbolInfoString(_Symbol, SYMBOL_PATH, path))
     {
      StringToLower(path);
      if(StringFind(path, "stock") >= 0 ||
         StringFind(path, "share") >= 0 ||
         StringFind(path, "equity") >= 0 ||
         (StringFind(path, "cfd") >= 0 && StringFind(path, "forex") < 0))
         return true;
      if(StringFind(path, "forex") >= 0 ||
         StringFind(path, "fx") >= 0 ||
         StringFind(path, "currenc") >= 0)
         return false;
     }

   // Weak name heuristics (Exness often uses AAPL, #AAPL, AAPL.m, US100 etc.)
   if(StringFind(name, "aapl") >= 0 || StringFind(name, "msft") >= 0 ||
      StringFind(name, "tsla") >= 0 || StringFind(name, "amzn") >= 0 ||
      StringFind(name, "nvda") >= 0 || StringFind(name, "googl") >= 0 ||
      StringFind(name, "meta") >= 0 || StringFind(name, "us500") >= 0 ||
      StringFind(name, "us100") >= 0 || StringFind(name, "ustec") >= 0)
      return true;

   return false; // default to forex filters if unknown
  }

//+------------------------------------------------------------------+
//| Minimal JSON string field extractor (no nested objects)          |
//+------------------------------------------------------------------+
string JsonExtractString(const string json, const string key)
  {
   // Match "key" : "value"  (value may be empty; stops at unescaped ")
   string pat = "\"" + key + "\"";
   int p = StringFind(json, pat);
   if(p < 0) return "";
   int colon = StringFind(json, ":", p + StringLen(pat));
   if(colon < 0) return "";
   int i = colon + 1;
   int n = StringLen(json);
   while(i < n)
     {
      ushort c = StringGetCharacter(json, i);
      if(c==' ' || c=='\t' || c=='\r' || c=='\n') { i++; continue; }
      break;
     }
   if(i >= n) return "";
   // null
   if(StringFind(json, "null", i) == i)
      return "";
   if(StringGetCharacter(json, i) != '"')
      return ""; // non-string
   i++;
   string out = "";
   while(i < n)
     {
      ushort c = StringGetCharacter(json, i);
      if(c == '\\' && i + 1 < n)
        {
         ushort nch = StringGetCharacter(json, i + 1);
         out += ShortToString(nch);
         i += 2;
         continue;
        }
      if(c == '"') break;
      out += ShortToString(c);
      i++;
     }
   return out;
  }

//+------------------------------------------------------------------+
double JsonExtractNumber(const string json, const string key)
  {
   string pat = "\"" + key + "\"";
   int p = StringFind(json, pat);
   if(p < 0) return 0.0;
   int colon = StringFind(json, ":", p + StringLen(pat));
   if(colon < 0) return 0.0;
   int i = colon + 1;
   int n = StringLen(json);
   while(i < n)
     {
      ushort c = StringGetCharacter(json, i);
      if(c==' ' || c=='\t' || c=='\r' || c=='\n') { i++; continue; }
      break;
     }
   string num = "";
   while(i < n)
     {
      ushort c = StringGetCharacter(json, i);
      if((c>='0' && c<='9') || c=='.' || c=='-' || c=='+' || c=='e' || c=='E')
        {
         num += ShortToString(c);
         i++;
         continue;
        }
      break;
     }
   if(StringLen(num) == 0) return 0.0;
   return StringToDouble(num);
  }

//+------------------------------------------------------------------+
//| Parse ISO-8601-ish UTC timestamp → datetime (GMT). Returns 0 fail|
//| Accepts: 2026-09-09T10:11:31... or 2026-09-09 10:11:31           |
//+------------------------------------------------------------------+
datetime ParseIsoUtc(const string ts)
  {
   if(StringLen(ts) < 19) return 0;
   // Build "YYYY.MM.DD HH:MM:SS"
   string y = StringSubstr(ts, 0, 4);
   string mo = StringSubstr(ts, 5, 2);
   string d = StringSubstr(ts, 8, 2);
   string h = StringSubstr(ts, 11, 2);
   string mi = StringSubstr(ts, 14, 2);
   string s = StringSubstr(ts, 17, 2);
   string norm = y + "." + mo + "." + d + " " + h + ":" + mi + ":" + s;
   datetime t = StringToTime(norm);
   // StringToTime uses local/server interpretation; we treat signal ts as UTC
   // and compare against TimeGMT(). Offset between broker and GMT is absorbed
   // by using TimeGMT() for age when possible; if broker TZ != UTC the age
   // may be skewed by hours — prefer file mtime as secondary check.
   return t;
  }

//+------------------------------------------------------------------+
bool SymbolMatchesSignal(const string sig_symbol)
  {
   if(StringLen(sig_symbol) == 0) return false;
   string chart = _Symbol;
   string sig = sig_symbol;
   StringToUpper(chart);
   StringToUpper(sig);
   // Strip common prefixes
   if(StringGetCharacter(chart, 0) == '#')
      chart = StringSubstr(chart, 1);
   if(StringGetCharacter(sig, 0) == '#')
      sig = StringSubstr(sig, 1);
   if(chart == sig) return true;
   // Chart may have broker suffix: EURUSD.m, EURUSDm, EURUSD_i
   if(StringFind(chart, sig) == 0 && StringLen(chart) >= StringLen(sig))
     {
      if(StringLen(chart) == StringLen(sig)) return true;
      ushort next = StringGetCharacter(chart, StringLen(sig));
      // suffix starts with non-letter often, or trailing letter like 'm'
      if(!(next >= 'A' && next <= 'Z') || next == 'M' || StringLen(chart) <= StringLen(sig) + 3)
         return true;
     }
   // Signal longer than chart (unlikely) — also allow chart as prefix of sig
   if(StringFind(sig, chart) == 0) return true;
   return false;
  }

//+------------------------------------------------------------------+
bool ReadSignalFile(string &out_json, datetime &out_mtime)
  {
   out_json = "";
   out_mtime = 0;
   // Prefer Common\Files (shared across terminals) then local MQL5\Files
   int flags[2];
   flags[0] = FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON;
   flags[1] = FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ;

   for(int f=0; f<2; f++)
     {
      int h = FileOpen(InpSignalFile, flags[f]);
      if(h == INVALID_HANDLE)
         continue;
      datetime mtime = (datetime)FileGetInteger(h, FILE_MODIFY_DATE);
      string body = "";
      while(!FileIsEnding(h))
        {
         string line = FileReadString(h);
         body += line;
         if(!FileIsEnding(h))
            body += "\n";
        }
      FileClose(h);
      if(StringLen(body) > 0)
        {
         out_json = body;
         out_mtime = mtime;
         return true;
        }
     }
   return false;
  }

//+------------------------------------------------------------------+
void TryLoadAiSignal(AiSignal &sig)
  {
   sig.loaded = false;
   sig.usable = false;
   sig.action = "";
   sig.symbol = "";
   sig.confidence = 0;
   sig.ts_raw = "";
   sig.ts_gmt = 0;
   sig.age_sec = -1;
   sig.rationale = "";
   sig.provider = "";
   sig.reason = "no file";

   string json;
   datetime file_mtime = 0;
   if(!ReadSignalFile(json, file_mtime))
     {
      sig.reason = "signal file not found (Common or local Files): " + InpSignalFile;
      return;
     }

   sig.loaded = true;
   sig.action     = JsonExtractString(json, "action");
   StringToLower(sig.action);
   sig.symbol     = JsonExtractString(json, "symbol");
   sig.confidence = JsonExtractNumber(json, "confidence");
   sig.ts_raw     = JsonExtractString(json, "ts");
   sig.rationale  = JsonExtractString(json, "rationale");
   sig.provider   = JsonExtractString(json, "provider"); // may be nested under meta
   if(StringLen(sig.provider) == 0)
     {
      // meta.provider — crude: find "provider" after "meta"
      int meta_pos = StringFind(json, "\"meta\"");
      if(meta_pos >= 0)
        {
         string meta_slice = StringSubstr(json, meta_pos);
         sig.provider = JsonExtractString(meta_slice, "provider");
        }
     }

   // Prefer file mtime for age (avoids ISO/broker TZ skew); fall back to ts vs TimeGMT
   datetime now_local = TimeLocal();
   if(file_mtime > 0 && now_local > 0)
     {
      sig.age_sec = (int)(now_local - file_mtime);
      if(sig.age_sec < 0) sig.age_sec = 0;
     }
   else
     {
      sig.ts_gmt = ParseIsoUtc(sig.ts_raw);
      datetime now_gmt = TimeGMT();
      if(sig.ts_gmt > 0 && now_gmt > 0)
        {
         sig.age_sec = (int)(now_gmt - sig.ts_gmt);
         if(sig.age_sec < -120)
            sig.age_sec = (int)(TimeCurrent() - sig.ts_gmt);
         if(sig.age_sec < 0) sig.age_sec = 0;
        }
     }

   if(sig.action != "buy" && sig.action != "sell" && sig.action != "hold")
     {
      sig.reason = "bad action: " + sig.action;
      return;
     }
   if(sig.action == "hold")
     {
      sig.reason = "action=hold (ignored)";
      return;
     }
   if(sig.confidence < InpMinConfidence)
     {
      sig.reason = StringFormat("confidence %.2f < min %.2f", sig.confidence, InpMinConfidence);
      return;
     }
   if(sig.age_sec < 0)
     {
      sig.reason = "could not parse ts age; refusing stale-unknown signal";
      return;
     }
   if(sig.age_sec > InpMaxSignalAgeSec)
     {
      sig.reason = StringFormat("signal age %ds > max %ds (stale)", sig.age_sec, InpMaxSignalAgeSec);
      return;
     }
   if(!SymbolMatchesSignal(sig.symbol))
     {
      sig.reason = "symbol mismatch signal=" + sig.symbol + " chart=" + _Symbol;
      return;
     }

   sig.usable = true;
   sig.reason = "ok";
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpRiskPercent <= 0 || InpRiskPercent > 2.0)
     {
      Print("Refusing to start: RiskPercent must be between 0 and 2.");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpMinConfidence < 0.0 || InpMinConfidence > 1.0)
     {
      Print("Refusing to start: InpMinConfidence must be 0..1.");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpMaxSignalAgeSec < 30)
     {
      Print("Refusing to start: InpMaxSignalAgeSec must be >= 30.");
      return INIT_PARAMETERS_INCORRECT;
     }

   g_is_stock = DetectIsStock();

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.LogLevel(LOG_LEVEL_ERRORS);

   h_fast  = iMA(_Symbol, InpTrendTF, InpFastEMA, 0, MODE_EMA, PRICE_CLOSE);
   h_slow  = iMA(_Symbol, InpTrendTF, InpSlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   h_trend = iMA(_Symbol, InpTrendTF, InpTrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   h_atr   = iATR(_Symbol, InpTrendTF, InpATRPeriod);
   h_rsi   = iRSI(_Symbol, InpTrendTF, InpRSIPeriod, PRICE_CLOSE);

   if(h_fast==INVALID_HANDLE || h_slow==INVALID_HANDLE || h_trend==INVALID_HANDLE
      || h_atr==INVALID_HANDLE || h_rsi==INVALID_HANDLE)
     {
      Print("Indicator handle failed.");
      return INIT_FAILED;
     }

   ResetDayIfNeeded();

   string mode_str = g_is_stock ? "STOCK/CFD" : "FOREX";
   string mode_src = (InpSymbolMode==SYMBOL_MODE_AUTO) ? "Auto" :
                     (InpSymbolMode==SYMBOL_MODE_FOREX) ? "Forced Forex" : "Forced Stock";
   string sig_mode = (InpSignalMode==SIGNAL_MODE_AUTO) ? "Auto" :
                     (InpSignalMode==SIGNAL_MODE_RULES_ONLY) ? "RulesOnly" : "AIOnly";
   long calc = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_CALC_MODE);
   Print("HELIX started on ", _Symbol, " ", EnumToString(InpTrendTF),
         " | mode=", mode_str, " (", mode_src, ")",
         " | signalMode=", sig_mode,
         " | calc_mode=", calc,
         " | risk=", DoubleToString(InpRiskPercent,2), "%",
         " | maxDailyLoss=", DoubleToString(InpMaxDailyLossPct,2), "%",
         " | maxPos=", InpMaxPositions,
         " | maxTrades/day=", InpMaxTradesPerDay,
         " | RR=", DoubleToString(InpMinRR,2));
   Print("AI signal file=", InpSignalFile,
         " minConf=", DoubleToString(InpMinConfidence,2),
         " maxAgeSec=", InpMaxSignalAgeSec,
         " rulesFallback=", InpUseRulesFallback ? "yes" : "no");
   Print("Place latest.json under Terminal\\Common\\Files\\", InpSignalFile,
         " (or MQL5\\Files\\...). See helix-brain mt5_bridge.py");
   if(g_is_stock)
      Print("Stock filters: maxSpread=", InpStMaxSpreadPoints,
            " session=", InpStSessionStartHour, ":",
            StringFormat("%02d", InpStSessionStartMin), "-",
            InpStSessionEndHour, ":",
            StringFormat("%02d", InpStSessionEndMin),
            " (BROKER SERVER TIME — align to your Exness TZ)",
            " ATR min/max=", InpStMinATRPoints, "/", InpStMaxATRPoints);
   else
      Print("Forex filters: maxSpread=", InpFxMaxSpreadPoints,
            " session=", InpFxSessionStartHour, "-", InpFxSessionEndHour,
            " (broker server time)",
            " ATR min/max=", InpFxMinATRPoints, "/", InpFxMaxATRPoints);

   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(h_fast!=INVALID_HANDLE)  IndicatorRelease(h_fast);
   if(h_slow!=INVALID_HANDLE)  IndicatorRelease(h_slow);
   if(h_trend!=INVALID_HANDLE) IndicatorRelease(h_trend);
   if(h_atr!=INVALID_HANDLE)   IndicatorRelease(h_atr);
   if(h_rsi!=INVALID_HANDLE)   IndicatorRelease(h_rsi);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)) return;
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED)) return;
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)) return;
   if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT)) return;

   ResetDayIfNeeded();
   if(DailyLossHit()) return;

   // New-bar logic so we do not spam orders every tick
   datetime bar = iTime(_Symbol, InpTrendTF, 0);
   if(bar == g_last_bar) return;
   g_last_bar = bar;

   if(!SessionOk()) return;
   if(!SpreadOk()) return;
   if(CountOurPositions() >= InpMaxPositions) return;
   if(g_trades_today >= InpMaxTradesPerDay) return;

   double ema_f[], ema_s[], ema_t[], atr[], rsi[];
   ArraySetAsSeries(ema_f,true); ArraySetAsSeries(ema_s,true);
   ArraySetAsSeries(ema_t,true); ArraySetAsSeries(atr,true); ArraySetAsSeries(rsi,true);

   if(CopyBuffer(h_fast,0,0,4,ema_f)<4) return;
   if(CopyBuffer(h_slow,0,0,4,ema_s)<4) return;
   if(CopyBuffer(h_trend,0,0,4,ema_t)<4) return;
   if(CopyBuffer(h_atr,0,0,4,atr)<4) return;
   if(CopyBuffer(h_rsi,0,0,4,rsi)<4) return;

   double close1 = iClose(_Symbol, InpTrendTF, 1);
   if(close1<=0 || atr[1]<=0) return;

   double atr_pts = atr[1] / _Point;
   if(!AtrOk(atr_pts)) return;

   double sl_dist = atr[1] * InpSL_ATR_Mult;
   if(sl_dist <= 0) return;

   //----- Decision: AI and/or rules -----
   bool want_buy = false;
   bool want_sell = false;
   string src = "";

   if(InpSignalMode != SIGNAL_MODE_RULES_ONLY)
     {
      AiSignal ai;
      TryLoadAiSignal(ai);
      if(ai.usable)
        {
         if(ai.action == "buy")  { want_buy = true;  src = "AI"; }
         if(ai.action == "sell") { want_sell = true; src = "AI"; }
         Print("AI signal usable: ", ai.action, " conf=", DoubleToString(ai.confidence,2),
               " age=", ai.age_sec, "s provider=", ai.provider,
               " | ", ai.rationale);
        }
      else
        {
         static datetime last_ai_log = 0;
         if(TimeCurrent() - last_ai_log > 300)
           {
            Print("AI signal not used: ", ai.reason);
            last_ai_log = TimeCurrent();
           }
        }
     }

   bool allow_rules = false;
   if(InpSignalMode == SIGNAL_MODE_RULES_ONLY)
      allow_rules = true;
   else if(InpSignalMode == SIGNAL_MODE_AUTO && !want_buy && !want_sell && InpUseRulesFallback)
      allow_rules = true;
   // AIOnly: never rules

   if(allow_rules && !want_buy && !want_sell)
     {
      bool uptrend   = (close1 > ema_t[1] && ema_f[1] > ema_s[1] && ema_s[1] > ema_t[1]);
      bool downtrend = (close1 < ema_t[1] && ema_f[1] < ema_s[1] && ema_s[1] < ema_t[1]);
      bool cross_up   = (ema_f[2] <= ema_s[2] && ema_f[1] > ema_s[1]);
      bool cross_down = (ema_f[2] >= ema_s[2] && ema_f[1] < ema_s[1]);

      if(uptrend && cross_up && rsi[1] < InpRSIBuyMax)
        { want_buy = true; src = "Rules"; }
      else if(downtrend && cross_down && rsi[1] > InpRSISellMin)
        { want_sell = true; src = "Rules"; }
     }

   if(want_buy)
      OpenTrade(ORDER_TYPE_BUY, sl_dist, src);
   else if(want_sell)
      OpenTrade(ORDER_TYPE_SELL, sl_dist, src);
  }

//+------------------------------------------------------------------+
bool AtrOk(double atr_pts)
  {
   bool use_filter = g_is_stock ? InpStUseATRFilter : InpFxUseATRFilter;
   if(!use_filter) return true;
   double mn = g_is_stock ? InpStMinATRPoints : InpFxMinATRPoints;
   double mx = g_is_stock ? InpStMaxATRPoints : InpFxMaxATRPoints;
   if(atr_pts < mn) return false;
   if(atr_pts > mx) return false;
   return true;
  }

//+------------------------------------------------------------------+
void OpenTrade(ENUM_ORDER_TYPE type, double sl_distance, const string source="")
  {
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask<=0 || bid<=0) return;

   double sl, tp, price;
   if(type==ORDER_TYPE_BUY)
     {
      price = ask;
      sl = price - sl_distance;
      tp = price + sl_distance * InpMinRR;
     }
   else
     {
      price = bid;
      sl = price + sl_distance;
      tp = price - sl_distance * InpMinRR;
     }

   sl = NormalizePrice(sl);
   tp = NormalizePrice(tp);

   if(!StopsValid(type, price, sl, tp))
     {
      Print("Stops rejected by broker stop-level. Skip.");
      return;
     }

   double lots = LotsFromRisk(sl_distance);
   if(lots <= 0)
     {
      Print("Lot size came out 0. Account too small for this stop distance.");
      return;
     }

   string comment = InpTradeComment;
   if(StringLen(source) > 0)
      comment = InpTradeComment + " " + source;

   bool ok=false;
   for(int i=0;i<InpMaxRetries && !ok;i++)
     {
      if(type==ORDER_TYPE_BUY)
         ok = trade.Buy(lots, _Symbol, 0.0, sl, tp, comment);
      else
         ok = trade.Sell(lots, _Symbol, 0.0, sl, tp, comment);
      if(!ok)
         Print("Order failed: ", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
     }

   if(ok)
     {
      g_trades_today++;
      Print("Opened ", EnumToString(type), " lots=", DoubleToString(lots,2),
            " sl=", DoubleToString(sl,_Digits), " tp=", DoubleToString(tp,_Digits),
            " src=", source);
     }
  }

//+------------------------------------------------------------------+
double LotsFromRisk(double sl_distance)
  {
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double risk_money = equity * InpRiskPercent / 100.0;
   if(risk_money <= 0) return 0;

   double tick_size  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double vol_min    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vol_max    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vol_step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(tick_size<=0 || tick_value<=0 || vol_step<=0) return 0;

   double ticks = sl_distance / tick_size;
   if(ticks <= 0) return 0;

   double lots = risk_money / (ticks * tick_value);
   lots = MathFloor(lots / vol_step) * vol_step;
   if(lots < vol_min) return 0;
   if(lots > vol_max) lots = vol_max;

   // Extra cap: never use more than 20% of free margin on one trade
   double margin=0;
   ENUM_ORDER_TYPE dummy = ORDER_TYPE_BUY;
   if(OrderCalcMargin(dummy, _Symbol, lots, SymbolInfoDouble(_Symbol,SYMBOL_ASK), margin))
     {
      double free = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      if(margin > 0 && free > 0 && margin > free * 0.20)
        {
         lots = lots * (free * 0.20 / margin);
         lots = MathFloor(lots / vol_step) * vol_step;
         if(lots < vol_min) return 0;
        }
     }
   return NormalizeDouble(lots, 2);
  }

//+------------------------------------------------------------------+
bool StopsValid(ENUM_ORDER_TYPE type, double price, double sl, double tp)
  {
   long stops_lvl = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double min_dist = stops_lvl * _Point;
   if(type==ORDER_TYPE_BUY)
     {
      if(price - sl < min_dist) return false;
      if(tp - price < min_dist) return false;
     }
   else
     {
      if(sl - price < min_dist) return false;
      if(price - tp < min_dist) return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
double NormalizePrice(double p)
  {
   double tick = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick<=0) return NormalizeDouble(p, _Digits);
   return NormalizeDouble(MathRound(p/tick)*tick, _Digits);
  }

//+------------------------------------------------------------------+
int CountOurPositions()
  {
   int n=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket==0) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      n++;
     }
   return n;
  }

//+------------------------------------------------------------------+
bool SpreadOk()
  {
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   int max_sp = g_is_stock ? InpStMaxSpreadPoints : InpFxMaxSpreadPoints;
   if(spread > max_sp) return false;
   return true;
  }

//+------------------------------------------------------------------+
bool SessionOk()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);   // broker server time

   if(dt.day_of_week==0 || dt.day_of_week==6) return false;

   if(g_is_stock)
     {
      if(InpStSkipFridayLate && dt.day_of_week==5 && dt.hour>=InpStFridayCutoffHour)
         return false;
      if(!InpStOnlyCashSession) return true;

      int now_min  = dt.hour * 60 + dt.min;
      int start_m  = InpStSessionStartHour * 60 + InpStSessionStartMin;
      int end_m    = InpStSessionEndHour * 60 + InpStSessionEndMin;
      if(now_min < start_m) return false;
      if(now_min >= end_m) return false;
      return true;
     }

   // Forex path (original behaviour)
   if(InpFxSkipFridayLate && dt.day_of_week==5 && dt.hour>=InpFxFridayCutoffHour)
      return false;
   if(!InpFxOnlyLiquidHours) return true;
   if(dt.hour < InpFxSessionStartHour) return false;
   if(dt.hour >= InpFxSessionEndHour) return false;
   return true;
  }

//+------------------------------------------------------------------+
void ResetDayIfNeeded()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   datetime start = StringToTime(StringFormat("%04d.%02d.%02d 00:00:00", dt.year, dt.mon, dt.day));
   if(start != g_day_start)
     {
      g_day_start = start;
      g_day_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
      g_trades_today = 0;
     }
  }

//+------------------------------------------------------------------+
bool DailyLossHit()
  {
   if(g_day_start_equity <= 0) return false;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double dd = (g_day_start_equity - eq) / g_day_start_equity * 100.0;
   if(dd >= InpMaxDailyLossPct)
     {
      static datetime last_warn=0;
      if(TimeCurrent()-last_warn > 3600)
        {
         Print("Daily loss cap hit (", DoubleToString(dd,2), "%). No new trades today.");
         last_warn = TimeCurrent();
        }
      return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   // reserved for later journal / state
  }
//+------------------------------------------------------------------+
