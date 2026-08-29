"""
Formats and sends the Telegram alert, and logs it to CSV for review.
"""

import os
import csv
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv
from config import TELEGRAM_TOKEN_ENV, TELEGRAM_CHAT_ID_ENV, LOG_FILE
import timeutil

load_dotenv()

TOKEN = os.getenv(TELEGRAM_TOKEN_ENV)
CHAT_ID = os.getenv(TELEGRAM_CHAT_ID_ENV)


def _fmt(value: float, digits: int) -> str:
    return f"{value:.{digits}f}"


def format_message(result: dict) -> str:
    digits = result["digits"]
    is_bullish = result["bias"] == "bullish"

    arrow = "🔺" if is_bullish else "🔻"
    side = "BUY" if is_bullish else "SELL"

    if result["swept"] is not None:
        rule_line = "Daily key-level rejection + liquidity sweep (A+)"
        if is_bullish:
            sweep_line = (
                f"Swept previous day's low {_fmt(result['prior_day_low'], digits)}, "
                f"closed back above"
            )
        else:
            sweep_line = (
                f"Swept previous day's high {_fmt(result['prior_day_high'], digits)}, "
                f"closed back below"
            )
    else:
        rule_line = "Daily key-level rejection only, no liquidity sweep (A)"
        sweep_line = "No liquidity sweep confirmed on this setup."

    now_eat = datetime.now(timezone.utc)  # generated-at time is genuinely UTC "now"

    return (
        f"BIAS CONFIRMED - EXTERNAL BO  {arrow}  {side}  {result['symbol']}\n"
        f"(D1->H4)\n\n"
        f"Rule       : {rule_line}\n"
        f"Rejection  : {timeutil.format_eat_short(result['rejection_time'])} EAT\n"
        f"External BO: {timeutil.format_eat_short(result['bos_time'])} EAT\n"
        f"Level      : {_fmt(result['rejection_price'], digits)} ({result['rejection_level']})\n\n"
        f"{sweep_line}\n\n"
        f"Not an entry signal, look for your entry model.\n"
        f"⏰ Alert generated: {timeutil.format_eat_readable(now_eat)} EAT"
    )


def send_telegram_alert(message: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing. Check your .env file."
        )
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    resp.raise_for_status()
    return resp.json()


def log_alert(result: dict):
    file_exists = os.path.isfile(LOG_FILE)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    digits = result["digits"]
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "logged_at_utc", "symbol", "bias", "grade", "rejection_level",
                "rejection_price", "rejection_time_eat", "swept",
                "prior_day_high", "prior_day_low", "bos_broken_level",
                "bos_confirming_close", "bos_time_eat"
            ])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            result["symbol"], result["bias"], result["grade"],
            result["rejection_level"], _fmt(result["rejection_price"], digits),
            timeutil.format_eat_short(result["rejection_time"]), result["swept"],
            _fmt(result["prior_day_high"], digits), _fmt(result["prior_day_low"], digits),
            _fmt(result["bos_broken_level"], digits), _fmt(result["bos_confirming_close"], digits),
            timeutil.format_eat_short(result["bos_time"]),
        ])
