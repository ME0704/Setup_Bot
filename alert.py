"""
Formats and sends the Telegram alert, and logs it to CSV for review.
Connects active licenses (users.json) with watchlist pairs (subscriptions.json)
and always delivers to the admin.
"""

import os
import csv
import json
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv
import config
import timeutil

load_dotenv()

# Telegram Credentials
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv(getattr(config, "TELEGRAM_TOKEN_ENV", ""), "")
ADMIN_ID = str(os.getenv("ADMIN_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
LOG_FILE = getattr(config, "LOG_FILE", "alerts.csv")

SUBS_FILE = getattr(config, "SUBSCRIPTIONS_FILE", "subscriptions.json")
USERS_FILE = getattr(config, "USERS_DB", "users.json")


def _fmt(value: float, digits: int) -> str:
    return f"{value:.{digits}f}"


def format_message(result: dict) -> str:
    digits = result["digits"]
    is_bullish = result["bias"] == "bullish"

    header_icon = "🟢" if is_bullish else "🔴"
    side = "BUY" if is_bullish else "SELL"

    # Extract the formed date and shape
    formed_date_str = result["rejection_time"].strftime("%a %d %b")  # e.g., Fri 18 Sep
    shape = result.get("shape", "V") 

    if result["rule_name"] == "Previous candle sweep":
        rej_type = f"{shape}-shape KL (Liquidity Sweep) · Formed {formed_date_str}"
    elif result["rule_name"] == "OC key level":
        rej_type = f"OC Level · Formed {formed_date_str}"
    else:
        rej_type = f"{shape}-shape KL · Formed {formed_date_str}"

    alignment = "Aligned ✅" if result["trend_aligned"] else "Counter-Trend ⚠️"
    if result["trend_aligned"] is None:
        alignment = "None established"

    bos_time = timeutil.format_eat_compact(result['bos_time'])

    lines = [
        f"{header_icon} {side} BIAS · {result['symbol']} [D1 ➔ H4]",
        "",
        f"🎯 D1 Rejection: {_fmt(result['rejection_price'], digits)} ({rej_type})",
        f"⚡ 4H External BOS: {_fmt(result['bos_broken_level'], digits)} at {bos_time}",
        f"📊 Daily Trend: {alignment}",
    ]

    if result["swept"] is not None:
        lines.append("\n🔥 Grade A+ (Liquidity sweep confirmed)")

    if result.get("adverse_sweep"):
        level_name = "High" if is_bullish else "Low"
        lines.append(f"\n⚠️ Warning: Previous Daily {level_name} has been taken. Use confirmation entry.")

    lines += [
        "",
        "⏳ Bias only. Execute via your own model."
    ]

    return "\n".join(lines)


def _extract_symbol_from_message(message: str) -> str:
    """Extracts 'EURUSD' from '▲ BUY · EURUSD · D1→H4'."""
    try:
        header = message.strip().split("\n")[0]
        parts = header.split("·")
        if len(parts) >= 2:
            return parts[1].strip()
    except Exception:
        pass
    return ""


def _normalize_symbol(sym: str) -> str:
    """Strips broker suffixes like .r, .pro, m to guarantee clean matches."""
    s = sym.upper().replace("/", "").strip()
    for ext in [".R", ".RAW", ".PRO", ".M", "_I", "M"]:
        if s.endswith(ext):
            return s[:-len(ext)]
    return s


def _get_active_subscribers_for_symbol(symbol: str) -> list:
    """Returns active users from users.json subscribed to this pair in subscriptions.json."""
    recipients = set()
    clean_target = _normalize_symbol(symbol)

    # 1. Check users.json for active unexpired accounts
    valid_users = set()
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                users_db = json.load(f)
            now = datetime.now()
            for uid, udata in users_db.items():
                exp_str = udata.get("expiry")
                if exp_str:
                    try:
                        if now < datetime.fromisoformat(exp_str):
                            valid_users.add(str(uid))
                    except Exception:
                        pass
        except Exception as e:
            print(f"[ALERT WARNING] Error reading users.json: {e}")

    # 2. Check subscriptions.json for chosen pairs
    if os.path.exists(SUBS_FILE):
        try:
            with open(SUBS_FILE, "r") as f:
                subs_db = json.load(f)
            for uid, pairs in subs_db.items():
                clean_pairs = [_normalize_symbol(p) for p in pairs]
                if str(uid) in valid_users and clean_target in clean_pairs:
                    recipients.add(str(uid))
        except Exception as e:
            print(f"[ALERT WARNING] Error reading subscriptions.json: {e}")

    # 3. Always include Admin
    if ADMIN_ID:
        recipients.add(ADMIN_ID)

    print(f"[DISPATCH CHECK] Asset: {clean_target} | Delivering to {len(recipients)} recipients: {list(recipients)}")
    return list(recipients)


def send_telegram_alert(message: str, symbol: str = None):
    """Broadcasts setup alerts to all valid subscribers."""
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing in .env file.")

    if not symbol:
        symbol = _extract_symbol_from_message(message)

    recipients = _get_active_subscribers_for_symbol(symbol)
    if not recipients:
        print(f"[ALERT SKIP] No active subscribers found for {symbol}")
        return []

    return send_to_chat_ids(message, recipients)


def send_to_chat_ids(message: str, chat_ids):
    """Sends individually to each chat ID."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    responses = []

    for chat_id in chat_ids:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "protect_content": False  
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                responses.append(resp.json())
            else:
                print(f"[ALERT ERROR] Delivery failed to {chat_id}: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"[ALERT EXCEPTION] Could not reach {chat_id}: {e}")

    return responses


def log_alert(result: dict):
    file_exists = os.path.isfile(LOG_FILE)
    if os.path.dirname(LOG_FILE):
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    digits = result["digits"]
    lo, hi = result["bos_range"] if result["bos_range"] else (None, None)

    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "logged_at_utc", "symbol", "bias", "grade", "rule_name", "shape",
                "trend_established_eat", "trend_aligned", "rejection_price", "rejection_time_eat",
                "bos_range_low", "bos_range_high", "reference_level", "oc_level_formed_eat",
                "next_day_rule_ok", "swept",
                "prior_day_high", "prior_day_low", "bos_broken_level",
                "bos_confirming_close", "bos_time_eat"
            ])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            result["symbol"], result["bias"], result["grade"], result["rule_name"],
            result["shape"],
            timeutil.format_eat_short(result["trend_established_time"]) if result["trend_established_time"] else "",
            result["trend_aligned"],
            _fmt(result["rejection_price"], digits),
            timeutil.format_eat_short(result["rejection_time"]),
            _fmt(lo, digits) if lo is not None else "",
            _fmt(hi, digits) if hi is not None else "",
            _fmt(result["reference_level"], digits) if result["reference_level"] is not None else "",
            timeutil.format_eat_short(result["oc_level_formed_time"]) if result["oc_level_formed_time"] else "",
            result["next_day_rule_ok"], result["swept"],
            _fmt(result["prior_day_high"], digits), _fmt(result["prior_day_low"], digits),
            _fmt(result["bos_broken_level"], digits), _fmt(result["bos_confirming_close"], digits),
            timeutil.format_eat_short(result["bos_time"]),
        ])