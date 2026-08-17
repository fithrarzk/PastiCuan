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


def allocate_lots(
    weights: dict[str, float],
    prices: dict[str, float],
    available_cash: float,
    *,
    lot_size: int = 100,
) -> dict:
    """Convert long-only target weights to affordable IDX lots.

    ``weights`` may be fractions or percentages. Rounding is always downward so
    the result cannot create leverage or spend unavailable cash.
    """
    if available_cash <= 0 or lot_size <= 0:
        return {"error": "Cash and lot size must be positive.", "allocations": {}, "cash_remaining": available_cash}
    total = sum(max(0.0, float(weight)) for weight in weights.values())
    if total <= 0:
        return {"error": "At least one positive long-only weight is required.", "allocations": {}, "cash_remaining": available_cash}
    allocations, spent = {}, 0.0
    for ticker, weight in weights.items():
        price = float(prices.get(ticker, 0) or 0)
        normalized = max(0.0, float(weight)) / total
        lots = int((available_cash * normalized) // (price * lot_size)) if price > 0 else 0
        value = lots * lot_size * price
        allocations[ticker] = {"weight_target": normalized, "lots": lots,
                               "shares": lots * lot_size, "value": value}
        spent += value
    return {"error": None, "allocations": allocations, "invested": spent,
            "cash_remaining": available_cash - spent, "lot_size": lot_size}


def optimize_portfolio(
    tickers: list[str],
    period: str = "3y",
    risk_free_rate: float | None = None,
    max_position: float = 0.50,
    shrinkage: float = 0.25,
    price_history: pd.DataFrame | None = None,
) -> dict:
    """
    Runs Markowitz Mean-Variance Portfolio Optimization on a basket of tickers.
    """
    cleaned_tickers = [_normalize_ticker(t) for t in tickers if t.strip()]
    cleaned_tickers = list(dict.fromkeys(cleaned_tickers))  # Remove duplicates

    if len(cleaned_tickers) < 2:
        return {"error": "Please provide at least 2 valid ticker symbols for portfolio optimization."}

    # Fetch historical daily prices
    if price_history is not None:
        prices = price_history.copy()
    else:
        try:
            data = yf.download(cleaned_tickers, period=period, progress=False, auto_adjust=False, actions=True)
            if isinstance(data.columns, pd.MultiIndex):
                prices = data["Adj Close"] if "Adj Close" in data.columns.get_level_values(0) else data["Close"]
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
    if len(daily_returns) < 504:
        return {"error": "At least 504 overlapping completed sessions are required."}
    mean_returns = daily_returns.mean() * 252
    sample_cov = daily_returns.cov() * 252
    diagonal = pd.DataFrame(np.diag(np.diag(sample_cov)), index=sample_cov.index, columns=sample_cov.columns)
    cov_matrix = (1 - shrinkage) * sample_cov + shrinkage * diagonal

    num_assets = len(valid_cols)

    def portfolio_performance(weights):
        weights = np.array(weights)
        port_return = np.sum(mean_returns * weights)
        port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        sharpe = ((port_return - risk_free_rate) / port_vol
                  if risk_free_rate is not None and port_vol > 0 else None)
        return port_return, port_vol, sharpe

    # Optimization 1: Maximize Sharpe Ratio
    def neg_sharpe(weights):
        sharpe = portfolio_performance(weights)[2]
        return -sharpe if sharpe is not None else 0.0

    constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
    if max_position * num_assets < 1:
        return {"error": "Position cap is infeasible for the number of selected assets."}
    bounds = tuple((0.0, max_position) for _ in range(num_assets))
    init_weights = num_assets * [1.0 / num_assets]

    if risk_free_rate is None:
        res_sharpe = None
        max_sharpe_weights = None
        ret_max = vol_max = sharpe_max = None
    else:
        res_sharpe = minimize(neg_sharpe, init_weights, method='SLSQP', bounds=bounds, constraints=constraints)
        if not res_sharpe.success:
            return {"error": f"Maximum-Sharpe optimization failed: {res_sharpe.message}"}
        max_sharpe_weights = res_sharpe.x
        ret_max, vol_max, sharpe_max = portfolio_performance(max_sharpe_weights)

    # Optimization 2: Minimum Volatility
    def min_volatility(weights):
        return portfolio_performance(weights)[1]

    res_vol = minimize(min_volatility, init_weights, method='SLSQP', bounds=bounds, constraints=constraints)
    if not res_vol.success:
        return {"error": f"Minimum-volatility optimization failed: {res_vol.message}"}
    min_vol_weights = res_vol.x

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
    } if max_sharpe_weights is not None else {}

    min_vol_alloc = {
        ticker: round(float(weight * 100), 2)
        for ticker, weight in zip(display_tickers, min_vol_weights)
    }
    portfolio_variance = float(np.dot(min_vol_weights.T, np.dot(cov_matrix, min_vol_weights)))
    marginal = np.dot(cov_matrix, min_vol_weights)
    risk_contributions = (
        min_vol_weights * marginal / portfolio_variance if portfolio_variance > 0 else np.zeros(num_assets)
    )

    eq_alloc = {
        ticker: round(100.0 / num_assets, 2)
        for ticker in display_tickers
    }

    return {
        "tickers": display_tickers,
        "max_sharpe": {
            "weights": opt_alloc,
            "expected_return": float(ret_max * 100) if ret_max is not None else None,
            "volatility": float(vol_max * 100) if vol_max is not None else None,
            "sharpe_ratio": float(sharpe_max) if sharpe_max is not None else None,
            "status": "EXPERIMENTAL" if risk_free_rate is not None else "UNAVAILABLE_WITHOUT_POLICY_RATE",
        },
        "min_volatility": {
            "weights": min_vol_alloc,
            "expected_return": None,
            "historical_annualized_return": float(ret_min_v * 100),
            "volatility": float(vol_min_v * 100),
            "sharpe_ratio": float(sharpe_min_v) if sharpe_min_v is not None else None,
            "risk_contributions": {
                ticker: round(float(value * 100), 2)
                for ticker, value in zip(display_tickers, risk_contributions)
            },
        },
        "equal_weight": {
            "weights": eq_alloc,
            "expected_return": None,
            "historical_annualized_return": float(portfolio_performance(init_weights)[0] * 100),
            "volatility": float(portfolio_performance(init_weights)[1] * 100),
            "sharpe_ratio": (float(portfolio_performance(init_weights)[2])
                             if portfolio_performance(init_weights)[2] is not None else None),
        },
        "efficient_frontier": efficient_frontier,
        "default_allocation": "min_volatility",
        "covariance_method": f"diagonal shrinkage ({shrinkage:.2f})",
        "observations": int(len(daily_returns)),
        "constraints": {"long_only": True, "leverage": False, "max_position": max_position},
        "risk_free_rate": risk_free_rate,
        "return_model_status": "UNAVAILABLE",
    }
