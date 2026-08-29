"""
4H Break of Structure (BOS) detection using fractal swing points.

A swing HIGH at index i = high[i] is the highest high within
[i-width, i+width] (classic fractal, width=2 => 5-candle fractal).
Same logic mirrored for swing LOWS.

BOS bullish = close breaks above the most recent confirmed swing high
BOS bearish = close breaks below the most recent confirmed swing low
"""

import pandas as pd
from config import FRACTAL_WIDTH


def find_swing_points(df: pd.DataFrame, width: int = FRACTAL_WIDTH):
    """
    Returns two lists of (index, price) tuples: swing_highs, swing_lows.
    Only fully confirmed fractals are returned (needs `width` candles on
    both sides, so the most recent `width` candles can never be confirmed
    swings yet — that's expected and correct, it prevents repainting).
    """
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    swing_highs = []
    swing_lows = []

    for i in range(width, n - width):
        window_high = highs[i - width: i + width + 1]
        if highs[i] == max(window_high):
            swing_highs.append((i, highs[i]))

        window_low = lows[i - width: i + width + 1]
        if lows[i] == min(window_low):
            swing_lows.append((i, lows[i]))

    return swing_highs, swing_lows


def detect_bos(df: pd.DataFrame, direction: str, after_time=None, width: int = FRACTAL_WIDTH):
    """
    direction: "bullish" or "bearish" — the direction we're looking to confirm
    (this comes from the daily bias; we only check BOS in that direction).

    after_time: a pandas Timestamp (or None). If given, only 4H candles with
    time >= after_time are eligible to count as the BOS confirmation. This
    is how we enforce "BOS must happen on today's daily candle, after
    yesterday's rejection" — pass today's daily open time in from bias_engine.

    Returns a dict for the FIRST eligible candle that confirms the break
    (earliest one today, not necessarily the very latest closed candle):
    {
        "broken_level": float,
        "broken_index": int,
        "confirming_close": float,
        "confirming_time": Timestamp
    }
    or None if no BOS has happened within the eligible window yet.
    """
    swing_highs, swing_lows = find_swing_points(df, width)
    n = len(df)

    if after_time is not None:
        eligible_indices = [i for i in range(n) if df.iloc[i]["time"] >= after_time]
    else:
        eligible_indices = [n - 1]  # fall back to old behavior: latest candle only

    if not eligible_indices:
        return None  # no 4H candles yet within today's window

    if direction not in ("bullish", "bearish"):
        raise ValueError("direction must be 'bullish' or 'bearish'")

    for idx in eligible_indices:
        candle = df.iloc[idx]

        if direction == "bullish":
            relevant_highs = [sh for sh in swing_highs if sh[0] < idx]
            if not relevant_highs:
                continue
            last_swing_idx, last_swing_price = relevant_highs[-1]
            if candle["close"] > last_swing_price:
                return {
                    "broken_level": last_swing_price,
                    "broken_index": last_swing_idx,
                    "confirming_close": candle["close"],
                    "confirming_time": candle["time"],
                }

        else:  # bearish
            relevant_lows = [sl for sl in swing_lows if sl[0] < idx]
            if not relevant_lows:
                continue
            last_swing_idx, last_swing_price = relevant_lows[-1]
            if candle["close"] < last_swing_price:
                return {
                    "broken_level": last_swing_price,
                    "broken_index": last_swing_idx,
                    "confirming_close": candle["close"],
                    "confirming_time": candle["time"],
                }

    return None
