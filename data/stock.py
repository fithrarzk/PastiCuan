import yfinance as yf
import pandas as pd


def get_stock_data(ticker: str) -> dict:
    """
    Fetches basic info, financial ratios, and 1-year historical
    price data for an Indonesian stock.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol. A '.JK' suffix is automatically appended
        if the symbol does not already end with it.

    Returns
    -------
    dict with keys:
        - ticker  : resolved ticker string (with .JK)
        - basic   : dict  - longName, sector
        - ratios  : dict  - PE, PBV, ROE, Debt-to-Equity, Net Profit Margin
        - history : pd.DataFrame - OHLCV for last 1 year
        - info    : raw yfinance info dict
        - error   : str | None
    """
    ticker = ticker.strip().upper()
    if not ticker.endswith(".JK"):
        ticker = ticker + ".JK"

    result = {
        "ticker": ticker,
        "basic": {},
        "ratios": {},
        "history": pd.DataFrame(),
        "info": {},
        "error": None,
    }

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # yfinance returns a minimal dict for invalid tickers
        if not info or (
            info.get("regularMarketPrice") is None
            and info.get("currentPrice") is None
            and info.get("previousClose") is None
        ):
            hist_check = stock.history(period="5d", auto_adjust=False, actions=True)
            if hist_check.empty:
                result["error"] = f"Ticker **{ticker}** not found or has no trading data."
                return result

        result["info"] = info

        result["basic"] = {
            "longName": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector") or "N/A",
        }

        def fmt_pct(val):
            return f"{val * 100:.2f}%" if val is not None else "N/A"

        def fmt_num(val, decimals=2):
            return f"{val:.{decimals}f}" if val is not None else "N/A"

        result["ratios"] = {
            "PE (Price-to-Earnings)": fmt_num(info.get("trailingPE")),
            "PBV (Price-to-Book)":    fmt_num(info.get("priceToBook")),
            "ROE (Return on Equity)": fmt_pct(info.get("returnOnEquity")),
            "Debt-to-Equity":         fmt_num(info.get("debtToEquity")),
            "Net Profit Margin":      fmt_pct(info.get("profitMargins")),
        }

        history = stock.history(period="1y", auto_adjust=False, actions=True)
        if history.empty:
            result["error"] = f"No historical price data available for **{ticker}**."
        else:
            result["history"] = history

    except Exception as exc:
        result["error"] = f"An error occurred while fetching data: {exc}"

    return result
