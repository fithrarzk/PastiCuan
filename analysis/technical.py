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

    # ── MACD (12, 26, 9) ─────────────────────────────────────────────────────
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"]        = ema12 - ema26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"]   = df["MACD"] - df["MACD_Signal"]

    macd_val    = df["MACD"].iloc[-1]        if not df["MACD"].isna().all()        else None
    macd_sig_val = df["MACD_Signal"].iloc[-1] if not df["MACD_Signal"].isna().all() else None
    macd_hist_val = df["MACD_Hist"].iloc[-1]  if not df["MACD_Hist"].isna().all()   else None

    if macd_val is not None and macd_sig_val is not None and len(df) >= 2:
        prev_macd = df["MACD"].iloc[-2]
        prev_sig  = df["MACD_Signal"].iloc[-2]
        if prev_macd <= prev_sig and macd_val > macd_sig_val:
            macd_signal = "🟢 Bullish Crossover (MACD crossed above Signal)"
        elif prev_macd >= prev_sig and macd_val < macd_sig_val:
            macd_signal = "🔴 Bearish Crossover (MACD crossed below Signal)"
        elif macd_val > macd_sig_val:
            macd_signal = "🟢 Bullish (MACD above Signal)"
        elif macd_val < macd_sig_val:
            macd_signal = "🔴 Bearish (MACD below Signal)"
        else:
            macd_signal = "🟡 Neutral"
    else:
        macd_signal = "N/A"

    # ── MFI (14) — Money Flow Index ────────────────────────────────────────
    typical_price = (high + low + close) / 3
    raw_money_flow = typical_price * df["Volume"]
    tp_delta = typical_price.diff()
    pos_flow = raw_money_flow.where(tp_delta > 0, 0.0).rolling(14).sum()
    neg_flow = raw_money_flow.where(tp_delta < 0, 0.0).rolling(14).sum()
    money_ratio = pos_flow / neg_flow.replace(0, np.nan)
    df["MFI"] = 100 - (100 / (1 + money_ratio))

    mfi_val = df["MFI"].iloc[-1] if not df["MFI"].isna().all() else None
    if mfi_val is None:
        mfi_signal = "N/A"
    elif mfi_val >= 80:
        mfi_signal = "🔴 Overbought (MFI ≥ 80) — potential distribution"
    elif mfi_val <= 20:
        mfi_signal = "🟢 Oversold (MFI ≤ 20) — potential accumulation"
    elif mfi_val >= 60:
        mfi_signal = "🟢 Strong Inflow — accumulation likely"
    elif mfi_val <= 40:
        mfi_signal = "🔴 Weak Flow — distribution likely"
    else:
        mfi_signal = "🟡 Neutral money flow"

    # ── OBV (On-Balance Volume) ───────────────────────────────────────────
    obv_sign = np.sign(close.diff()).fillna(0)
    df["OBV"] = (obv_sign * df["Volume"]).cumsum()

    obv_val = df["OBV"].iloc[-1] if not df["OBV"].isna().all() else None
    # OBV trend: compare OBV SMA-20 slope over last 5 bars
    obv_sma = df["OBV"].rolling(20).mean()
    if len(obv_sma.dropna()) >= 5:
        obv_slope = obv_sma.iloc[-1] - obv_sma.iloc[-5]
    else:
        obv_slope = None

    if obv_slope is not None:
        if obv_slope > 0:
            obv_signal = "🟢 Rising OBV — volume supports price trend"
        elif obv_slope < 0:
            obv_signal = "🔴 Falling OBV — volume diverging from price"
        else:
            obv_signal = "🟡 Flat OBV"
    else:
        obv_signal = "N/A"

    # ── Smart Money Flow verdict ───────────────────────────────────────────
    price_bullish = (rsi_val is not None and rsi_val > 50) if rsi_val else False
    vol_bullish   = (mfi_val is not None and mfi_val > 50) and (obv_slope is not None and obv_slope > 0)
    vol_bearish   = (mfi_val is not None and mfi_val < 50) and (obv_slope is not None and obv_slope < 0)

    if price_bullish and vol_bullish:
        smart_money = "🟢 Accumulation — price rise supported by strong volume inflow (Smart Money buying)"
    elif price_bullish and vol_bearish:
        smart_money = "🟠 Distribution Warning — price rising but volume weakening (potential Smart Money exit)"
    elif not price_bullish and vol_bullish:
        smart_money = "🟢 Stealth Accumulation — price weak but volume quietly building (Smart Money loading)"
    elif not price_bullish and vol_bearish:
        smart_money = "🔴 Distribution — price falling with volume outflow (Smart Money exiting)"
    else:
        smart_money = "🟡 Inconclusive — mixed volume signals"

    return {
        "rsi":        rsi_val,        "rsi_signal":  rsi_signal,
        "sma50":      sma50_val,      "sma200":      sma200_val,        "sma_signal":  sma_signal,
        "support":    support_val,    "resistance":  resistance_val,    "sr_signal":   sr_signal,
        "atr":        atr_val,        "atr_pct":     atr_pct_val,       "atr_signal":  atr_signal,
        "macd":       macd_val,       "macd_signal_val": macd_sig_val,
        "macd_hist":  macd_hist_val,  "macd_signal": macd_signal,
        "mfi":        mfi_val,        "mfi_signal":  mfi_signal,
        "obv":        obv_val,        "obv_signal":  obv_signal,
        "smart_money": smart_money,
        "df":         df,
    }
