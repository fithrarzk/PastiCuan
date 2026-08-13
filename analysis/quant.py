"""
Multi-Factor Quantitative Equity Engine for PastiCuan (Level 2 Quant).

Evaluates 4 core Quant Factors:
1. Value Factor (Earnings Yield, Book Yield, Div Yield)
2. Quality Factor (ROE, ROA, Net Margin, Debt Safety)
3. Momentum Factor (1M, 3M, 6M Risk-Adjusted Momentum)
4. Low Volatility Factor (Realized Volatility, Downside Vol, Beta)
"""

import numpy as np
import pandas as pd


def _clip(val, low=0.0, high=100.0):
    return float(max(low, min(high, val)))


def _score_to_grade(score: float) -> str:
    if score >= 80:
        return "A+"
    if score >= 70:
        return "A"
    if score >= 60:
        return "B"
    if score >= 50:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def compute_quant_factors(
    info: dict,
    history: pd.DataFrame,
    sector: str | None = None,
    quarterly_income: pd.DataFrame | None = None,
    quarterly_balance: pd.DataFrame | None = None,
) -> dict:
    """
    Computes a comprehensive Multi-Factor Quant Model for an individual stock.
    Returns normalized scores (0-100) for Value, Quality, Momentum, and Low Volatility.
    """
    info = info or {}
    sector_lower = (sector or "").lower()

    # 1. VALUE FACTOR
    pe = info.get("trailingPE")
    pbv = info.get("priceToBook")
    div_yield = info.get("dividendYield") or 0.0

    ey = (1.0 / pe * 100) if (pe and pe > 0) else 0.0
    by = (1.0 / pbv * 100) if (pbv and pbv > 0) else 0.0

    # Score components
    ey_score = _clip((ey / 12.0) * 100) if ey > 0 else 30.0
    by_score = _clip((by / 100.0) * 100) if by > 0 else 30.0
    dy_score = _clip((div_yield / 0.06) * 100)

    value_score = _clip(ey_score * 0.45 + by_score * 0.35 + dy_score * 0.20)

    # 2. QUALITY FACTOR
    roe = info.get("returnOnEquity") or 0.0
    roa = info.get("returnOnAssets") or 0.0
    margin = info.get("profitMargins") or 0.0
    dte = info.get("debtToEquity") or 50.0

    roe_score = _clip((roe / 0.20) * 100)
    roa_score = _clip((roa / 0.10) * 100)
    margin_score = _clip((margin / 0.25) * 100)
    
    # Lower Debt-to-Equity is higher safety score
    is_bank = "bank" in sector_lower or "financial" in sector_lower
    dte_thresh = 600.0 if is_bank else 150.0
    dte_score = _clip(100.0 - (dte / dte_thresh) * 70.0)

    quality_score = _clip(roe_score * 0.35 + roa_score * 0.20 + margin_score * 0.25 + dte_score * 0.20)

    # 3. MOMENTUM FACTOR
    mom_1m = 0.0
    mom_3m = 0.0
    mom_6m = 0.0
    mom_sharpe = 0.0

    if history is not None and not history.empty and "Close" in history.columns:
        close = history["Close"].dropna()
        if len(close) >= 20:
            mom_1m = float((close.iloc[-1] / close.iloc[-20] - 1) * 100)
        if len(close) >= 60:
            mom_3m = float((close.iloc[-1] / close.iloc[-60] - 1) * 100)
        if len(close) >= 120:
            mom_6m = float((close.iloc[-1] / close.iloc[-120] - 1) * 100)

        daily_ret = close.pct_change().dropna()
        if len(daily_ret) >= 60:
            ann_vol = float(daily_ret.tail(60).std() * np.sqrt(252) * 100)
            if ann_vol > 0:
                mom_sharpe = (mom_3m / ann_vol)

    m1_score = _clip(50.0 + mom_1m * 2.5)
    m3_score = _clip(50.0 + mom_3m * 1.5)
    m6_score = _clip(50.0 + mom_6m * 1.0)
    ms_score = _clip(50.0 + mom_sharpe * 25.0)

    momentum_score = _clip(m1_score * 0.25 + m3_score * 0.35 + m6_score * 0.20 + ms_score * 0.20)

    # 4. LOW VOLATILITY FACTOR
    beta = info.get("beta") or 1.0
    beta_score = _clip(100.0 - (beta - 0.5) * 50.0)

    realized_vol = 30.0
    downside_vol = 20.0
    if history is not None and not history.empty and "Close" in history.columns:
        returns = history["Close"].dropna().pct_change().dropna()
        if len(returns) >= 30:
            realized_vol = float(returns.tail(60).std() * np.sqrt(252) * 100)
            negative_rets = returns[returns < 0]
            if not negative_rets.empty:
                downside_vol = float(negative_rets.tail(60).std() * np.sqrt(252) * 100)

    vol_score = _clip(100.0 - (realized_vol / 50.0) * 80.0)
    dvol_score = _clip(100.0 - (downside_vol / 35.0) * 80.0)

    low_vol_score = _clip(vol_score * 0.45 + dvol_score * 0.35 + beta_score * 0.20)

    # DYNAMIC FACTOR WEIGHTING BY SECTOR
    if is_bank:
        w_val, w_qual, w_mom, w_vol = 0.30, 0.35, 0.20, 0.15
    elif any(k in sector_lower for k in ["tech", "growth"]):
        w_val, w_qual, w_mom, w_vol = 0.15, 0.25, 0.45, 0.15
    elif any(k in sector_lower for k in ["energy", "material", "mining", "coal"]):
        w_val, w_qual, w_mom, w_vol = 0.35, 0.20, 0.25, 0.20
    else:
        w_val, w_qual, w_mom, w_vol = 0.25, 0.25, 0.25, 0.25

    composite_quant_score = _clip(
        value_score * w_val +
        quality_score * w_qual +
        momentum_score * w_mom +
        low_vol_score * w_vol
    )

    return {
        "composite_score": composite_quant_score,
        "grade": _score_to_grade(composite_quant_score),
        "factor_weights": {
            "value": w_val,
            "quality": w_qual,
            "momentum": w_mom,
            "low_volatility": w_vol,
        },
        "factors": {
            "value": {
                "score": value_score,
                "grade": _score_to_grade(value_score),
                "earnings_yield": ey,
                "book_yield": by,
                "dividend_yield": div_yield * 100,
            },
            "quality": {
                "score": quality_score,
                "grade": _score_to_grade(quality_score),
                "roe": roe * 100,
                "roa": roa * 100,
                "net_margin": margin * 100,
                "debt_to_equity": dte,
            },
            "momentum": {
                "score": momentum_score,
                "grade": _score_to_grade(momentum_score),
                "return_1m": mom_1m,
                "return_3m": mom_3m,
                "return_6m": mom_6m,
                "sharpe_momentum": mom_sharpe,
            },
            "low_volatility": {
                "score": low_vol_score,
                "grade": _score_to_grade(low_vol_score),
                "realized_volatility": realized_vol,
                "downside_volatility": downside_vol,
                "beta": beta,
            },
        },
    }
