"""Watchlist scanner tab."""

import pandas as pd
import streamlit as st

from analysis.backtest import backtest_technical_strategy
from analysis.decision import build_decision_report
from analysis.fundamental import analyze_fundamental
from analysis.technical import analyze_technical
from data.extended import get_extended_data


def _liquidity_from_history(history: pd.DataFrame) -> dict:
    if history is None or history.empty:
        return {"avg_volume": None, "avg_value": None}
    tail = history.tail(min(len(history), 60))
    avg_volume = float(tail["Volume"].fillna(0).mean()) if "Volume" in tail else None
    avg_value = float((tail["Close"] * tail["Volume"].fillna(0)).mean()) if {"Close", "Volume"}.issubset(tail.columns) else None
    return {"avg_volume": avg_volume, "avg_value": avg_value}


def _normalize_input(value: str) -> list[str]:
    tickers = []
    for raw in value.split(","):
        ticker = raw.strip().upper()
        if ticker:
            tickers.append(ticker)
    return list(dict.fromkeys(tickers))


def render_scanner_tab(period_yf: str) -> None:
    st.caption("Rank a small IDX watchlist using the same decision engine as the single-stock view.")
    ticker_input = st.text_area(
        "Watchlist Tickers",
        value="BBCA, BBRI, BMRI, ADRO, PTBA",
        height=80,
        help="Comma-separated IDX tickers. Keep this to around 5-8 names for a responsive scan.",
    )
    c1, c2, c3 = st.columns(3)
    min_rr = c1.number_input("Minimum Risk/Reward", min_value=0.0, value=0.8, step=0.1)
    min_avg_value = c2.number_input("Minimum Avg Value Traded (IDR)", min_value=0, value=1_000_000_000, step=500_000_000)
    only_uptrend = c3.checkbox("Only Uptrend", value=False)

    if not st.button("Run Scanner", type="primary"):
        return

    tickers = _normalize_input(ticker_input)[:8]
    if not tickers:
        st.warning("Enter at least one ticker.")
        return

    rows = []
    progress = st.progress(0)
    for idx, ticker in enumerate(tickers, start=1):
        progress.progress(idx / len(tickers), text=f"Scanning {ticker}...")
        data = get_extended_data(ticker, period=period_yf)
        if data.get("error") or data["history"].empty:
            rows.append({"Ticker": ticker, "Status": data.get("error", "No data")})
            continue

        history = data["history"]
        info = data["info"]
        sector = data["basic"].get("sector", "N/A")
        tech = analyze_technical(history, sector=sector, info=info)
        fund = analyze_fundamental(
            info,
            sector,
            quarterly_income=data.get("quarterly_income"),
            quarterly_balance=data.get("quarterly_balance"),
        )
        backtest = backtest_technical_strategy(history, sector=sector, info=info)
        liquidity = _liquidity_from_history(history)
        decision = build_decision_report(tech, fund, backtest=backtest, liquidity=liquidity)

        rr = tech.get("risk_reward")
        avg_value = liquidity.get("avg_value") or 0
        trend_ok = "Uptrend" in tech.get("sma_signal", "") or "Constructive" in tech.get("sma_signal", "")
        passes = (rr is None or rr >= min_rr) and avg_value >= min_avg_value and (trend_ok or not only_uptrend)

        rows.append({
            "Ticker": data["ticker"],
            "Company": data["basic"].get("longName", data["ticker"]),
            "Verdict": decision.get("final_verdict"),
            "Final Score": round(decision.get("final_score", 0), 1),
            "Technical": round(tech.get("technical_score", 0), 1),
            "Fundamental": round(fund.get("fundamental_score", 0), 1),
            "Backtest Win Rate": round(backtest.get("summary", {}).get("win_rate", 0), 1),
            "Risk/Reward": round(rr, 2) if rr is not None else None,
            "Avg Value": avg_value,
            "Status": "Pass" if passes else "Filtered",
        })
    progress.empty()

    result = pd.DataFrame(rows)
    if result.empty:
        st.info("No scanner results.")
        return
    if "Final Score" in result.columns:
        result = result.sort_values("Final Score", ascending=False, na_position="last")
    st.dataframe(result, use_container_width=True, hide_index=True)
