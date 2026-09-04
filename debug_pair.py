"""
Diagnostic tool. Checks BOTH directions independently (no trend gate),
trying SHAPE -> SWEEP -> OC rules for each, then 4H BOS.

Usage:  python debug_pair.py JP225.std
"""

import sys
import data_feed
import pattern
import sweep_rule
import oc_shape_rule
import liquidity
import structure
import timeutil
from config import DAILY_LOOKBACK, H4_LOOKBACK, LEVEL_TOUCH_TOLERANCE_PIPS


def debug_pair(symbol: str):
    data_feed.connect()
    point = data_feed.symbol_point(symbol)
    digits = data_feed.symbol_digits(symbol)
    print(f"\n=== {symbol} ===  point:{point}  digits:{digits}\n")

    daily_df = data_feed.get_candles(symbol, "D1", DAILY_LOOKBACK)
    daily_closed_df = data_feed.get_closed_candles(symbol, "D1", DAILY_LOOKBACK)
    prior_day = daily_df.iloc[-2]
    today = daily_df.iloc[-1]
    prior_day_index = len(daily_closed_df) - 1

    print(f"Prior day: {prior_day['time']}  O:{prior_day['open']:.{digits}f} "
          f"H:{prior_day['high']:.{digits}f} L:{prior_day['low']:.{digits}f} C:{prior_day['close']:.{digits}f}")
    print(f"Today:     {today['time']}  O:{today['open']:.{digits}f} "
          f"H:{today['high']:.{digits}f} L:{today['low']:.{digits}f} C:{today['close']:.{digits}f}\n")

    trend, trend_event = structure.determine_trend(daily_closed_df)
    if trend is None:
        print("Daily trend: none established yet (informational only, doesn't block anything)\n")
    else:
        print(f"Daily trend: {trend}, established {trend_event['confirming_time']} "
              f"(broke {trend_event['broken_level']:.{digits}f}) — informational only, doesn't block anything\n")

    h4_df = data_feed.get_closed_candles(symbol, "H4", H4_LOOKBACK)
    tolerance = LEVEL_TOUCH_TOLERANCE_PIPS.get(symbol, LEVEL_TOUCH_TOLERANCE_PIPS["default"]) * point

    for direction in ("bullish", "bearish"):
        print(f"--- Checking {direction.upper()} ---")

        shape = pattern.detect_shape_rejection(daily_closed_df, prior_day_index, trend_direction=direction)
        if shape is not None:
            lo, hi = shape["bos_range"]
            print(f"  SHAPE match: {shape['shape']}-shape @ {shape['price']:.{digits}f} "
                  f"range=[{lo:.{digits}f},{hi:.{digits}f}] date={shape['pivot_time']}")
        else:
            swept = sweep_rule.detect_sweep_rejection(daily_closed_df, prior_day_index, trend_direction=direction)
            if swept is not None:
                print(f"  SWEEP match: swept {swept['swept_level']:.{digits}f}, "
                      f"rejected @ {swept['reject_price']:.{digits}f} date={swept['pivot_time']}")
            else:
                oc = oc_shape_rule.detect_oc_rejection(daily_closed_df, prior_day_index, direction, tolerance)
                if oc is not None:
                    print(f"  OC match: level {oc['level_price']:.{digits}f} (set {oc['level_formed_time']}), "
                          f"rejected @ {oc['reject_price']:.{digits}f} date={oc['pivot_time']}")
                else:
                    print("  No qualifying rejection (shape/sweep/OC) found for this direction.\n")
                    continue

        bos = structure.detect_bos(h4_df, direction, after_time=today["time"])
        if bos is None:
            print("  No fresh 4H BOS within today's window. No alert for this direction.\n")
            continue

        print(f"  4H BOS: broke {bos['broken_level']:.{digits}f}, closed {bos['confirming_close']:.{digits}f}, "
              f"at {bos['confirming_time']}")
        print(f"  >>> VALID {direction.upper()} SETUP — would alert. <<<\n")

    data_feed.shutdown()


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "JP225.std"
    debug_pair(symbol)