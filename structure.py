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


def _find_transition_events(df: pd.DataFrame, direction: str, width: int = FRACTAL_WIDTH):
    """
    Finds every candle where price FIRST crosses its relevant swing level —
    i.e. this candle's close is beyond the level, but the immediately
    PRIOR candle's close was not (relative to that same swing level).

    This is the actual "break of structure" event. Without this check, a
    persistent trend would re-qualify as a "break" on every single candle
    that simply continues past a level broken days earlier — which is not
    a fresh structure break, just continuation.
    """
    swing_highs, swing_lows = find_swing_points(df, width)
    n = len(df)
    events = []

    def relevant_swing(swings, idx):
        candidates = [s for s in swings if s[0] < idx]
        return candidates[-1] if candidates else None

    for i in range(1, n):
        if direction == "bullish":
            curr = relevant_swing(swing_highs, i)
            if curr is None:
                continue
            curr_idx, curr_price = curr
            close_i = df.iloc[i]["close"]
            close_prev = df.iloc[i - 1]["close"]

            prev = relevant_swing(swing_highs, i - 1)
            prev_broken = prev is not None and close_prev > prev[1]

            if close_i > curr_price and not prev_broken:
                events.append({
                    "broken_level": curr_price,
                    "broken_index": curr_idx,
                    "confirming_close": close_i,
                    "confirming_time": df.iloc[i]["time"],
                })

        elif direction == "bearish":
            curr = relevant_swing(swing_lows, i)
            if curr is None:
                continue
            curr_idx, curr_price = curr
            close_i = df.iloc[i]["close"]
            close_prev = df.iloc[i - 1]["close"]

            prev = relevant_swing(swing_lows, i - 1)
            prev_broken = prev is not None and close_prev < prev[1]

            if close_i < curr_price and not prev_broken:
                events.append({
                    "broken_level": curr_price,
                    "broken_index": curr_idx,
                    "confirming_close": close_i,
                    "confirming_time": df.iloc[i]["time"],
                })

        else:
            raise ValueError("direction must be 'bullish' or 'bearish'")

    return events


def detect_bos(df: pd.DataFrame, direction: str, after_time=None, width: int = FRACTAL_WIDTH):
    """
    direction: "bullish" or "bearish" — the direction we're looking to confirm
    (this comes from the daily bias; we only check BOS in that direction).

    after_time: a pandas Timestamp (or None). Finds the most recent FRESH
    break-of-structure event (the candle where price first crossed the
    relevant swing level — not just any candle sitting beyond it). If that
    event happened before after_time, it's treated as stale/old news and
    this returns None — this is what stops a break from last week firing
    an alert today just because price is still trending in that direction.

    Returns:
    {
        "broken_level": float,
        "broken_index": int,
        "confirming_close": float,
        "confirming_time": Timestamp
    }
    or None if no fresh BOS event exists within the eligible window.
    """
    if direction not in ("bullish", "bearish"):
        raise ValueError("direction must be 'bullish' or 'bearish'")

    events = _find_transition_events(df, direction, width)
    if not events:
        return None

    latest_event = events[-1]  # most recent fresh break, anywhere in the lookback

    if after_time is not None and latest_event["confirming_time"] < after_time:
        return None  # the real break happened before today — stale, don't alert

    return latest_event


def determine_trend(df: pd.DataFrame, width: int = FRACTAL_WIDTH):
    """
    Determines the CURRENT trend on whatever timeframe df represents, by
    finding whichever break-of-structure event — bullish or bearish —
    happened most recently. That direction IS the current trend.

    Returns (direction, event_dict) where direction is "bullish"/"bearish",
    or (None, None) if no structure break has occurred yet in this lookback
    (e.g. not enough history, or price has never broken any swing point).
    """
    bull_events = _find_transition_events(df, "bullish", width)
    bear_events = _find_transition_events(df, "bearish", width)

    last_bull = bull_events[-1] if bull_events else None
    last_bear = bear_events[-1] if bear_events else None

    if last_bull is None and last_bear is None:
        return None, None
    if last_bull is None:
        return "bearish", last_bear
    if last_bear is None:
        return "bullish", last_bull

    if last_bull["confirming_time"] > last_bear["confirming_time"]:
        return "bullish", last_bull
    return "bearish", last_bear