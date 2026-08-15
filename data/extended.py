"""Extended data fetching for multi-year analysis and multi-ticker comparison."""

import os

import yfinance as yf
import pandas as pd


def _normalize_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    return ticker if ticker.endswith(".JK") else ticker + ".JK"


def _normalize_info_currency(info: dict) -> dict:
    """Do not guess FX or rewrite provider fundamentals.

    The authoritative pipeline converts each statement fact with the correct
    point-in-time rate. This Yahoo compatibility adapter only flags mismatches.
    """
    if not info:
        return info
    info = info.copy()
    fin_curr = info.get("financialCurrency")
    curr = info.get("currency", "IDR")
    info["_currency_alignment_status"] = (
        "AVAILABLE" if not fin_curr or fin_curr == curr else "INSUFFICIENT_DATA"
    )
    return info


def get_extended_data(ticker: str, period: str = "3y", *, include_fundamentals: bool = True) -> dict:
    ticker = _normalize_ticker(ticker)
    result = {
        "ticker": ticker,
        "basic": {},
        "ratios": {},
        "history": pd.DataFrame(),
        "info": {},
        "quarterly_income": pd.DataFrame(),
        "quarterly_balance": pd.DataFrame(),
        "quarterly_cashflow": pd.DataFrame(),
        "fundamental_source": {
            "provider": "Yahoo Finance",
            "source_class": "yahoo_fallback",
            "source_url": f"https://finance.yahoo.com/quote/{ticker}",
            "published_at": None,
        },
        "error": None,
    }
    request_timeout = max(5.0, min(30.0, float(os.getenv("YAHOO_REQUEST_TIMEOUT", "12"))))
    try:
        # yfinance owns a process-wide singleton session. Supplying and closing
        # a different session per ticker races under the full-universe scanner:
        # one worker can close the session another worker has just installed.
        stock = yf.Ticker(ticker)
        # Price history is the minimum viable evidence and uses Yahoo's chart
        # endpoint. Fetch it before the crumb-dependent quote-summary endpoint
        # so a fundamentals authentication failure cannot discard usable OHLCV.
        history = stock.history(period=period, auto_adjust=False, actions=True, timeout=request_timeout)
        if history.empty:
            result["error"] = f"No historical price data available for {ticker}."
            return result
        history = history.dropna(subset=["Close"])
        result["history"] = history

        info = {}
        if include_fundamentals:
            try:
                info = _normalize_info_currency(stock.info)
            except Exception as exc:
                result["fundamental_source"]["status"] = "UNAVAILABLE"
                result["fundamental_source"]["warning"] = type(exc).__name__
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
        if include_fundamentals:
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
            try:
                qcf = stock.quarterly_cash_flow
                if qcf is not None and not qcf.empty:
                    result["quarterly_cashflow"] = qcf
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
            hist = stock.history(period=period, auto_adjust=False, actions=True)
            if not hist.empty:
                result[t] = hist
        except Exception:
            pass
    return result
