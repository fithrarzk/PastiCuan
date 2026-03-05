import os

import streamlit as st
from dotenv import load_dotenv

from data.stock import get_stock_data
from analysis.technical import analyze_technical
from analysis.fundamental import analyze_fundamental
from analysis.ai import generate_ai_analysis
from ui.charts import render_price_chart
from ui.components import render_ratios, render_technical_summary, render_fundamental_analysis

load_dotenv()


def main():
    st.set_page_config(
        page_title="PastiCuan – IDX Stock Analyzer",
        page_icon="📈",
        layout="wide",
    )

    # ── Sidebar ──────────────────────────────────────────────────────
    with st.sidebar:
        st.title("📈 PastiCuan")
        st.caption("Indonesian Stock (IDX) Analyzer")
        st.divider()

        ticker_input = st.text_input(
            "Stock Ticker",
            placeholder="e.g. BBCA or BBCA.JK",
            help="Enter the IDX stock ticker. '.JK' suffix will be added automatically.",
        )

        analyze_btn = st.button("Analyze", use_container_width=True, type="primary")

        st.divider()
        st.caption("Data source: Yahoo Finance (yfinance)")
        st.caption("Prices in IDR (Indonesian Rupiah)")

    # ── Main area ─────────────────────────────────────────────────────
    if not ticker_input or not analyze_btn:
        st.markdown("## Welcome to PastiCuan 👋")
        st.info(
            "Enter a stock ticker in the **sidebar** (e.g. `BBCA`, `TLKM`, `BMRI`) "
            "and click **Analyze** to see financial data and price history.",
            icon="👈",
        )
        st.stop()

    with st.spinner(f"Fetching data for **{ticker_input.upper()}** …"):
        data = get_stock_data(ticker_input)

    if data["error"]:
        st.error(data["error"])
        st.stop()

    ticker  = data["ticker"]
    basic   = data["basic"]
    ratios  = data["ratios"]
    history = data["history"]
    info    = data["info"]
    sector  = basic["sector"]

    tech = analyze_technical(history)
    fund = analyze_fundamental(info, sector)

    # ── Header ───────────────────────────────────────────────────────
    st.title(basic["longName"])
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.caption(f"🏷 Ticker: `{ticker}`")
        st.caption(f"🏢 Sector: **{sector}**")
    with col_h2:
        if not history.empty:
            latest_close = history["Close"].iloc[-1]
            prev_close   = history["Close"].iloc[-2] if len(history) > 1 else latest_close
            pct_change   = (latest_close - prev_close) / prev_close * 100
            st.metric(
                label="Last Close (IDR)",
                value=f"Rp {latest_close:,.0f}",
                delta=f"{pct_change:+.2f}%",
            )

    st.divider()

    st.subheader("📊 Financial Ratios")
    render_ratios(ratios)

    st.divider()

    st.subheader("🏦 Fundamental Valuation")
    render_fundamental_analysis(fund)

    st.divider()

    st.subheader("📡 Technical Indicators")
    render_technical_summary(tech)

    st.divider()

    # ── AI-Powered Analysis ──────────────────────────────────────────
    st.subheader("🤖 AI-Powered Analysis")
    if os.environ.get("GEMINI_API_KEY"):
        with st.spinner("Generating AI analysis …"):
            ai_result = generate_ai_analysis(fund, tech, ticker)
        st.markdown(ai_result)
    else:
        st.info(
            "Set `GEMINI_API_KEY` in your `.env` file to enable AI-powered analysis.",
            icon="🔑",
        )

    st.divider()

    st.subheader("📉 Price History (1 Year)")
    render_price_chart(tech, ticker)

    with st.expander("📋 Raw Historical Data"):
        fmt_hist = history[["Open", "High", "Low", "Close", "Volume"]].copy()
        fmt_hist.index = fmt_hist.index.strftime("%Y-%m-%d")
        st.dataframe(fmt_hist.sort_index(ascending=False), use_container_width=True)


if __name__ == "__main__":
    main()
