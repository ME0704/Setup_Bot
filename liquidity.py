"""
Detects whether TODAY's (still-forming) daily candle has swept the
previous day's high or low — i.e. taken the liquidity resting there.
"""

import pandas as pd
from config import SWEEP_MIN_PIPS


def _min_sweep_price(symbol: str, point: float) -> float:
    pips = SWEEP_MIN_PIPS.get(symbol, SWEEP_MIN_PIPS["default"])
    return pips * point


def detect_sweep(today: pd.Series, prior_day: pd.Series, symbol: str, point: float):
    """
    Returns "low" if today swept the prior day's low,
            "high" if today swept the prior day's high,
            None if neither has happened (yet).
    """
    min_sweep = _min_sweep_price(symbol, point)

    swept_low = today["low"] <= (prior_day["low"] - min_sweep)
    swept_high = today["high"] >= (prior_day["high"] + min_sweep)

    if swept_low and swept_high:
        # both swept today (rare, choppy day) — go with whichever is more extreme
        low_dist = prior_day["low"] - today["low"]
        high_dist = today["high"] - prior_day["high"]
        return "low" if low_dist >= high_dist else "high"
    if swept_low:
        return "low"
    if swept_high:
        return "high"
    return None
