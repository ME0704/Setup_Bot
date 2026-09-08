"""
Low-level Telegram Bot API helpers for the interactive /pairs listener:
long-polling for updates, sending/editing messages with inline keyboards,
and answering callback queries (button taps).
"""

import os
import json
import requests
from dotenv import load_dotenv
from config import TELEGRAM_TOKEN_ENV

load_dotenv()
TOKEN = os.getenv(TELEGRAM_TOKEN_ENV)
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"


def get_updates(offset=None, timeout=30):
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=timeout + 10)
    resp.raise_for_status()
    return resp.json().get("result", [])


def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    resp = requests.post(f"{BASE_URL}/sendMessage", data=data)
    resp.raise_for_status()
    return resp.json()


def edit_message_reply_markup(chat_id, message_id, reply_markup):
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": json.dumps(reply_markup),
    }
    # not raising here - Telegram returns a harmless "message not modified"
    # error if the keyboard content didn't actually change between taps
    return requests.post(f"{BASE_URL}/editMessageReplyMarkup", data=data).json()


def answer_callback_query(callback_query_id, text=None):
    data = {"callback_query_id": callback_query_id}
    if text:
        data["text"] = text
    requests.post(f"{BASE_URL}/answerCallbackQuery", data=data)