import yfinance as yf
import streamlit as st
from dotenv import load_dotenv

from data.extended import get_extended_data
from analysis.technical import analyze_technical
from analysis.fundamental import analyze_fundamental
from analysis.valuation_bands import compute_valuation_bands
from analysis.seasonality import compute_seasonality
from ui.tabs import (
    render_dashboard_tab,
    render_valuation_tab,
    render_comparison_tab,
    render_seasonality_tab,
    render_technical_tab,
)

load_dotenv()

PERIOD_MAP = {"3 Years": "3y", "5 Years": "5y", "Max": "max"}


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
            value="BBCA",
            placeholder="e.g. BBCA or BBCA.JK",
            help="Enter the IDX stock ticker. '.JK' suffix will be added automatically.",
        )

        period_label = st.selectbox(
            "Analysis Period",
            options=list(PERIOD_MAP.keys()),
            index=0,
        )
        period_yf = PERIOD_MAP[period_label]

        analyze_btn = st.button("🔍 Analyze", use_container_width=True, type="primary")

        st.divider()
        st.caption("Data source: Yahoo Finance (yfinance)")
        st.caption("Prices in IDR (Indonesian Rupiah)")

    # ── Welcome screen ────────────────────────────────────────────────
    if not ticker_input:
        st.markdown("## Welcome to PastiCuan 👋")
        st.info(
            "Enter a stock ticker in the **sidebar** (e.g. `BBCA`, `TLKM`, `BMRI`) "
            "and click **Analyze** to see financial data and price history.",
            icon="👈",
        )
        st.stop()

    # ── Session-state cache key ───────────────────────────────────────
    request_key = (ticker_input.strip().upper(), period_yf)
    if analyze_btn or st.session_state.get("last_request") != request_key:
        # Clear all cached data when ticker/period change
        if st.session_state.get("last_request") != request_key:
            st.session_state["ai_result"] = None
        st.session_state["last_request"] = request_key

        with st.spinner(f"Fetching {period_label} data for **{ticker_input.upper()}** …"):
            data = get_extended_data(ticker_input, period=period_yf)

        if data["error"]:
            st.error(data["error"])
            st.stop()

        ticker  = data["ticker"]
        history = data["history"]
        info    = data["info"]
        sector  = data["basic"].get("sector", "N/A")

        tech  = analyze_technical(history)
        fund  = analyze_fundamental(info, sector)
        bands = compute_valuation_bands(
            history,
            data["quarterly_income"],
            data["quarterly_balance"],
            info,
        )
        seasonality = compute_seasonality(history)

        # Fetch 10-year history specifically for seasonality analysis
        try:
            hist_10y = yf.Ticker(ticker).history(period="10y")
            if not hist_10y.empty:
                seasonality = compute_seasonality(hist_10y)
        except Exception:
            pass  # fall back to the period-based seasonality computed above

        st.session_state["fetched_data"]  = data
        st.session_state["tech"]          = tech
        st.session_state["fund"]          = fund
        st.session_state["bands"]         = bands
        st.session_state["seasonality"]   = seasonality

    elif not st.session_state.get("fetched_data"):
        st.markdown("## Welcome to PastiCuan 👋")
        st.info("Click **Analyze** in the sidebar to load data.", icon="👈")
        st.stop()

    data        = st.session_state["fetched_data"]
    tech        = st.session_state["tech"]
    fund        = st.session_state["fund"]
    bands       = st.session_state["bands"]
    seasonality = st.session_state["seasonality"]
    ticker      = data["ticker"]
    basic       = data["basic"]

    # ── Header ────────────────────────────────────────────────────────
    col_title, col_price = st.columns([3, 1])
    with col_title:
        st.title(basic["longName"])
        st.markdown(
            f"🏷 **Ticker:** `{ticker}` &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"🏢 **Sector:** {basic.get('sector', 'N/A')} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"🗓 **Period:** {period_label}"
        )
    with col_price:
        history = data["history"]
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

    # ── Tabs ──────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🏠 Dashboard & AI",
        "📐 Valuation Bands",
        "🆚 Comparison",
        "📅 Seasonality",
        "📉 Technical Chart",
    ])

    with tab1:
        render_dashboard_tab(data, tech, fund, bands=bands, seasonality=seasonality)

    with tab2:
        render_valuation_tab(bands, ticker)

    with tab3:
        render_comparison_tab(ticker, period_yf)

    with tab4:
        render_seasonality_tab(seasonality, ticker)

    with tab5:
        render_technical_tab(tech, ticker, history)


if __name__ == "__main__":
    main()
