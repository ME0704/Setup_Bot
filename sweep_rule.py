"""
Next Day Rule / "Previous candle sweep": a Daily candle sweeps the PRIOR
candle's high or low, then closes back on the rejecting side — a stop-hunt
and reversal within a single candle. This is a separate, independent way
to qualify a rejection, alongside the A-shape/V-shape rule in pattern.py.

Searches backward the same way the shape rule does, so it can find this
pattern several candles back, not just yesterday.
"""

from config import SHAPE_LOOKBACK_CANDLES


def detect_sweep_rejection(daily_closed_df, prior_day_index: int, trend_direction: str,
                            max_lookback: int = SHAPE_LOOKBACK_CANDLES):
    """
    Returns:
    {
        "direction": "bearish" | "bullish",
        "swept_level": float,     # the prior candle's high (bearish) or low (bullish)
        "reject_price": float,    # this candle's close
        "pivot_time": Timestamp,  # date of the candle that swept + rejected
        "pivot_index": int,
    }
    or None if no qualifying sweep+reject candle exists within the lookback.
    """
    start = max(1, prior_day_index - max_lookback)

    for i in range(prior_day_index, start - 1, -1):  # most recent first
        candle = daily_closed_df.iloc[i]
        prev = daily_closed_df.iloc[i - 1]

        if trend_direction == "bearish":
            swept = candle["high"] > prev["high"]
            rejected = candle["close"] < prev["high"]
            if swept and rejected:
                return {
                    "direction": "bearish",
                    "swept_level": prev["high"],
                    "reject_price": candle["close"],
                    "pivot_time": candle["time"],
                    "pivot_index": i,
                }

        elif trend_direction == "bullish":
            swept = candle["low"] < prev["low"]
            rejected = candle["close"] > prev["low"]
            if swept and rejected:
                return {
                    "direction": "bullish",
                    "swept_level": prev["low"],
                    "reject_price": candle["close"],
                    "pivot_time": candle["time"],
                    "pivot_index": i,
                }

    return None