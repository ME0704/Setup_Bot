# Forex Bias/BOS Telegram Bot

Watches your pairs on MT5 (forex.com feed) and alerts you when:

**Mandatory (fires the alert):**
1. **Prior day rejected off a daily key level** (Support, Resistance, Daily Open, or Prior Close)
2. **4H breaks structure** in that same direction — and that break must happen on **today's** daily candle, after yesterday's rejection was already valid (a stale break from before the rejection doesn't count)

**Top-up (upgrades the setup, not required):**
3. **Today's candle swept the prior day's high or low** in the matching direction (liquidity grab) → marks the alert as **A+**

So you'll get alerted on rejection + BOS alone (grade **A**), and if the liquidity sweep also lines up, it's flagged **⭐ A+** in the message. Either way, you go find your own entry, same as your current process.

## Setup (local PC, Windows)

1. Install Python 3.10+ from python.org (check "Add to PATH" during install)
2. Open this folder in a terminal (PowerShell or CMD) and run:
   ```
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your real Telegram bot token + chat ID:
   ```
   copy .env.example .env
   ```
   Then edit `.env` with notepad.
4. Make sure MT5 is open and logged into your forex.com account.
5. Check `config.py` — confirm the symbol names in `PAIRS` match exactly what's in your MT5 Market Watch (some brokers add suffixes).
6. Run it:
   ```
   python main.py
   ```

It will print status to the console and only message Telegram when a full setup confirms.

## File map

| File | What it does |
|---|---|
| `config.py` | All your tunable settings — pairs, thresholds, timing |
| `data_feed.py` | Pulls candles from your MT5 terminal |
| `key_levels.py` | Builds the daily key-level list (S/R, Open, Prior Close) |
| `rejection.py` | Checks if prior day rejected off a key level |
| `liquidity.py` | Checks if today swept prior day's high/low |
| `structure.py` | Detects 4H break of structure via swing points |
| `bias_engine.py` | Combines all of the above into one pass/fail per pair |
| `alert.py` | Formats + sends the Telegram message, logs to CSV |
| `main.py` | The loop — run this file |
| `logs/alerts.csv` | Every alert ever fired, for your own review/backtesting |

## Tuning notes

- **Key levels currently use classic pivot formula (Pivot/R1/S1) + Prior Day H/L + Daily Open + Prior Close.** If you draw S/R manually and it differs from pivots, swap the logic in `key_levels.py` — everything downstream just needs a `{label: price}` dict, so you could hardcode your own levels per pair if you want full manual control while testing.
- **`REJECTION_WICK_TO_BODY_RATIO`** (config.py) controls how "sharp" a rejection wick needs to be. Raise it if you're getting too many weak signals, lower it if you're missing real rejections.
- **`SWEEP_MIN_PIPS`** controls how far past the prior day's high/low price needs to travel to count as a genuine sweep (vs. just barely touching it).
- **`FRACTAL_WIDTH`** controls how "significant" a 4H swing point needs to be before a break of it counts as BOS. 2 = standard 5-candle fractal. Raise to 3 for stricter/more major structure only.

## Known limitations to keep in mind while testing

- Rejection + sweep only checked once per day; if today's candle later stops sweeping (rare, would need a redraw), the bot won't un-fire — it's a one-shot check per candle cycle.
- BOS detection uses **closed 4H candles only** — no intra-candle repainting, but it does mean confirmation lands on the 4H close, not mid-candle.
- No entry logic is included on purpose — you said you want to eyeball entries yourself, so the bot's job stops at "bias + BOS confirmed."
- This is unweighted logic: rejection wick + sweep + BOS are all-or-nothing gates, not a scored/weighted system. If you find you want "the BOS was really strong" vs "barely broke" nuance later, that's a natural next iteration.
