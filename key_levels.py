"""
Builds the set of daily key levels to check rejections against:
- Prior day High / Low
- Prior day Close
- Today's Daily Open
- Classic pivot Support/Resistance (S1/R1), derived from prior day's H/L/C

If you mark your own S/R manually on chart, replace `pivot_levels()`
with your own level list — everything downstream just expects a dict
of {label: price}.
"""

import pandas as pd


def pivot_levels(prior_high: float, prior_low: float, prior_close: float) -> dict:
    pivot = (prior_high + prior_low + prior_close) / 3
    r1 = (2 * pivot) - prior_low
    s1 = (2 * pivot) - prior_high
    return {
        "Pivot": pivot,
        "R1": r1,
        "S1": s1,
    }


def get_daily_key_levels(daily_df: pd.DataFrame) -> dict:
    """
    daily_df must have at least 2 completed daily candles (prior day + the
    one before it, so we can compute pivots from the fully closed prior day)
    plus today's forming candle as the last row.

    Returns a dict of {label: price} representing all key levels to check
    the prior day's rejection against.
    """
    if len(daily_df) < 3:
        raise ValueError("Need at least 3 daily candles to compute key levels.")

    prior_day = daily_df.iloc[-2]        # yesterday, fully closed
    day_before_prior = daily_df.iloc[-3]  # used to build pivots FOR prior day
    today = daily_df.iloc[-1]            # today, still forming

    levels = {
        "Prior Day High": prior_day["high"],
        "Prior Day Low": prior_day["low"],
        "Prior Day Close (2 days ago)": day_before_prior["close"],
        "Today's Daily Open": today["open"],
    }

    pivots = pivot_levels(
        day_before_prior["high"], day_before_prior["low"], day_before_prior["close"]
    )
    for label, price in pivots.items():
        levels[label] = price

    return levels
