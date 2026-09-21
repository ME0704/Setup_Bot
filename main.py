"""
Entry point for MS Radar (Forex).
Run this with:  python main.py

Loop logic:
- Periodically checks every pair in config.PAIRS.
- Deduplicates alerts via logs/alert_state.json.
- Routes alerts dynamically to active subscribers (users.json + subscriptions.json)
  and admin via alert.send_telegram_alert.
"""

import time
import json
import os
from datetime import datetime, timezone

import data_feed
import bias_engine
import bias_engine_weekly
import alert
from config import PAIRS, POLL_INTERVAL_SECONDS

STATE_FILE = "logs/alert_state.json"


def load_state():
    if not os.path.isfile(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def signature_for(result):
    return f"{result['rejection_time'].isoformat()}|{result['bos_time'].isoformat()}"


def run():
    data_feed.connect(terminal_path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
    state = load_state()

    print(f"[main] Watching {len(PAIRS)} pairs. Checking every {POLL_INTERVAL_SECONDS}s.")
    print(f"[main] Pairs: {', '.join(PAIRS)}")
    print(f"[main] Loaded {len(state)} previously-alerted signatures from disk.")

    try:
        while True:
            for symbol in PAIRS:
                try:
                    results = bias_engine.evaluate_pair(symbol) + bias_engine_weekly.evaluate_pair(symbol)

                    for result in results:
                        tf_tag = result.get("timeframe_pair", "D1→H4")
                        key = f"{symbol}_{result['bias']}_{tf_tag}"
                        sig = signature_for(result)

                        if state.get(key) == sig:
                            continue  # Already alerted this exact setup

                        message = alert.format_message(result)
                        alert.log_alert(result)

                        # Dispatch via alert.py (handles .m/.std suffixes, users.json, and subscriptions.json)
                        alert.send_telegram_alert(message, symbol=symbol)

                        state[key] = sig
                        save_state(state)

                        print(f"[{datetime.now(timezone.utc)}] PROCESSED SETUP: {symbol} - {result['bias']}")

                except Exception as pair_error:
                    print(f"[main] Error processing {symbol}: {pair_error}")

            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n[main] Stopped by user.")
    finally:
        data_feed.shutdown()


if __name__ == "__main__":
    run()