"""Extended data fetching for multi-year analysis and multi-ticker comparison."""

import yfinance as yf
import pandas as pd


def _normalize_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    return ticker if ticker.endswith(".JK") else ticker + ".JK"


def _normalize_info_currency(info: dict) -> dict:
    if not info:
        return info
    info = info.copy()
    fin_curr = info.get("financialCurrency")
    curr = info.get("currency", "IDR")
    
    if fin_curr == "USD" and curr == "IDR":
        try:
            usdidr_hist = yf.Ticker("USDIDR=X").history(period="5d")
            rate = float(usdidr_hist["Close"].dropna().iloc[-1]) if not usdidr_hist.empty else 16300.0
        except Exception:
            rate = 16300.0

        price = info.get("currentPrice") or info.get("previousClose") or info.get("regularMarketPrice")
        bv = info.get("bookValue")
        if bv and price and price > 0:
            bv_idr = bv * rate
            info["bookValue"] = bv_idr
            info["priceToBook"] = price / bv_idr
            
    return info


def get_extended_data(ticker: str, period: str = "3y") -> dict:
    ticker = _normalize_ticker(ticker)
    result = {
        "ticker": ticker,
        "basic": {},
        "ratios": {},
        "history": pd.DataFrame(),
        "info": {},
        "quarterly_income": pd.DataFrame(),
        "quarterly_balance": pd.DataFrame(),
        "error": None,
    }
    try:
        stock = yf.Ticker(ticker)
        info = _normalize_info_currency(stock.info)

        if not info or (
            info.get("regularMarketPrice") is None
            and info.get("currentPrice") is None
            and info.get("previousClose") is None
        ):
            hist_check = stock.history(period="5d")
            if hist_check.empty:
                result["error"] = f"Ticker **{ticker}** not found or has no trading data."
                return result
        result["info"] = info
        result["basic"] = {
            "longName": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector") or "N/A",
            "marketCap": info.get("marketCap"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
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
        history = stock.history(period=period)
        if history.empty:
            result["error"] = f"No historical price data available for **{ticker}**."
            return result
        history = history.dropna(subset=["Close"])
        result["history"] = history

        try:
            qi = stock.quarterly_income_stmt
            if qi is not None and not qi.empty:
                result["quarterly_income"] = qi
        except Exception:
            pass
        try:
            qb = stock.quarterly_balance_sheet
            if qb is not None and not qb.empty:
                result["quarterly_balance"] = qb
        except Exception:
            pass
    except Exception as exc:
        result["error"] = f"An error occurred while fetching data: {exc}"
    return result


def get_comparison_data(tickers: list, period: str = "3y") -> dict:
    result = {}
    for t in tickers:
        t = _normalize_ticker(t)
        try:
            stock = yf.Ticker(t)
            hist = stock.history(period=period)
            if not hist.empty:
                result[t] = hist
        except Exception:
            pass
    return result
