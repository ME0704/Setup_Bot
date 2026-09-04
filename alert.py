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

    arrow = "🟢▲" if is_bullish else "🔴▼"
    side = "BUY" if is_bullish else "SELL"

    if result["rule_name"] == "Key level in range":
        lo, hi = result["bos_range"]
        formed_date = timeutil.format_eat_date_only(result["rejection_time"])
        detail_line = (
            f"{side} rejection at {result['shape']}-shape @ {_fmt(result['rejection_price'], digits)} "
            f"(formed {formed_date}), inside the BOS range [{_fmt(lo, digits)}, {_fmt(hi, digits)}]."
        )
    elif result["rule_name"] == "Previous candle sweep":
        formed_date = timeutil.format_eat_date_only(result["rejection_time"])
        detail_line = (
            f"{side} rejection at {_fmt(result['rejection_price'], digits)} (formed {formed_date}), "
            f"after sweeping {_fmt(result['reference_level'], digits)}."
        )
    else:  # "OC key level"
        formed_date = timeutil.format_eat_date_only(result["rejection_time"])
        level_set_date = timeutil.format_eat_date_only(result["oc_level_formed_time"])
        detail_line = (
            f"{side} rejection at OC-shape @ {_fmt(result['reference_level'], digits)} "
            f"(level set {level_set_date}, rejected {formed_date})."
        )

    now_eat = datetime.now(timezone.utc)

    if result["trend_aligned"] is None:
        alignment_text = "No Daily trend established yet"
    else:
        alignment_text = "Aligned" if result["trend_aligned"] else "Not aligned (counter-trend)"

    lines = [
        f"{arrow} {side} · {result['symbol']} · D1→H4",
        "External breakout confirmed",
        "",
        f"Rule           : {result['rule_name']}",
        f"Trend Alignment: {alignment_text}",
        f"Rejection      : {timeutil.format_eat_compact(result['rejection_time'])}",
        f"External BO    : {timeutil.format_eat_compact(result['bos_time'])}",
        f"Level          : {_fmt(result['bos_broken_level'], digits)}",
        "",
        detail_line,
    ]

    if result["swept"] is not None:
        lines.append("🔥 Liquidity sweep confirmed (A+)")

    lines += [
        "",
        "⚠️ Not an entry signal. Bias only — wait for your entry model.",
        "",
        f"Sent {timeutil.format_eat_sent(now_eat)} EAT",
    ]

    return "\n".join(lines)


def send_telegram_alert(message: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing. Check your .env file."
        )
    chat_ids = [cid.strip() for cid in CHAT_ID.split(",") if cid.strip()]
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    responses = []
    for chat_id in chat_ids:
        resp = requests.post(url, data={"chat_id": chat_id, "text": message})
        resp.raise_for_status()
        responses.append(resp.json())
    return responses


def log_alert(result: dict):
    file_exists = os.path.isfile(LOG_FILE)
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