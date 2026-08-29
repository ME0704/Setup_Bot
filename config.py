"""
Central configuration for the bot.
Tune thresholds here as you test — don't touch logic files for tuning.
"""

# Pairs the bot watches. Must match your MT5 Market Watch symbol names exactly.
PAIRS = [
    "GBPUSD.m",
    "USDJPY.m",
    "JP225.std",
    "XAUUSD.m",
    "UK100.std",
    "US30.std",
    "AUDJPY.m",
]

# --- Reference info only (not used in code logic) ---
# MT5 already gives each symbol its OWN correct candle close times based on
# that symbol's actual trading session — you don't need to configure close
# times anywhere, the bot reads them straight off each symbol's real data.
# This table is just so you know what to expect when alerts land:
#
#   Symbol       | Approx pip/point size      | 4H close pattern (server time)
#   -------------|-----------------------------|---------------------------------
#   GBPUSD.m     | 0.0001 (5th decimal)        | standard FX session boundaries
#   USDJPY.m     | 0.01   (3rd decimal, JPY)   | standard FX session boundaries
#   AUDJPY.m     | 0.01   (3rd decimal, JPY)   | standard FX session boundaries
#   XAUUSD.m     | 0.01   (gold, 2 decimals)   | closes ~1H after FX majors
#   JP225.std    | 1.0    (index points)       | closes ~1H after FX majors
#   UK100.std    | 1.0    (index points)       | standard/index session boundaries
#   US30.std     | 1.0    (index points)       | standard/index session boundaries
#
# Exact pip VALUE in your account currency depends on lot size and your
# account currency — check each symbol's "Specification" tab in MT5
# (right-click symbol in Market Watch -> Specification) for the precise figure.

# --- Broker server timezone calibration (REQUIRED for correct EAT display) ---
# MT5 candle timestamps are in your BROKER'S SERVER time, not UTC and not
# your local time. Set this to (server_time - UTC_time) in hours.
# How to find it: look at the clock bottom-right in your MT5 terminal,
# compare to actual current UTC time. Example: MT5 shows 15:00, UTC is
# 12:00 -> offset is +3. Update this if your broker shifts for DST.
BROKER_SERVER_UTC_OFFSET_HOURS = 3

# How many historical candles to pull each time (plenty of buffer for swing detection)
DAILY_LOOKBACK = 60
H4_LOOKBACK = 200

# --- Rejection detection tuning ---
# A candle counts as a "rejection" off a level if the wick on the level side
# is at least this many times the size of the body.
REJECTION_WICK_TO_BODY_RATIO = 1.5

# The level must be touched within this % of the candle's range from the wick tip
# (keeps us from counting a level that's nowhere near the actual wick)
# Values are in POINTS (as reported by MT5 symbol_info.point), not pips.
LEVEL_TOUCH_TOLERANCE_PIPS = {
    "default": 15,
    "XAUUSD.m": 150,
    "USDJPY.m": 15,
    "AUDJPY.m": 15,
    "JP225.std": 300,
    "UK100.std": 300,
    "US30.std": 300,
}

# --- Liquidity sweep tuning ---
# How far beyond the previous day's high/low price must poke to count as a sweep
# Values are in POINTS (as reported by MT5 symbol_info.point), not pips.
SWEEP_MIN_PIPS = {
    "default": 2,
    "XAUUSD.m": 50,
    "JP225.std": 100,
    "UK100.std": 100,
    "US30.std": 100,
}

# --- 4H structure (BOS) tuning ---
# Fractal width for swing high/low detection (2 = classic 5-candle fractal)
FRACTAL_WIDTH = 2

# --- Telegram ---
# Loaded from .env — see .env.example
TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"

# --- Loop timing ---
# How often (seconds) the bot checks for new candle closes / conditions.
# 60s is fine since we only act on candle CLOSE, not every tick.
POLL_INTERVAL_SECONDS = 60

LOG_FILE = "logs/alerts.csv"
