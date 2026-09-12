"""
W1->D1 mode: the exact same model as D1->H4, just one timeframe higher.

1. TREND: last WEEKLY break of structure (informational only).
2. REJECTION: shape/sweep/OC rule on WEEKLY candles, either direction —
   reusing the SAME rule functions from pattern.py/sweep_rule.py/
   oc_shape_rule.py, since they're timeframe-agnostic (just take a
   dataframe of candles, don't care what timeframe it represents).
3. EXTERNAL BO: a DAILY break of structure in that direction, on/after
   this week's open — confirming the weekly reaction on the lower timeframe.

Run this ALONGSIDE the regular D1->H4 engine (main.py calls both).
"""

import data_feed
import pattern
import sweep_rule
import oc_shape_rule
import liquidity
import structure
from config import WEEKLY_LOOKBACK, DAILY_LOOKBACK_FOR_W1, LEVEL_TOUCH_TOLERANCE_PIPS


def _oc_tolerance(symbol, point):
    pips = LEVEL_TOUCH_TOLERANCE_PIPS.get(symbol, LEVEL_TOUCH_TOLERANCE_PIPS["default"])
    return pips * point


def _find_rejection(weekly_closed_df, prior_week_index, direction, symbol, point):
    shape = pattern.detect_shape_rejection(weekly_closed_df, prior_week_index, trend_direction=direction)
    if shape is not None:
        return ("Key level in range", shape["price"], shape["pivot_time"],
                shape["bos_range"], shape["shape"], None, None)

    swept = sweep_rule.detect_sweep_rejection(weekly_closed_df, prior_week_index, trend_direction=direction)
    if swept is not None:
        return ("Previous candle sweep", swept["reject_price"], swept["pivot_time"],
                None, None, swept["swept_level"], None)

    tolerance = _oc_tolerance(symbol, point)
    oc = oc_shape_rule.detect_oc_rejection(weekly_closed_df, prior_week_index, direction, tolerance)
    if oc is not None:
        return ("OC key level", oc["reject_price"], oc["pivot_time"],
                None, "OC", oc["level_price"], oc["level_formed_time"])

    return None


def evaluate_pair(symbol: str):
    point = data_feed.symbol_point(symbol)
    digits = data_feed.symbol_digits(symbol)

    weekly_df = data_feed.get_candles(symbol, "W1", WEEKLY_LOOKBACK)
    weekly_closed_df = data_feed.get_closed_candles(symbol, "W1", WEEKLY_LOOKBACK)

    prior_week = weekly_df.iloc[-2]
    this_week = weekly_df.iloc[-1]

    trend, trend_event = structure.determine_trend(weekly_closed_df)  # informational only
    prior_week_index = len(weekly_closed_df) - 1

    daily_df_for_bos = data_feed.get_closed_candles(symbol, "D1", DAILY_LOOKBACK_FOR_W1)

    results = []

    for direction in ("bullish", "bearish"):
        found = _find_rejection(weekly_closed_df, prior_week_index, direction, symbol, point)
        if found is None:
            continue

        (rule_name, rejection_price, rejection_time, bos_range,
         shape_letter, reference_level, oc_level_formed_time) = found

        bos = structure.detect_bos(daily_df_for_bos, direction, after_time=this_week["time"])
        if bos is None:
            continue

        next_day_rule_ok = bos["confirming_time"].date() > rejection_time.date()
        trend_aligned = (trend == direction) if trend is not None else None

        this_week_swept = liquidity.detect_sweep(this_week, prior_week, symbol, point)
        sweep_agrees = (
            (direction == "bullish" and this_week_swept == "low") or
            (direction == "bearish" and this_week_swept == "high")
        )
        adverse_sweep = (
            (direction == "bullish" and this_week_swept == "high") or
            (direction == "bearish" and this_week_swept == "low")
        )
        grade = "A+" if sweep_agrees else "A"

        results.append({
            "symbol": symbol,
            "bias": direction,
            "grade": grade,
            "digits": digits,
            "timeframe_pair": "D1→H4",
            "timeframe_pair": "W1→D1",
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
            "swept": this_week_swept if sweep_agrees else None,
            "prior_day_high": prior_week["high"],
            "prior_day_low": prior_week["low"],
            "bos_broken_level": bos["broken_level"],
            "bos_confirming_close": bos["confirming_close"],
            "bos_time": bos["confirming_time"],
        })

    return results