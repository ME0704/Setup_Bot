"""
A-shape / V-shape rejection detection.

A-shape = a Daily swing HIGH (price rises into it, then falls away) — the
classic peak pivot. Feeds SELL setups: expects a support break (bearish
BOS) on the lower timeframe afterward.

V-shape = a Daily swing LOW (price falls into it, then rises away) — the
classic trough pivot. Feeds BUY setups: expects a resistance break
(bullish BOS) on the lower timeframe afterward.

"Inside the BOS range" = the pivot's price must sit within
[nearest opposite swing low, nearest opposite swing high] around it — i.e.
it's a genuine reaction INSIDE the current established range, not a break
to a fresh extreme.
"""

import structure
from config import FRACTAL_WIDTH, SHAPE_LOOKBACK_CANDLES


def detect_shape_rejection(daily_closed_df, prior_day_index: int, trend_direction: str,
                            width: int = FRACTAL_WIDTH, max_lookback: int = SHAPE_LOOKBACK_CANDLES):
    """
    Searches BACKWARD through confirmed swing pivots (most recent first, up
    to max_lookback candles behind prior_day_index) for the first one that:
      - matches trend_direction (A-shape/bearish or V-shape/bullish)
      - sits INSIDE its bounding BOS range

    This does not stop at just the single most recent pivot — if that one
    doesn't qualify, it keeps checking earlier ones until it finds a valid
    rejection or runs out of lookback. This is what lets the bot find a
    rejection that happened many candles back, not just yesterday.

    Returns:
    {
        "shape": "A" | "V",
        "direction": "bearish" | "bullish",
        "price": float,
        "bos_range": (low, high),
        "inside_range": True,
        "pivot_index": int,
        "pivot_time": Timestamp,
    }
    or None if no qualifying pivot exists within the lookback window.
    """
    swing_highs, swing_lows = structure.find_swing_points(daily_closed_df, width)

    candidates = []
    for idx, price in swing_highs:
        if idx <= prior_day_index:
            candidates.append((idx, price, "A", "bearish"))
    for idx, price in swing_lows:
        if idx <= prior_day_index:
            candidates.append((idx, price, "V", "bullish"))

    candidates.sort(key=lambda c: c[0], reverse=True)  # most recent first
    candidates = [c for c in candidates if prior_day_index - c[0] <= max_lookback]

    for idx, price, shape, direction in candidates:
        if direction != trend_direction:
            continue

        prior_lows = [sl for sl in swing_lows if sl[0] < idx]
        prior_highs = [sh for sh in swing_highs if sh[0] < idx]
        range_low = prior_lows[-1][1] if prior_lows else None
        range_high = prior_highs[-1][1] if prior_highs else None
        if range_low is None or range_high is None:
            continue

        lo, hi = min(range_low, range_high), max(range_low, range_high)
        if lo <= price <= hi:
            return {
                "shape": shape,
                "direction": direction,
                "price": price,
                "bos_range": (lo, hi),
                "inside_range": True,
                "pivot_index": idx,
                "pivot_time": daily_closed_df.iloc[idx]["time"],
            }

    return None  # no qualifying pivot found within the lookback