"""
The model — no longer gated on the Daily trend:

For EACH direction (bullish AND bearish), independently:
1. REJECTION: try the SHAPE rule, then SWEEP rule, then OC rule, in that
   priority order, searching back SHAPE_LOOKBACK_CANDLES for the most
   recent qualifying one.
2. EXTERNAL BO: 4H break of structure in that SAME direction, on/after today.

If both checks pass, it's a valid trade idea for that direction. The Daily
trend (from the last Daily BOS) is reported for context — "Trend Alignment:
Aligned" or "Not aligned" — but it does NOT gate whether an idea fires.
Waiting for the trend itself to flip can mean missing the actual reversal
move, which is exactly what this change fixes.

evaluate_pair() returns a LIST (0, 1, or 2 items — one per direction that
qualifies), not a single result.
"""

import data_feed
import pattern
import sweep_rule
import oc_shape_rule
import liquidity
import structure
from config import DAILY_LOOKBACK, H4_LOOKBACK, LEVEL_TOUCH_TOLERANCE_PIPS


def _oc_tolerance(symbol, point):
    pips = LEVEL_TOUCH_TOLERANCE_PIPS.get(symbol, LEVEL_TOUCH_TOLERANCE_PIPS["default"])
    return pips * point


def _find_rejection(daily_closed_df, prior_day_index, direction, symbol, point):
    """
    Tries SHAPE rule, then SWEEP rule, then OC rule, for a given direction.
    Returns (rule_name, rejection_price, rejection_time, bos_range,
             shape_letter, reference_level, oc_level_formed_time) or None.
    """
    shape = pattern.detect_shape_rejection(daily_closed_df, prior_day_index, trend_direction=direction)
    if shape is not None:
        return ("Key level in range", shape["price"], shape["pivot_time"],
                shape["bos_range"], shape["shape"], None, None)

    swept = sweep_rule.detect_sweep_rejection(daily_closed_df, prior_day_index, trend_direction=direction)
    if swept is not None:
        return ("Previous candle sweep", swept["reject_price"], swept["pivot_time"],
                None, None, swept["swept_level"], None)

    tolerance = _oc_tolerance(symbol, point)
    oc = oc_shape_rule.detect_oc_rejection(daily_closed_df, prior_day_index, direction, tolerance)
    if oc is not None:
        return ("OC key level", oc["reject_price"], oc["pivot_time"],
                None, "OC", oc["level_price"], oc["level_formed_time"])

    return None


def evaluate_pair(symbol: str):
    point = data_feed.symbol_point(symbol)
    digits = data_feed.symbol_digits(symbol)

    daily_df = data_feed.get_candles(symbol, "D1", DAILY_LOOKBACK)
    daily_closed_df = data_feed.get_closed_candles(symbol, "D1", DAILY_LOOKBACK)

    prior_day = daily_df.iloc[-2]
    today = daily_df.iloc[-1]

    trend, trend_event = structure.determine_trend(daily_closed_df)  # informational only now
    prior_day_index = len(daily_closed_df) - 1

    h4_df = data_feed.get_closed_candles(symbol, "H4", H4_LOOKBACK)

    results = []

    for direction in ("bullish", "bearish"):
        found = _find_rejection(daily_closed_df, prior_day_index, direction, symbol, point)
        if found is None:
            continue

        (rule_name, rejection_price, rejection_time, bos_range,
         shape_letter, reference_level, oc_level_formed_time) = found

        bos = structure.detect_bos(h4_df, direction, after_time=today["time"])
        if bos is None:
            continue

        next_day_rule_ok = bos["confirming_time"].date() > rejection_time.date()
        trend_aligned = (trend == direction) if trend is not None else None

        today_swept = liquidity.detect_sweep(today, prior_day, symbol, point)
        sweep_agrees = (
            (direction == "bullish" and today_swept == "low") or
            (direction == "bearish" and today_swept == "high")
        )
        adverse_sweep = (
            (direction == "bullish" and today_swept == "high") or
            (direction == "bearish" and today_swept == "low")
        )
        grade = "A+" if sweep_agrees else "A"

        results.append({
            "symbol": symbol,
            "bias": direction,
            "grade": grade,
            "digits": digits,
            "trend_established_time": trend_event["confirming_time"] if trend_event else None,
            "trend_aligned": trend_aligned,
            "rule_name": rule_name,
            "adverse_sweep": adverse_sweep,
            "shape": shape_letter,
            "rejection_price": rejection_price,
            "rejection_time": rejection_time,
            "bos_range": bos_range,
            "reference_level": reference_level,
            "oc_level_formed_time": oc_level_formed_time,
            "next_day_rule_ok": next_day_rule_ok,
            "swept": today_swept if sweep_agrees else None,
            "prior_day_high": prior_day["high"],
            "prior_day_low": prior_day["low"],
            "bos_broken_level": bos["broken_level"],
            "bos_confirming_close": bos["confirming_close"],
            "bos_time": bos["confirming_time"],
        })

    return results