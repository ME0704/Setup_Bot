"""
OC-shape key level: a candle CLOSES at a price, and the very next candle
OPENS from that same price (no gap) — that price becomes a reference level,
since it went untested right at the open. Later, when price returns to
that level and rejects (wicks into it, closes back away), that's an
OC-shape rejection — a third independent rule alongside A-shape/V-shape
(pattern.py) and Previous candle sweep (sweep_rule.py).
"""

from config import SHAPE_LOOKBACK_CANDLES


def _find_oc_levels(daily_closed_df, tolerance, before_index):
    """Every (formed_index, level_price) where close[i] ~= open[i+1], for i+1 < before_index."""
    levels = []
    for i in range(0, before_index - 1):
        close_i = daily_closed_df.iloc[i]["close"]
        open_next = daily_closed_df.iloc[i + 1]["open"]
        if abs(close_i - open_next) <= tolerance:
            levels.append((i + 1, close_i))
    return levels


def detect_oc_rejection(daily_closed_df, prior_day_index: int, trend_direction: str,
                         tolerance: float, max_lookback: int = SHAPE_LOOKBACK_CANDLES):
    """
    Searches backward (most recent candle first) for a candle that touches
    and rejects a previously-formed OC level, in trend_direction.

    Returns:
    {
        "direction": "bearish"|"bullish",
        "level_price": float,
        "reject_price": float,
        "pivot_time": Timestamp,       # the rejection candle's date
        "pivot_index": int,
        "level_formed_time": Timestamp # when the OC level itself was set
    }
    or None.
    """
    start = max(1, prior_day_index - max_lookback)

    for i in range(prior_day_index, start - 1, -1):
        candle = daily_closed_df.iloc[i]
        levels = _find_oc_levels(daily_closed_df, tolerance, i)

        for formed_idx, level_price in reversed(levels):  # nearest-formed level first
            if trend_direction == "bearish":
                touched = candle["high"] >= level_price - tolerance
                rejected = candle["close"] < level_price
                if touched and rejected:
                    return {
                        "direction": "bearish", "level_price": level_price,
                        "reject_price": candle["close"], "pivot_time": candle["time"],
                        "pivot_index": i,
                        "level_formed_time": daily_closed_df.iloc[formed_idx]["time"],
                    }
            elif trend_direction == "bullish":
                touched = candle["low"] <= level_price + tolerance
                rejected = candle["close"] > level_price
                if touched and rejected:
                    return {
                        "direction": "bullish", "level_price": level_price,
                        "reject_price": candle["close"], "pivot_time": candle["time"],
                        "pivot_index": i,
                        "level_formed_time": daily_closed_df.iloc[formed_idx]["time"],
                    }

    return None