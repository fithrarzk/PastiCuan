"""
Markowitz Mean-Variance Portfolio Optimizer for PastiCuan (Level 2 Quant).

Computes:
- Maximum Sharpe Ratio optimal portfolio allocation weights (%)
- Minimum Volatility portfolio weights (%)
- Efficient Frontier risk/return curves
- Expected Annual Return, Annualized Volatility, and Sharpe Ratio
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import yfinance as yf


def _normalize_ticker(t: str) -> str:
    t = t.strip().upper().replace(".JK", "")
    return t + ".JK"


def optimize_portfolio(
    tickers: list[str],
    period: str = "1y",
    risk_free_rate: float = 0.06,  # 6% BI rate proxy
) -> dict:
    """
    Runs Markowitz Mean-Variance Portfolio Optimization on a basket of tickers.
    """
    cleaned_tickers = [_normalize_ticker(t) for t in tickers if t.strip()]
    cleaned_tickers = list(dict.fromkeys(cleaned_tickers))  # Remove duplicates

    if len(cleaned_tickers) < 2:
        return {"error": "Please provide at least 2 valid ticker symbols for portfolio optimization."}

    # Fetch historical daily prices
    try:
        data = yf.download(cleaned_tickers, period=period, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"]
        else:
            prices = data[["Close"]] if "Close" in data else data
    except Exception as exc:
        return {"error": f"Failed to download price history for tickers: {exc}"}

    prices = prices.dropna(how="all").ffill().dropna()

    # Ensure all requested tickers have valid data
    valid_cols = [col for col in prices.columns if not prices[col].isna().all()]
    if len(valid_cols) < 2:
        return {"error": "Insufficient overlapping historical data across selected tickers."}

    prices = prices[valid_cols]
    display_tickers = [c.replace(".JK", "") for c in valid_cols]

    # Daily Returns & Annualized Metrics
    daily_returns = prices.pct_change().dropna()
    mean_returns = daily_returns.mean() * 252
    cov_matrix = daily_returns.cov() * 252

    num_assets = len(valid_cols)

    def portfolio_performance(weights):
        weights = np.array(weights)
        port_return = np.sum(mean_returns * weights)
        port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        sharpe = (port_return - risk_free_rate) / port_vol if port_vol > 0 else 0
        return port_return, port_vol, sharpe

    # Optimization 1: Maximize Sharpe Ratio
    def neg_sharpe(weights):
        return -portfolio_performance(weights)[2]

    constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
    bounds = tuple((0.0, 1.0) for _ in range(num_assets))
    init_weights = num_assets * [1.0 / num_assets]

    res_sharpe = minimize(neg_sharpe, init_weights, method='SLSQP', bounds=bounds, constraints=constraints)
    max_sharpe_weights = res_sharpe.x if res_sharpe.success else init_weights

    ret_max, vol_max, sharpe_max = portfolio_performance(max_sharpe_weights)

    # Optimization 2: Minimum Volatility
    def min_volatility(weights):
        return portfolio_performance(weights)[1]

    res_vol = minimize(min_volatility, init_weights, method='SLSQP', bounds=bounds, constraints=constraints)
    min_vol_weights = res_vol.x if res_vol.success else init_weights

    ret_min_v, vol_min_v, sharpe_min_v = portfolio_performance(min_vol_weights)

    # Generate Efficient Frontier points
    target_returns = np.linspace(mean_returns.min(), mean_returns.max(), 25)
    efficient_frontier = []

    for target in target_returns:
        cons = (
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1},
            {'type': 'eq', 'fun': lambda w: portfolio_performance(w)[0] - target}
        )
        res_ef = minimize(min_volatility, init_weights, method='SLSQP', bounds=bounds, constraints=cons)
        if res_ef.success:
            r, v, s = portfolio_performance(res_ef.x)
            efficient_frontier.append({"return": float(r * 100), "volatility": float(v * 100)})

    # Format result outputs
    opt_alloc = {
        ticker: round(float(weight * 100), 2)
        for ticker, weight in zip(display_tickers, max_sharpe_weights)
    }

    min_vol_alloc = {
        ticker: round(float(weight * 100), 2)
        for ticker, weight in zip(display_tickers, min_vol_weights)
    }

    eq_alloc = {
        ticker: round(100.0 / num_assets, 2)
        for ticker in display_tickers
    }

    return {
        "tickers": display_tickers,
        "max_sharpe": {
            "weights": opt_alloc,
            "expected_return": float(ret_max * 100),
            "volatility": float(vol_max * 100),
            "sharpe_ratio": float(sharpe_max),
        },
        "min_volatility": {
            "weights": min_vol_alloc,
            "expected_return": float(ret_min_v * 100),
            "volatility": float(vol_min_v * 100),
            "sharpe_ratio": float(sharpe_min_v),
        },
        "equal_weight": {
            "weights": eq_alloc,
            "expected_return": float(portfolio_performance(init_weights)[0] * 100),
            "volatility": float(portfolio_performance(init_weights)[1] * 100),
            "sharpe_ratio": float(portfolio_performance(init_weights)[2]),
        },
        "efficient_frontier": efficient_frontier,
    }
