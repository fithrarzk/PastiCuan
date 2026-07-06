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

    # ── Global CSS ────────────────────────────────────────────────────
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"],
    .stMarkdown, button, input, select, textarea, label {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont,
                     'SF Pro Display', sans-serif !important;
        -webkit-font-smoothing: antialiased;
    }
    .stApp, .stApp > div, [data-testid="stAppViewContainer"] {
        background-color: #000000 !important;
    }
    [data-testid="stHeader"] { background-color: #000000 !important; }
    h1, h2, h3, h4, h5, h6 { color: #F5F5F7 !important; font-weight: 600 !important; }
    p, li { color: #F5F5F7 !important; line-height: 1.6; }

    [data-testid="stSidebar"], [data-testid="stSidebar"] > div {
        background-color: #111113 !important;
        border-right: 1px solid #38383A !important;
    }

    [data-testid="metric-container"] {
        background: #1C1C1E !important;
        border: 1px solid #38383A !important;
        border-radius: 12px !important;
        padding: 16px 20px !important;
    }
    [data-testid="stMetricLabel"] > div {
        color: #8E8E93 !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
    }
    [data-testid="stMetricValue"] > div {
        color: #F5F5F7 !important;
        font-size: 1.35rem !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricDelta"] > div {
        font-size: 0.8rem !important;
        font-weight: 500 !important;
    }
    [data-testid="stMetricDelta"][data-direction="positive"] > div { color: #30D158 !important; }
    [data-testid="stMetricDelta"][data-direction="negative"] > div { color: #FF453A !important; }
    [data-testid="stMetricDelta"][data-direction="off"] > div { color: #8E8E93 !important; }

    [data-testid="baseButton-primary"] {
        background-color: #F5F5F7 !important;
        border-radius: 12px !important;
        border: none !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em !important;
        color: #000000 !important;
    }
    [data-testid="baseButton-primary"]:hover { background-color: #E5E5EA !important; }
    [data-testid="baseButton-secondary"] {
        background-color: #1C1C1E !important;
        border: 1px solid #38383A !important;
        border-radius: 12px !important;
        color: #F5F5F7 !important;
    }

    [data-testid="stTextInput"] input {
        border-radius: 12px !important;
        border-color: #38383A !important;
        background: #1C1C1E !important;
        color: #F5F5F7 !important;
    }
    [data-testid="stTextInput"] input:focus {
        border-color: #F5F5F7 !important;
        box-shadow: none !important;
    }
    [data-testid="stSelectbox"] > div > div {
        border-radius: 12px !important;
        border-color: #38383A !important;
        background: #1C1C1E !important;
        color: #F5F5F7 !important;
    }

    [data-testid="stTabs"] [role="tablist"] {
        border-bottom: 1px solid #38383A !important;
        gap: 0 !important;
        background: transparent !important;
    }
    [data-testid="stTabs"] [role="tab"] {
        font-size: 0.83rem !important;
        font-weight: 500 !important;
        color: #8E8E93 !important;
        border: none !important;
        border-bottom: 2px solid transparent !important;
        border-radius: 0 !important;
        padding: 10px 20px !important;
        background: transparent !important;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        color: #F5F5F7 !important;
        border-bottom: 2px solid #F5F5F7 !important;
        font-weight: 600 !important;
    }
    [data-testid="stTabs"] [role="tab"]:hover {
        color: #F5F5F7 !important;
        background: transparent !important;
    }

    [data-testid="stExpander"] {
        border: 1px solid #38383A !important;
        border-radius: 12px !important;
        background: #1C1C1E !important;
    }
    [data-testid="stExpander"] summary {
        border-radius: 12px !important;
        font-weight: 500 !important;
        color: #F5F5F7 !important;
    }

    [data-testid="stDataFrame"] {
        border: 1px solid #38383A !important;
        border-radius: 12px !important;
        overflow: hidden !important;
    }
    [data-testid="stAlert"] { border-radius: 12px !important; }
    hr { border-color: #38383A !important; margin: 1.5rem 0 !important; }
    .stCaption, [data-testid="stCaptionContainer"] p, small {
        color: #8E8E93 !important;
        font-size: 0.8rem !important;
    }
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: #1C1C1E; }
    ::-webkit-scrollbar-thumb { background: #48484A; border-radius: 3px; }
    </style>
    """, unsafe_allow_html=True)

    # ── Sidebar ──────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### PastiCuan")
        st.caption("IDX Equity Research · Indonesia")
        st.divider()

        ticker_input = st.text_input(
            "Ticker Symbol",
            value="BBCA",
            placeholder="e.g. BBCA",
            help="Enter the IDX stock ticker. The .JK suffix is added automatically.",
        )

        period_label = st.selectbox(
            "Analysis Period",
            options=list(PERIOD_MAP.keys()),
            index=0,
        )
        period_yf = PERIOD_MAP[period_label]

        analyze_btn = st.button("Analyze", use_container_width=True, type="primary")

        st.divider()
        st.caption("Data · Yahoo Finance")
        st.caption("Prices in Indonesian Rupiah (IDR)")

    # ── Welcome screen ────────────────────────────────────────────────
    if not ticker_input:
        st.markdown("""
        <div style="text-align:center;padding:80px 40px;">
            <p style="font-size:0.72rem;font-weight:600;color:#8E8E93;text-transform:uppercase;
                      letter-spacing:0.12em;margin-bottom:16px;">IDX Equity Research</p>
            <h1 style="font-size:2.6rem;font-weight:700;color:#F5F5F7;margin-bottom:12px;">PastiCuan</h1>
            <p style="font-size:1rem;color:#8E8E93;max-width:420px;margin:0 auto;">
                Enter a ticker symbol in the sidebar and click <strong>Analyze</strong> to begin.
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # ── Session-state cache key ───────────────────────────────────────
    request_key = (ticker_input.strip().upper(), period_yf)
    if analyze_btn or st.session_state.get("last_request") != request_key:
        # Clear all cached data when ticker/period change
        if st.session_state.get("last_request") != request_key:
            st.session_state["ai_result"] = None
        st.session_state["last_request"] = request_key

        with st.spinner(f"Loading {ticker_input.upper()} — {period_label}…"):
            data = get_extended_data(ticker_input, period=period_yf)

        if data["error"]:
            st.error(data["error"])
            st.stop()

        ticker  = data["ticker"]
        history = data["history"]
        info    = data["info"]
        sector  = data["basic"].get("sector", "N/A")

        tech  = analyze_technical(history, sector=sector, info=info)
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
        st.markdown("""
        <div style="text-align:center;padding:80px 40px;">
            <p style="font-size:0.72rem;font-weight:600;color:#8E8E93;text-transform:uppercase;
                      letter-spacing:0.12em;margin-bottom:16px;">IDX Equity Research</p>
            <h1 style="font-size:2.6rem;font-weight:700;color:#F5F5F7;margin-bottom:12px;">PastiCuan</h1>
            <p style="font-size:1rem;color:#8E8E93;max-width:420px;margin:0 auto;">
                Click <strong>Analyze</strong> in the sidebar to load data.
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    data        = st.session_state["fetched_data"]
    tech        = st.session_state["tech"]
    fund        = st.session_state["fund"]
    bands       = st.session_state["bands"]
    seasonality = st.session_state["seasonality"]
    ticker      = data["ticker"]
    basic       = data["basic"]

    # ── Executive Summary Header ──────────────────────────────────────
    history = data["history"]
    latest_close = history["Close"].iloc[-1] if not history.empty else 0
    prev_close   = history["Close"].iloc[-2] if len(history) > 1 else latest_close
    pct_change   = (latest_close - prev_close) / prev_close * 100 if prev_close else 0
    chg_color    = "#30D158" if pct_change >= 0 else "#FF453A"
    chg_sign     = "+" if pct_change >= 0 else ""
    st.markdown(f"""
    <div style="padding:28px 0 20px 0;border-bottom:1px solid #38383A;margin-bottom:24px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:12px;">
            <div>
                <div style="font-size:0.72rem;font-weight:600;color:#8E8E93;
                            text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;">
                    {ticker}&nbsp;&nbsp;&middot;&nbsp;&nbsp;{basic.get('sector','N/A')}&nbsp;&nbsp;&middot;&nbsp;&nbsp;{period_label}
                </div>
                <h1 style="font-size:1.9rem;font-weight:700;color:#F5F5F7;margin:0;line-height:1.2;">
                    {basic.get('longName','')}
                </h1>
            </div>
            <div style="text-align:right;">
                <div style="font-size:1.9rem;font-weight:700;color:#F5F5F7;line-height:1.2;">
                    Rp {latest_close:,.0f}
                </div>
                <div style="font-size:0.95rem;font-weight:500;color:{chg_color};margin-top:4px;">
                    {chg_sign}{pct_change:.2f}%
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Dashboard",
        "Valuation Bands",
        "Comparison",
        "Seasonality",
        "Technical",
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
