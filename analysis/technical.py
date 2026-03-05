import pandas as pd
import numpy as np


def analyze_technical(df: pd.DataFrame) -> dict:
    """
    Calculates technical indicators from OHLCV price history.

    Indicators
    ----------
    - RSI (14-day Wilder's smoothing)
    - SMA 50 and SMA 200
    - Support & Resistance from last 3 months' highs/lows
    - ATR (14-day Average True Range)

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV DataFrame from yfinance.

    Returns
    -------
    dict of computed values, signal labels, and a 'df' key containing
    the original DataFrame with indicator columns appended.
    """
    df = df.copy()
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    # ── RSI (14) ─────────────────────────────────────────────────────────────
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    rsi_val = df["RSI"].iloc[-1] if not df["RSI"].isna().all() else None
    if rsi_val is None:
        rsi_signal = "N/A"
    elif rsi_val >= 70:
        rsi_signal = "🔴 Overbought (RSI ≥ 70)"
    elif rsi_val <= 30:
        rsi_signal = "🟢 Oversold (RSI ≤ 30)"
    else:
        rsi_signal = "🟡 Neutral (30 – 70)"

    # ── SMA 50 & 200 ─────────────────────────────────────────────────────────
    df["SMA50"]  = close.rolling(50).mean()
    df["SMA200"] = close.rolling(200).mean()

    sma50_val  = df["SMA50"].iloc[-1]  if not df["SMA50"].isna().all()  else None
    sma200_val = df["SMA200"].iloc[-1] if not df["SMA200"].isna().all() else None

    if sma50_val is not None and sma200_val is not None:
        if sma50_val > sma200_val:
            sma_signal = "🟢 Golden Cross — SMA50 above SMA200 (Bullish)"
        else:
            sma_signal = "🔴 Death Cross — SMA50 below SMA200 (Bearish)"
    else:
        sma_signal = "⚪ Insufficient data for SMA200 signal"

    # ── Support & Resistance (last 3 months) ─────────────────────────────────
    cutoff = df.index[-1] - pd.DateOffset(months=3)
    df_3m  = df.loc[df.index >= cutoff]

    support_val    = float(df_3m["Low"].min())  if not df_3m.empty else None
    resistance_val = float(df_3m["High"].max()) if not df_3m.empty else None

    current_price = float(close.iloc[-1])
    if support_val and resistance_val:
        rng = resistance_val - support_val
        pos = (current_price - support_val) / rng * 100 if rng > 0 else 50
        if pos <= 25:
            sr_signal = "🟢 Near Support — potential bounce zone"
        elif pos >= 75:
            sr_signal = "🔴 Near Resistance — potential reversal zone"
        else:
            sr_signal = "🟡 Mid-range between Support and Resistance"
    else:
        sr_signal = "N/A"

    # ── ATR (14) ─────────────────────────────────────────────────────────────
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low,
         (high - prev_close).abs(),
         (low  - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()

    atr_val     = df["ATR"].iloc[-1] if not df["ATR"].isna().all() else None
    atr_pct_val = (atr_val / current_price * 100) if atr_val else None

    if atr_pct_val is None:
        atr_signal = "N/A"
    elif atr_pct_val >= 3.0:
        atr_signal = "🔴 High Volatility"
    elif atr_pct_val >= 1.5:
        atr_signal = "🟡 Moderate Volatility"
    else:
        atr_signal = "🟢 Low Volatility"

    return {
        "rsi":        rsi_val,        "rsi_signal":  rsi_signal,
        "sma50":      sma50_val,      "sma200":      sma200_val,        "sma_signal":  sma_signal,
        "support":    support_val,    "resistance":  resistance_val,    "sr_signal":   sr_signal,
        "atr":        atr_val,        "atr_pct":     atr_pct_val,       "atr_signal":  atr_signal,
        "df":         df,
    }
