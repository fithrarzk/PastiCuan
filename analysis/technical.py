import pandas as pd
import numpy as np


SECTOR_PROFILES = {
    "financial services": "stable_compounder",
    "bank": "stable_compounder",
    "energy": "cyclical_high_volatility",
    "basic materials": "cyclical_high_volatility",
    "materials": "cyclical_high_volatility",
    "mining": "cyclical_high_volatility",
    "coal": "cyclical_high_volatility",
    "oil": "cyclical_high_volatility",
    "technology": "growth_high_beta",
    "consumer defensive": "defensive",
    "consumer staples": "defensive",
    "utilities": "defensive",
    "healthcare": "defensive",
}

PROFILE_CONFIG = {
    "cyclical_high_volatility": {
        "label": "Cyclical / High Volatility",
        "horizon": "Short-term tactical (1-8 weeks)",
        "rsi": 10,
        "fast_ma": 20,
        "slow_ma": 60,
        "long_ma": 120,
        "macd": (8, 21, 5),
        "sr_days": 65,
        "risk_multiple": 1.35,
        "target_multiple": 2.0,
        "weights": {
            "trend": 0.20,
            "momentum": 0.28,
            "volume": 0.22,
            "range": 0.15,
            "risk": 0.15,
        },
    },
    "growth_high_beta": {
        "label": "Growth / High Beta",
        "horizon": "Short-to-medium term (2-12 weeks)",
        "rsi": 14,
        "fast_ma": 21,
        "slow_ma": 89,
        "long_ma": 200,
        "macd": (10, 24, 7),
        "sr_days": 90,
        "risk_multiple": 1.55,
        "target_multiple": 2.2,
        "weights": {
            "trend": 0.24,
            "momentum": 0.26,
            "volume": 0.20,
            "range": 0.12,
            "risk": 0.18,
        },
    },
    "stable_compounder": {
        "label": "Stable Compounder / Bank-like",
        "horizon": "Medium-to-long term (3-12 months)",
        "rsi": 14,
        "fast_ma": 50,
        "slow_ma": 200,
        "long_ma": 200,
        "macd": (12, 26, 9),
        "sr_days": 126,
        "risk_multiple": 1.15,
        "target_multiple": 1.8,
        "weights": {
            "trend": 0.35,
            "momentum": 0.20,
            "volume": 0.15,
            "range": 0.15,
            "risk": 0.15,
        },
    },
    "defensive": {
        "label": "Defensive / Low Volatility",
        "horizon": "Medium term (2-9 months)",
        "rsi": 14,
        "fast_ma": 40,
        "slow_ma": 150,
        "long_ma": 200,
        "macd": (12, 26, 9),
        "sr_days": 126,
        "risk_multiple": 1.10,
        "target_multiple": 1.7,
        "weights": {
            "trend": 0.32,
            "momentum": 0.18,
            "volume": 0.15,
            "range": 0.17,
            "risk": 0.18,
        },
    },
    "balanced": {
        "label": "Balanced / General IDX",
        "horizon": "Intermediate term (1-6 months)",
        "rsi": 14,
        "fast_ma": 30,
        "slow_ma": 100,
        "long_ma": 200,
        "macd": (12, 26, 9),
        "sr_days": 90,
        "risk_multiple": 1.25,
        "target_multiple": 1.9,
        "weights": {
            "trend": 0.30,
            "momentum": 0.22,
            "volume": 0.16,
            "range": 0.16,
            "risk": 0.16,
        },
    },
}


def _last_valid(series: pd.Series):
    valid = series.dropna()
    return None if valid.empty else valid.iloc[-1]


def _fmt_price(value) -> str:
    return "N/A" if value is None or pd.isna(value) else f"Rp {value:,.0f}"


def _score_to_signal(score: float) -> str:
    if score >= 70:
        return "🟢 Strong Buy / Accumulation"
    if score >= 58:
        return "🟢 Buy on Weakness"
    if score >= 45:
        return "🟡 Hold / Wait for Confirmation"
    if score >= 35:
        return "🟠 Weak / Reduce Risk"
    return "🔴 Avoid / Downtrend Risk"


def _sector_profile(sector: str | None) -> str:
    sector_lower = (sector or "").lower()
    for keyword, profile in SECTOR_PROFILES.items():
        if keyword in sector_lower:
            return profile
    return "balanced"


def _realized_volatility(close: pd.Series) -> float | None:
    returns = close.pct_change().dropna()
    if len(returns) < 20:
        return None
    return float(returns.tail(min(len(returns), 252)).std() * np.sqrt(252) * 100)


def _pick_profile(sector: str | None, atr_pct: float | None, realized_vol: float | None, beta) -> str:
    base_profile = _sector_profile(sector)
    beta_val = beta if isinstance(beta, (int, float)) and not pd.isna(beta) else None

    high_vol = (
        (atr_pct is not None and atr_pct >= 3.0)
        or (realized_vol is not None and realized_vol >= 45)
        or (beta_val is not None and beta_val >= 1.35)
    )
    low_vol = (
        (atr_pct is not None and atr_pct <= 1.4)
        and (realized_vol is not None and realized_vol <= 25)
    )

    if high_vol and base_profile not in {"stable_compounder", "defensive"}:
        return "cyclical_high_volatility"
    if low_vol and base_profile == "balanced":
        return "defensive"
    return base_profile


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def _support_resistance(df: pd.DataFrame, lookback_days: int) -> tuple[float | None, float | None]:
    window = df.tail(min(len(df), lookback_days))
    if window.empty:
        return None, None
    support = window["Low"].rolling(3, min_periods=1).min().quantile(0.10)
    resistance = window["High"].rolling(3, min_periods=1).max().quantile(0.90)
    return float(support), float(resistance)


def _distance_pct(price: float, level: float | None) -> float | None:
    if level is None or level == 0:
        return None
    return (price - level) / level * 100


def analyze_technical(df: pd.DataFrame, sector: str | None = None, info: dict | None = None) -> dict:
    """
    Calculates adaptive technical indicators from OHLCV history.

    The analysis selects a trading horizon and indicator parameters from sector,
    realized volatility, ATR%, and beta. This keeps volatile cyclical stocks from
    being judged with the same slow lens as stable bank-like compounders.
    """
    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    if df is None or df.empty or not set(required_cols).issubset(df.columns):
        return {
            "error": "Insufficient OHLCV data for technical analysis.",
            "df": pd.DataFrame(),
        }

    df = df.copy().sort_index()
    df = df.dropna(subset=["High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0)

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    current_price = float(close.iloc[-1])

    df["ATR"] = _atr(high, low, close)
    atr_val = _last_valid(df["ATR"])
    atr_pct_val = float(atr_val / current_price * 100) if atr_val and current_price else None
    realized_vol = _realized_volatility(close)

    info = info or {}
    profile_key = _pick_profile(sector, atr_pct_val, realized_vol, info.get("beta"))
    config = PROFILE_CONFIG[profile_key]
    weights = config["weights"]

    rsi_period = config["rsi"]
    fast_ma = config["fast_ma"]
    slow_ma = config["slow_ma"]
    long_ma = config["long_ma"]
    macd_fast, macd_slow, macd_signal_period = config["macd"]

    df["RSI"] = _rsi(close, rsi_period)
    df["MA_Fast"] = close.rolling(fast_ma).mean()
    df["MA_Slow"] = close.rolling(slow_ma).mean()
    df["MA_Long"] = close.rolling(long_ma).mean()
    df["SMA50"] = close.rolling(50).mean()
    df["SMA200"] = close.rolling(200).mean()

    rsi_val = _last_valid(df["RSI"])
    fast_ma_val = _last_valid(df["MA_Fast"])
    slow_ma_val = _last_valid(df["MA_Slow"])
    long_ma_val = _last_valid(df["MA_Long"])
    sma50_val = _last_valid(df["SMA50"])
    sma200_val = _last_valid(df["SMA200"])

    rsi_low = 25 if profile_key == "cyclical_high_volatility" else 30
    rsi_high = 75 if profile_key == "cyclical_high_volatility" else 70
    if rsi_val is None:
        rsi_signal = "N/A"
    elif rsi_val >= rsi_high:
        rsi_signal = f"🔴 Overbought (RSI ≥ {rsi_high})"
    elif rsi_val <= rsi_low:
        rsi_signal = f"🟢 Oversold (RSI ≤ {rsi_low})"
    elif rsi_val >= 55:
        rsi_signal = "🟢 Positive momentum"
    elif rsi_val <= 45:
        rsi_signal = "🔴 Weak momentum"
    else:
        rsi_signal = "🟡 Neutral momentum"

    if fast_ma_val is not None and slow_ma_val is not None:
        if current_price > fast_ma_val > slow_ma_val:
            sma_signal = f"🟢 Uptrend — price above MA{fast_ma}/MA{slow_ma}"
        elif current_price < fast_ma_val < slow_ma_val:
            sma_signal = f"🔴 Downtrend — price below MA{fast_ma}/MA{slow_ma}"
        elif fast_ma_val > slow_ma_val:
            sma_signal = f"🟡 Constructive — MA{fast_ma} above MA{slow_ma}, price needs confirmation"
        else:
            sma_signal = f"🟠 Weak trend — MA{fast_ma} below MA{slow_ma}"
    else:
        sma_signal = f"⚪ Insufficient data for MA{slow_ma} trend signal"

    support_val, resistance_val = _support_resistance(df, config["sr_days"])
    support_distance = _distance_pct(current_price, support_val)
    resistance_distance = _distance_pct(resistance_val, current_price)
    if support_val is not None and resistance_val is not None:
        rng = resistance_val - support_val
        pos = (current_price - support_val) / rng * 100 if rng > 0 else 50
        if pos <= 25:
            sr_signal = "🟢 Near support — better risk/reward zone"
        elif pos >= 75:
            sr_signal = "🔴 Near resistance — upside is crowded"
        else:
            sr_signal = "🟡 Mid-range — wait for cleaner edge"
    else:
        sr_signal = "N/A"

    if atr_pct_val is None:
        atr_signal = "N/A"
    elif atr_pct_val >= 4.0:
        atr_signal = "🔴 Very High Volatility"
    elif atr_pct_val >= 2.5:
        atr_signal = "🟠 High Volatility"
    elif atr_pct_val >= 1.3:
        atr_signal = "🟡 Moderate Volatility"
    else:
        atr_signal = "🟢 Low Volatility"

    ema_fast = close.ewm(span=macd_fast, adjust=False).mean()
    ema_slow = close.ewm(span=macd_slow, adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_Signal"] = df["MACD"].ewm(span=macd_signal_period, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    macd_val = _last_valid(df["MACD"])
    macd_sig_val = _last_valid(df["MACD_Signal"])
    macd_hist_val = _last_valid(df["MACD_Hist"])
    macd_hist_prev = df["MACD_Hist"].dropna().iloc[-2] if len(df["MACD_Hist"].dropna()) >= 2 else None

    if macd_val is not None and macd_sig_val is not None and len(df) >= 2:
        prev_macd = df["MACD"].iloc[-2]
        prev_sig = df["MACD_Signal"].iloc[-2]
        hist_improving = macd_hist_prev is not None and macd_hist_val > macd_hist_prev
        if prev_macd <= prev_sig and macd_val > macd_sig_val:
            macd_signal = "🟢 Bullish crossover"
        elif prev_macd >= prev_sig and macd_val < macd_sig_val:
            macd_signal = "🔴 Bearish crossover"
        elif macd_val > macd_sig_val and hist_improving:
            macd_signal = "🟢 Bullish momentum strengthening"
        elif macd_val > macd_sig_val:
            macd_signal = "🟢 Bullish momentum"
        elif macd_val < macd_sig_val and hist_improving:
            macd_signal = "🟡 Bearish momentum fading"
        elif macd_val < macd_sig_val:
            macd_signal = "🔴 Bearish momentum"
        else:
            macd_signal = "🟡 Neutral"
    else:
        macd_signal = "N/A"

    typical_price = (high + low + close) / 3
    raw_money_flow = typical_price * df["Volume"]
    tp_delta = typical_price.diff()
    pos_flow = raw_money_flow.where(tp_delta > 0, 0.0).rolling(14).sum()
    neg_flow = raw_money_flow.where(tp_delta < 0, 0.0).rolling(14).sum()
    money_ratio = pos_flow / neg_flow.replace(0, np.nan)
    df["MFI"] = 100 - (100 / (1 + money_ratio))

    mfi_val = _last_valid(df["MFI"])
    if mfi_val is None:
        mfi_signal = "N/A"
    elif mfi_val >= 80:
        mfi_signal = "🔴 Overbought flow — watch distribution"
    elif mfi_val <= 20:
        mfi_signal = "🟢 Oversold flow — potential accumulation"
    elif mfi_val >= 60:
        mfi_signal = "🟢 Strong inflow"
    elif mfi_val <= 40:
        mfi_signal = "🔴 Weak flow"
    else:
        mfi_signal = "🟡 Neutral money flow"

    obv_sign = np.sign(close.diff()).fillna(0)
    df["OBV"] = (obv_sign * df["Volume"]).cumsum()
    obv_val = _last_valid(df["OBV"])
    obv_sma = df["OBV"].rolling(20).mean()
    if len(obv_sma.dropna()) >= 10:
        obv_slope = float(obv_sma.iloc[-1] - obv_sma.iloc[-10])
        obv_slope_pct = obv_slope / max(abs(obv_sma.iloc[-10]), 1) * 100
    else:
        obv_slope = None
        obv_slope_pct = None

    if obv_slope_pct is not None:
        if obv_slope_pct > 3:
            obv_signal = "🟢 Rising OBV — volume confirms demand"
        elif obv_slope_pct < -3:
            obv_signal = "🔴 Falling OBV — volume confirms supply"
        else:
            obv_signal = "🟡 Flat OBV"
    else:
        obv_signal = "N/A"

    trend_score = 50.0
    if fast_ma_val is not None:
        trend_score += 12 if current_price > fast_ma_val else -12
    if slow_ma_val is not None:
        trend_score += 14 if current_price > slow_ma_val else -14
    if fast_ma_val is not None and slow_ma_val is not None:
        trend_score += 10 if fast_ma_val > slow_ma_val else -10
    if long_ma_val is not None:
        trend_score += 8 if current_price > long_ma_val else -8

    momentum_score = 50.0
    if rsi_val is not None:
        if rsi_val < rsi_low:
            momentum_score += 8
        elif rsi_val > rsi_high:
            momentum_score -= 10
        else:
            momentum_score += (rsi_val - 50) * 1.1
    if macd_val is not None and macd_sig_val is not None:
        momentum_score += 12 if macd_val > macd_sig_val else -12
    if macd_hist_prev is not None and macd_hist_val is not None:
        momentum_score += 6 if macd_hist_val > macd_hist_prev else -6

    volume_score = 50.0
    if mfi_val is not None:
        if 45 <= mfi_val <= 75:
            volume_score += (mfi_val - 50) * 0.8
        elif mfi_val > 80:
            volume_score -= 8
        elif mfi_val < 20:
            volume_score += 5
        else:
            volume_score += (mfi_val - 50) * 0.4
    if obv_slope_pct is not None:
        volume_score += np.clip(obv_slope_pct, -15, 15)

    range_score = 50.0
    if support_val is not None and resistance_val is not None and resistance_val > support_val:
        range_position = (current_price - support_val) / (resistance_val - support_val)
        range_score += (0.5 - range_position) * 30
        if current_price > resistance_val:
            range_score += 12
        elif current_price < support_val:
            range_score -= 12

    risk_score = 50.0
    if atr_pct_val is not None:
        risk_score += np.clip((2.2 - atr_pct_val) * 7, -22, 18)
    if realized_vol is not None:
        risk_score += np.clip((35 - realized_vol) * 0.25, -12, 12)

    components = {
        "trend": float(np.clip(trend_score, 0, 100)),
        "momentum": float(np.clip(momentum_score, 0, 100)),
        "volume": float(np.clip(volume_score, 0, 100)),
        "range": float(np.clip(range_score, 0, 100)),
        "risk": float(np.clip(risk_score, 0, 100)),
    }
    technical_score = sum(components[key] * weights[key] for key in components)

    available_components = sum(
        [
            fast_ma_val is not None and slow_ma_val is not None,
            rsi_val is not None and macd_val is not None,
            mfi_val is not None and obv_slope_pct is not None,
            support_val is not None and resistance_val is not None,
            atr_pct_val is not None and realized_vol is not None,
        ]
    )
    confidence = min(95, max(35, available_components / 5 * 80 + min(len(df), 252) / 252 * 15))
    recommendation = _score_to_signal(technical_score)

    entry_low = support_val
    if support_val is not None and atr_val is not None:
        entry_high = min(current_price, support_val + atr_val * 0.8)
    else:
        entry_high = current_price

    if atr_val is not None:
        stop_loss = current_price - atr_val * config["risk_multiple"]
        take_profit = current_price + atr_val * config["target_multiple"]
        if support_val is not None:
            stop_loss = min(stop_loss, support_val - atr_val * 0.35)
        if resistance_val is not None and resistance_val > current_price:
            take_profit = min(take_profit, resistance_val)
    else:
        stop_loss = support_val
        take_profit = resistance_val

    reward = take_profit - current_price if take_profit is not None else None
    risk = current_price - stop_loss if stop_loss is not None else None
    risk_reward = reward / risk if reward is not None and risk and risk > 0 else None

    price_bullish = rsi_val is not None and rsi_val > 50
    vol_bullish = (mfi_val is not None and mfi_val > 50) and (obv_slope is not None and obv_slope > 0)
    vol_bearish = (mfi_val is not None and mfi_val < 50) and (obv_slope is not None and obv_slope < 0)

    if price_bullish and vol_bullish:
        smart_money = "🟢 Accumulation — price rise supported by volume inflow"
    elif price_bullish and vol_bearish:
        smart_money = "🟠 Distribution Warning — price rising while volume weakens"
    elif not price_bullish and vol_bullish:
        smart_money = "🟢 Stealth Accumulation — weak price with improving volume"
    elif not price_bullish and vol_bearish:
        smart_money = "🔴 Distribution — weak price with volume outflow"
    else:
        smart_money = "🟡 Inconclusive — mixed volume signals"

    profile_reason = (
        f"Sector '{sector or 'N/A'}', ATR {atr_pct_val:.1f}%"
        if atr_pct_val is not None
        else f"Sector '{sector or 'N/A'}'"
    )
    if realized_vol is not None:
        profile_reason += f", realized volatility {realized_vol:.1f}%"
    beta_val = info.get("beta")
    if isinstance(beta_val, (int, float)) and not pd.isna(beta_val):
        profile_reason += f", beta {beta_val:.2f}"

    return {
        "profile": profile_key,
        "profile_label": config["label"],
        "profile_reason": profile_reason,
        "horizon": config["horizon"],
        "rsi_period": rsi_period,
        "fast_ma_period": fast_ma,
        "slow_ma_period": slow_ma,
        "long_ma_period": long_ma,
        "macd_params": config["macd"],
        "sr_lookback_days": config["sr_days"],
        "technical_score": float(np.clip(technical_score, 0, 100)),
        "confidence": float(confidence),
        "recommendation": recommendation,
        "score_components": components,
        "entry_zone": (_fmt_price(entry_low), _fmt_price(entry_high)),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_reward": risk_reward,
        "current_price": current_price,
        "realized_volatility": realized_vol,
        "support_distance_pct": support_distance,
        "resistance_distance_pct": resistance_distance,
        "rsi": rsi_val,
        "rsi_signal": rsi_signal,
        "sma50": sma50_val,
        "sma200": sma200_val,
        "fast_ma": fast_ma_val,
        "slow_ma": slow_ma_val,
        "long_ma": long_ma_val,
        "sma_signal": sma_signal,
        "support": support_val,
        "resistance": resistance_val,
        "sr_signal": sr_signal,
        "atr": atr_val,
        "atr_pct": atr_pct_val,
        "atr_signal": atr_signal,
        "macd": macd_val,
        "macd_signal_val": macd_sig_val,
        "macd_hist": macd_hist_val,
        "macd_signal": macd_signal,
        "mfi": mfi_val,
        "mfi_signal": mfi_signal,
        "obv": obv_val,
        "obv_signal": obv_signal,
        "smart_money": smart_money,
        "df": df,
    }
