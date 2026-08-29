"""
Combines your rule set into one pass per pair:

MANDATORY (setup fires without these, no alert):
1. Prior day rejected off a daily key level              -> rejection.py
2. 4H breaks structure in that same direction, on TODAY'S -> structure.py
   daily candle (not before the rejection was valid)

TOP-UP (optional, upgrades grade but not required to fire):
3. Today's candle swept prior day's high/low in the         -> liquidity.py
   direction that agrees with the rejection

Grading:
- Rejection + BOS only                     -> grade "A"
- Rejection + BOS + matching sweep         -> grade "A+"

Sweep direction agreement (same logic as before, just no longer a gate):
- Rejection "bullish" (rejected UP off a level) agrees with a sweep of
  the prior day's LOW
- Rejection "bearish" (rejected DOWN off a level) agrees with a sweep of
  the prior day's HIGH
If a sweep happened but in the WRONG direction relative to the rejection,
it does not count toward the A+ upgrade (treated as no sweep, not a conflict).
"""

import data_feed
import key_levels
import rejection
import liquidity
import structure
from config import DAILY_LOOKBACK, H4_LOOKBACK


def evaluate_pair(symbol: str):
    """
    Runs the full check for one symbol.
    Returns an alert dict if the mandatory conditions (rejection + BOS) align,
    else None. Includes a "grade" field: "A" or "A+".
    """
    point = data_feed.symbol_point(symbol)
    digits = data_feed.symbol_digits(symbol)

    daily_df = data_feed.get_candles(symbol, "D1", DAILY_LOOKBACK)
    levels = key_levels.get_daily_key_levels(daily_df)

    prior_day = daily_df.iloc[-2]
    today = daily_df.iloc[-1]

    rej = rejection.detect_rejection(prior_day, levels, symbol, point)
    if rej is None:
        return None  # no valid rejection off any key level yesterday

    daily_bias = rej["direction"]  # "bullish" or "bearish"

    # --- 4H BOS confirmation (mandatory) ---
    # Only ever looks at FULLY CLOSED 4H candles (get_closed_candles drops the
    # live/forming one) — this is what makes sure we never alert mid-candle.
    # Must happen on/after TODAY's daily candle opened — i.e. after yesterday's
    # rejection was already in place.
    h4_df = data_feed.get_closed_candles(symbol, "H4", H4_LOOKBACK)
    today_open_time = today["time"]
    bos = structure.detect_bos(h4_df, daily_bias, after_time=today_open_time)
    if bos is None:
        return None  # bias is set, but 4H hasn't closed a BOS candle TODAY yet

    # --- Liquidity sweep (optional top-up, checked but never blocks) ---
    swept = liquidity.detect_sweep(today, prior_day, symbol, point)

    sweep_agrees = (
        (daily_bias == "bullish" and swept == "low") or
        (daily_bias == "bearish" and swept == "high")
    )

    grade = "A+" if sweep_agrees else "A"

    return {
        "symbol": symbol,
        "bias": daily_bias,
        "grade": grade,
        "digits": digits,
        "rejection_level": rej["level_label"],
        "rejection_price": rej["level_price"],
        "rejection_time": prior_day["time"],
        "swept": swept if sweep_agrees else None,
        "prior_day_high": prior_day["high"],
        "prior_day_low": prior_day["low"],
        "bos_broken_level": bos["broken_level"],
        "bos_confirming_close": bos["confirming_close"],
        "bos_time": bos["confirming_time"],
    }
