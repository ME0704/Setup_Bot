"""
Reads user preferences from the Supabase database (set via the web portal)
using the SERVICE ROLE key — this bypasses row-level security so the bot
can see EVERY user's settings, not just one signed-in user's own row.

IMPORTANT: the service role key is SERVER-ONLY. It must never appear in
the website code (that uses the anon key instead) — only here, in .env,
on this machine.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def _fetch_all_preferences():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing from .env")

    url = f"{SUPABASE_URL}/rest/v1/user_preferences?select=*"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_subscribers_for_pair(pair: str):
    """Returns a list of telegram_chat_id strings for every web user subscribed to this pair."""
    rows = _fetch_all_preferences()
    chat_ids = []
    for row in rows:
        pairs = row.get("pairs") or []
        chat_id = row.get("telegram_chat_id")
        if pair in pairs and chat_id:
            chat_ids.append(str(chat_id).strip())
    return chat_ids