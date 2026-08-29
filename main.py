"""
Entry point. Run this with:  python main.py

Loop logic:
- Every POLL_INTERVAL_SECONDS, re-check every pair in config.PAIRS
- Only alert ONCE per pair per daily bias setup (tracked in `already_alerted`)
- Resets the "already alerted" flag when the daily candle rolls over
  (i.e. when today's daily open time changes)
"""

import time
from datetime import datetime, timezone

import data_feed
import bias_engine
import alert
from config import PAIRS, POLL_INTERVAL_SECONDS


def run():
    data_feed.connect()

    # Tracks which pairs have already fired an alert for the CURRENT daily candle
    already_alerted = {symbol: False for symbol in PAIRS}
    last_daily_open_time = {symbol: None for symbol in PAIRS}

    print(f"[main] Watching {len(PAIRS)} pairs. Checking every {POLL_INTERVAL_SECONDS}s.")
    print(f"[main] Pairs: {', '.join(PAIRS)}")

    try:
        while True:
            for symbol in PAIRS:
                try:
                    # Detect new daily candle -> reset alert flag for this pair
                    daily_df = data_feed.get_candles(symbol, "D1", 3)
                    today_open_time = daily_df.iloc[-1]["time"]

                    if last_daily_open_time[symbol] != today_open_time:
                        last_daily_open_time[symbol] = today_open_time
                        already_alerted[symbol] = False

                    if already_alerted[symbol]:
                        continue  # already sent today's alert for this pair

                    result = bias_engine.evaluate_pair(symbol)
                    if result is not None:
                        message = alert.format_message(result)
                        alert.send_telegram_alert(message)
                        alert.log_alert(result)
                        already_alerted[symbol] = True
                        print(f"[{datetime.now(timezone.utc)}] ALERT SENT: {symbol} - {result['bias']}")

                except Exception as pair_error:
                    print(f"[main] Error processing {symbol}: {pair_error}")

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n[main] Stopped by user.")
    finally:
        data_feed.shutdown()


if __name__ == "__main__":
    run()
