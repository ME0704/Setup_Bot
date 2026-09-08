"""
Stores which pairs each Telegram chat wants alerts for — lets each user
(or group) build their own watchlist instead of everyone getting every pair.
"""

import json
import os

SETTINGS_FILE = "logs/user_settings.json"


def _load():
    if not os.path.isfile(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_user_pairs(chat_id):
    data = _load()
    return data.get(str(chat_id), {}).get("pairs", [])


def toggle_pair(chat_id, pair: str):
    data = _load()
    chat_id = str(chat_id)
    if chat_id not in data:
        data[chat_id] = {"pairs": []}
    pairs = data[chat_id]["pairs"]
    if pair in pairs:
        pairs.remove(pair)
    else:
        pairs.append(pair)
    _save(data)
    return pairs


def get_subscribers_for_pair(pair: str):
    data = _load()
    return [chat_id for chat_id, settings in data.items() if pair in settings.get("pairs", [])]


def reset_pairs(chat_id):
    data = _load()
    chat_id = str(chat_id)
    data[chat_id] = {"pairs": []}
    _save(data)
    return []