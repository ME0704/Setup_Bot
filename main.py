"""
Entry point. Run this with:  python main.py

Loop logic:
- Every POLL_INTERVAL_SECONDS, re-check every pair in config.PAIRS
- evaluate_pair() now returns a LIST of trade ideas (0, 1, or 2 — one per
  direction), since we no longer gate on the Daily trend.
- Alert de-duplication is PERSISTED TO DISK (logs/alert_state.json), keyed
  per symbol+direction to the exact (rejection_time, bos_time) pair. This
  means restarting the bot can never re-send an alert you already got, and
  a symbol can carry an active buy idea and sell idea at the same time,
  tracked independently.
- Alerts are routed ONLY to chats subscribed to that specific pair (via
  /pairs in listener.py), not blasted to everyone in .env.
"""

import time
import json
import os
from datetime import datetime, timezone

import data_feed
import bias_engine
import alert
import user_settings
import bias_engine_weekly
import supabase_settings
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
    data_feed.connect()
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
                            continue  # already alerted this EXACT setup

                        message = alert.format_message(result)
                        alert.log_alert(result)  # always log, regardless of subscribers

                        subscribers = set(user_settings.get_subscribers_for_pair(symbol))
                        try:
                            subscribers |= set(supabase_settings.get_subscribers_for_pair(symbol))
                        except Exception as sb_error:
                            print(f"[main] Supabase lookup failed (using local subscribers only): {sb_error}")
                        subscribers = list(subscribers)  
                        if subscribers:
                            alert.send_to_chat_ids(message, subscribers)
                        else:
                            print(f"[main] {symbol} setup found but no subscribers — not sent. "
                                  f"(Send /pairs to the bot to subscribe.)")

                        state[key] = sig
                        save_state(state)

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