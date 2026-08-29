"""
Converts MT5 broker-server timestamps to East Africa Time (EAT, UTC+3, no DST).

MT5 candle timestamps are in the BROKER'S SERVER time, not your local time
and not UTC. Every broker sets this differently. To convert correctly, you
need to tell us your broker's server UTC offset once (see config.py:
BROKER_SERVER_UTC_OFFSET_HOURS).

HOW TO FIND YOUR BROKER'S OFFSET:
Look at the clock in the bottom-right corner of your MT5 terminal window —
that's server time. Compare it to the actual current UTC time (search
"UTC time now"). The difference (server_time - utc_time) is your offset.
Example: if MT5 shows 15:00 and UTC is currently 12:00, your offset is +3.
"""

from datetime import timedelta
from config import BROKER_SERVER_UTC_OFFSET_HOURS

EAT_OFFSET_HOURS = 3  # East Africa Time is fixed UTC+3 year-round, no DST


def to_eat(broker_time):
    """Converts a naive MT5 candle/server timestamp into East Africa Time."""
    utc_time = broker_time - timedelta(hours=BROKER_SERVER_UTC_OFFSET_HOURS)
    return utc_time + timedelta(hours=EAT_OFFSET_HOURS)


def format_eat_short(broker_time) -> str:
    """e.g. '2026-08-27 03:00:00'"""
    return to_eat(broker_time).strftime("%Y-%m-%d %H:%M:%S")


def format_eat_readable(broker_time) -> str:
    """e.g. '27 August 2026, 7:00 AM' (no leading zeros on day/hour)"""
    dt = to_eat(broker_time)
    hour_12 = dt.strftime("%I").lstrip("0") or "12"
    return f"{dt.day} {dt.strftime('%B %Y')}, {hour_12}:{dt.strftime('%M %p')}"
