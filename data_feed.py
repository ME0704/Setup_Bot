"""
Pulls candles straight from your running MT5 terminal (forex.com feed).
This is the SAME data your charts show — no separate data source.
"""

import MetaTrader5 as mt5
import pandas as pd


def connect():
    """Call once at startup. Must have MT5 terminal open and logged in."""
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")
    print("[data_feed] Connected to MT5 terminal.")


def shutdown():
    mt5.shutdown()


def get_candles(symbol: str, timeframe: str, count: int) -> pd.DataFrame:
    """
    timeframe: 'D1' or 'H4'
    Returns a DataFrame indexed oldest -> newest with columns:
    time, open, high, low, close, tick_volume
    """
    tf_map = {
        "D1": mt5.TIMEFRAME_D1,
        "H4": mt5.TIMEFRAME_H4,
    }
    if timeframe not in tf_map:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(
            f"No candles returned for {symbol} {timeframe}. "
            f"Check symbol name matches Market Watch exactly. MT5 error: {mt5.last_error()}"
        )

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df[["time", "open", "high", "low", "close", "tick_volume"]]
    df.reset_index(drop=True, inplace=True)
    return df


def symbol_point(symbol: str) -> float:
    """Returns the pip/point size for a symbol, used to convert pip thresholds to price."""
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info() returned None for {symbol}")
    return info.point


def symbol_digits(symbol: str) -> int:
    """Returns the number of decimal digits this symbol is quoted with (from MT5)."""
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info() returned None for {symbol}")
    return info.digits


def get_closed_candles(symbol: str, timeframe: str, count: int) -> pd.DataFrame:
    """
    Same as get_candles(), but GUARANTEES every returned candle is fully closed.

    MT5's copy_rates_from_pos always includes the currently-forming candle
    at the most recent position — it is live and still changing. For
    anything that must only react to a confirmed close (like 4H break of
    structure), that forming candle must never be evaluated, or you'll get
    alerts firing mid-candle instead of on the actual close.

    This fetches one extra candle and drops the last (forming) one.
    """
    df = get_candles(symbol, timeframe, count + 1)
    return df.iloc[:-1].reset_index(drop=True)
