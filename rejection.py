"""
Detects whether the PRIOR completed daily candle rejected off a key level.

A "rejection" = price wicked into/through a level but the candle closed
back away from it, with a wick that's meaningfully bigger than the body
on that side (i.e. a pin-bar / rejection wick, not just a random candle
that happened to overlap a level).
"""

import pandas as pd
from config import REJECTION_WICK_TO_BODY_RATIO, LEVEL_TOUCH_TOLERANCE_PIPS


def _tolerance_price(symbol: str, point: float) -> float:
    pips = LEVEL_TOUCH_TOLERANCE_PIPS.get(symbol, LEVEL_TOUCH_TOLERANCE_PIPS["default"])
    return pips * point


def detect_rejection(prior_day: pd.Series, key_levels: dict, symbol: str, point: float):
    """
    Returns a dict describing the rejection if one is found, else None:
    {
        "level_label": str,
        "level_price": float,
        "direction": "bullish" | "bearish"   # direction of the rejection
    }

    bullish rejection = wicked BELOW a level (support-type) and closed back up
    bearish rejection = wicked ABOVE a level (resistance-type) and closed back down
    """
    o, h, l, c = prior_day["open"], prior_day["high"], prior_day["low"], prior_day["close"]
    body = abs(c - o)
    if body == 0:
        body = point  # avoid division by zero on doji candles

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    tolerance = _tolerance_price(symbol, point)

    best_match = None

    for label, level_price in key_levels.items():
        # Bullish rejection: candle's low pierced at/near the level, closed back above it
        touched_from_above = (l <= level_price + tolerance) and (c > level_price)
        wick_dominant_lower = lower_wick >= REJECTION_WICK_TO_BODY_RATIO * body

        if touched_from_above and wick_dominant_lower:
            best_match = {
                "level_label": label,
                "level_price": level_price,
                "direction": "bullish",
            }
            break  # first match wins; levels dict order is priority order

        # Bearish rejection: candle's high pierced at/near the level, closed back below it
        touched_from_below = (h >= level_price - tolerance) and (c < level_price)
        wick_dominant_upper = upper_wick >= REJECTION_WICK_TO_BODY_RATIO * body

        if touched_from_below and wick_dominant_upper:
            best_match = {
                "level_label": label,
                "level_price": level_price,
                "direction": "bearish",
            }
            break

    return best_match
