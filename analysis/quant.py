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


def compute_cross_sectional_factors(
    universe: pd.DataFrame,
    *,
    as_of=None,
    min_universe: int = 10,
    winsor_limits: tuple[float, float] = (0.05, 0.95),
) -> dict:
    """Rank point-in-time value/quality/momentum/low-volatility by sector.

    Required columns are ``ticker``, ``sector`` and any of the raw factor
    columns listed below. Rows must already be filtered to historical LQ45
    membership and facts available at ``as_of`` by the repository layer.
    """
    required = {"ticker", "sector"}
    if universe is None or universe.empty or not required.issubset(universe.columns):
        return {"status": "INSUFFICIENT_DATA", "reason": "Eligible point-in-time universe is missing.",
                "scores": pd.DataFrame(), "formula_version": "lq45-cross-section-v2"}
    if len(universe) < min_universe:
        return {"status": "INSUFFICIENT_DATA", "reason": f"At least {min_universe} eligible issuers are required.",
                "scores": pd.DataFrame(), "formula_version": "lq45-cross-section-v2"}

    df = universe.copy()
    definitions = {
        "value": {"earnings_yield": 1, "book_yield": 1, "dividend_yield": 1},
        "quality": {"roe": 1, "roic": 1, "cash_conversion": 1, "leverage": -1},
        "momentum": {"return_6m_skip_1m": 1, "return_12m_skip_1m": 1},
        "low_volatility": {"realized_volatility": -1, "downside_deviation": -1},
    }
    factor_scores: dict[str, pd.Series] = {}
    availability: dict[str, list[str]] = {}
    for factor, columns in definitions.items():
        ranked = []
        used = []
        for column, direction in columns.items():
            if column not in df:
                continue
            values = pd.to_numeric(df[column], errors="coerce")
            lo, hi = values.quantile(list(winsor_limits))
            values = values.clip(lo, hi)
            # Sector-aware percentile. Groups with fewer than five observations
            # cannot generate a factor component.
            counts = values.groupby(df["sector"]).transform("count")
            ranks = values.groupby(df["sector"]).rank(pct=True, method="average") * 100
            ranks = ranks.where(counts >= 5)
            ranked.append(ranks if direction > 0 else 100 - ranks)
            used.append(column)
        factor_scores[factor] = pd.concat(ranked, axis=1).mean(axis=1, skipna=True) if ranked else pd.Series(np.nan, index=df.index)
        availability[factor] = used
        df[factor] = factor_scores[factor]

    factor_frame = df[list(definitions)].copy()
    df["composite_percentile"] = factor_frame.mean(axis=1, skipna=True)
    df["coverage_pct"] = factor_frame.notna().mean(axis=1) * 100
    df.loc[df["coverage_pct"] == 0, "composite_percentile"] = np.nan
    return {
        "status": "AVAILABLE", "as_of": str(as_of) if as_of is not None else None,
        "scores": df[["ticker", "sector", *definitions, "composite_percentile", "coverage_pct"]],
        "available_inputs": availability, "formula_version": "lq45-cross-section-v2",
        "interpretation": "Relative eligible-universe percentile; not absolute investment quality.",
    }


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


def _available_weighted(parts: list[tuple[float | None, float]]) -> tuple[float | None, float]:
    available = [(value, weight) for value, weight in parts if value is not None]
    denominator = sum(weight for _, weight in available)
    if not denominator:
        return None, 0.0
    return float(sum(value * weight for value, weight in available) / denominator), denominator


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
    div_yield = info.get("dividendYield")

    ey = (1.0 / pe * 100) if (pe and pe > 0) else None
    by = (1.0 / pbv * 100) if (pbv and pbv > 0) else None

    # Score components
    ey_score = _clip((ey / 12.0) * 100) if ey is not None else None
    by_score = _clip(by) if by is not None else None
    dy_score = _clip((div_yield / 0.06) * 100) if div_yield is not None else None
    value_score, value_coverage = _available_weighted([(ey_score, .45), (by_score, .35), (dy_score, .20)])

    # 2. QUALITY FACTOR
    roe = info.get("returnOnEquity")
    roa = info.get("returnOnAssets")
    margin = info.get("profitMargins")
    dte = info.get("debtToEquity")

    roe_score = _clip((roe / 0.20) * 100) if roe is not None else None
    roa_score = _clip((roa / 0.10) * 100) if roa is not None else None
    margin_score = _clip((margin / 0.25) * 100) if margin is not None else None
    
    # Lower Debt-to-Equity is higher safety score
    is_bank = "bank" in sector_lower or "financial" in sector_lower
    dte_thresh = 600.0 if is_bank else 150.0
    dte_score = None if is_bank or dte is None else _clip(100.0 - (dte / dte_thresh) * 70.0)
    quality_score, quality_coverage = _available_weighted(
        [(roe_score, .35), (roa_score, .20), (margin_score, .25), (dte_score, .20)]
    )

    # 3. MOMENTUM FACTOR
    mom_1m = mom_3m = mom_6m = mom_sharpe = None

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

    m1_score = _clip(50.0 + mom_1m * 2.5) if mom_1m is not None else None
    m3_score = _clip(50.0 + mom_3m * 1.5) if mom_3m is not None else None
    m6_score = _clip(50.0 + mom_6m) if mom_6m is not None else None
    ms_score = _clip(50.0 + mom_sharpe * 25.0) if mom_sharpe is not None else None
    momentum_score, momentum_coverage = _available_weighted(
        [(m1_score, .25), (m3_score, .35), (m6_score, .20), (ms_score, .20)]
    )

    # 4. LOW VOLATILITY FACTOR
    beta = info.get("beta")
    beta_score = _clip(100.0 - (beta - 0.5) * 50.0) if beta is not None else None

    realized_vol = downside_vol = None
    if history is not None and not history.empty and "Close" in history.columns:
        returns = history["Close"].dropna().pct_change().dropna()
        if len(returns) >= 30:
            realized_vol = float(returns.tail(60).std() * np.sqrt(252) * 100)
            negative_rets = returns[returns < 0]
            if not negative_rets.empty:
                downside_vol = float(np.sqrt((negative_rets.tail(60) ** 2).mean()) * np.sqrt(252) * 100)

    vol_score = _clip(100.0 - (realized_vol / 50.0) * 80.0) if realized_vol is not None else None
    dvol_score = _clip(100.0 - (downside_vol / 35.0) * 80.0) if downside_vol is not None else None
    low_vol_score, low_vol_coverage = _available_weighted(
        [(vol_score, .45), (dvol_score, .35), (beta_score, .20)]
    )

    # DYNAMIC FACTOR WEIGHTING BY SECTOR
    if is_bank:
        w_val, w_qual, w_mom, w_vol = 0.30, 0.35, 0.20, 0.15
    elif any(k in sector_lower for k in ["tech", "growth"]):
        w_val, w_qual, w_mom, w_vol = 0.15, 0.25, 0.45, 0.15
    elif any(k in sector_lower for k in ["energy", "material", "mining", "coal"]):
        w_val, w_qual, w_mom, w_vol = 0.35, 0.20, 0.25, 0.20
    else:
        w_val, w_qual, w_mom, w_vol = 0.25, 0.25, 0.25, 0.25

    composite_quant_score, factor_coverage = _available_weighted([
        (value_score, w_val), (quality_score, w_qual),
        (momentum_score, w_mom), (low_vol_score, w_vol),
    ])

    return {
        "composite_score": composite_quant_score,
        "grade": _score_to_grade(composite_quant_score) if composite_quant_score is not None else "N/A",
        "status": "RESEARCH_ONLY_SINGLE_SECURITY" if composite_quant_score is not None else "INSUFFICIENT_DATA",
        "coverage_pct": factor_coverage * 100,
        "interpretation": "Compatibility diagnostic only; production grades require the LQ45 cross-section.",
        "factor_weights": {
            "value": w_val,
            "quality": w_qual,
            "momentum": w_mom,
            "low_volatility": w_vol,
        },
        "factors": {
            "value": {
                "score": value_score,
                "grade": _score_to_grade(value_score) if value_score is not None else "N/A",
                "coverage_pct": value_coverage * 100,
                "earnings_yield": ey,
                "book_yield": by,
                "dividend_yield": div_yield * 100 if div_yield is not None else None,
            },
            "quality": {
                "score": quality_score,
                "grade": _score_to_grade(quality_score) if quality_score is not None else "N/A",
                "coverage_pct": quality_coverage * 100,
                "roe": roe * 100 if roe is not None else None,
                "roa": roa * 100 if roa is not None else None,
                "net_margin": margin * 100 if margin is not None else None,
                "debt_to_equity": dte,
            },
            "momentum": {
                "score": momentum_score,
                "grade": _score_to_grade(momentum_score) if momentum_score is not None else "N/A",
                "coverage_pct": momentum_coverage * 100,
                "return_1m": mom_1m,
                "return_3m": mom_3m,
                "return_6m": mom_6m,
                "sharpe_momentum": mom_sharpe,
            },
            "low_volatility": {
                "score": low_vol_score,
                "grade": _score_to_grade(low_vol_score) if low_vol_score is not None else "N/A",
                "coverage_pct": low_vol_coverage * 100,
                "realized_volatility": realized_vol,
                "downside_volatility": downside_vol,
                "beta": beta,
            },
        },
    }
