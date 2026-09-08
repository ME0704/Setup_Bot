"""
Interactive settings listener. Run this ALONGSIDE main.py (a SEPARATE
terminal window, both running at the same time) — main.py finds and sends
alerts, this one listens for /pairs commands and button taps to manage
each chat's own watchlist.

Usage: python listener.py
"""

import time
import telegram_bot
import user_settings
from config import PAIRS


def build_keyboard(chat_id):
    selected = set(user_settings.get_user_pairs(chat_id))

    rows = []
    row = []
    for pair in PAIRS:
        mark = "✅ " if pair in selected else "▫️ "
        row.append({"text": f"{mark}{pair}", "callback_data": f"toggle:{pair}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([{"text": "🔄 Reset", "callback_data": "reset"}])
    rows.append([{"text": "✅ Done", "callback_data": "done"}])
    return {"inline_keyboard": rows}


def handle_command(chat_id, text):
    if text.strip() in ("/start", "/pairs"):
        keyboard = build_keyboard(chat_id)
        telegram_bot.send_message(
            chat_id,
            "Tap the pairs you want alerts for. Tap again to remove. "
            "Reset clears everything. Tap Done when finished.",
            reply_markup=keyboard,
        )


def handle_callback(callback_query):
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]
    data = callback_query["data"]

    if data.startswith("toggle:"):
        pair = data.split("toggle:", 1)[1]
        user_settings.toggle_pair(chat_id, pair)
        keyboard = build_keyboard(chat_id)
        telegram_bot.edit_message_reply_markup(chat_id, message_id, keyboard)
        telegram_bot.answer_callback_query(callback_query["id"])

    elif data == "reset":
        user_settings.reset_pairs(chat_id)
        keyboard = build_keyboard(chat_id)
        telegram_bot.edit_message_reply_markup(chat_id, message_id, keyboard)
        telegram_bot.answer_callback_query(callback_query["id"], text="Cleared all pairs.")

    elif data == "done":
        pairs = user_settings.get_user_pairs(chat_id)
        telegram_bot.answer_callback_query(callback_query["id"], text="Saved!")
        telegram_bot.send_message(
            chat_id,
            f"Watching {len(pairs)} pairs: {', '.join(pairs) if pairs else '(none selected)'}\n"
            f"Send /pairs anytime to change this.",
        )


def run():
    print("[listener] Listening for /pairs commands and button taps...")
    offset = None
    while True:
        try:
            updates = telegram_bot.get_updates(offset=offset)
            for update in updates:
                offset = update["update_id"] + 1

                if "message" in update and "text" in update["message"]:
                    chat_id = update["message"]["chat"]["id"]
                    handle_command(chat_id, update["message"]["text"])

                elif "callback_query" in update:
                    handle_callback(update["callback_query"])

        except Exception as e:
            print(f"[listener] Error: {e}")
            time.sleep(3)


if __name__ == "__main__":
    run()