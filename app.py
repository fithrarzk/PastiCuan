import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# ──────────────────────────────────────────────
# Core data-fetching function
# ──────────────────────────────────────────────

def get_stock_data(ticker: str) -> dict:
    """
    Fetches basic info, financial ratios, and 1-year historical
    price data for an Indonesian stock.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol.  A '.JK' suffix is automatically appended
        if the symbol does not already end with it.

    Returns
    -------
    dict with keys:
        - 'ticker'    : resolved ticker string (with .JK)
        - 'basic'     : dict  – longName, sector
        - 'ratios'    : dict  – PE, PBV, ROE, Debt-to-Equity, Net Profit Margin
        - 'history'   : pd.DataFrame – OHLCV for last 1 year
        - 'error'     : str | None
    """
    ticker = ticker.strip().upper()
    if not ticker.endswith(".JK"):
        ticker = ticker + ".JK"

    result = {
        "ticker": ticker,
        "basic": {},
        "ratios": {},
        "history": pd.DataFrame(),
        "error": None,
    }

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # yfinance returns a minimal dict for invalid tickers
        if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None and info.get("previousClose") is None:
            # Try fetching history to confirm it's a real ticker
            hist_check = stock.history(period="5d")
            if hist_check.empty:
                result["error"] = f"Ticker **{ticker}** not found or has no trading data."
                return result

        # ── 1. Basic info ────────────────────────────────────────────
        result["basic"] = {
            "longName": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector") or "N/A",
        }

        # ── 2. Financial ratios ──────────────────────────────────────
        def fmt_pct(val):
            """Format a decimal ratio as percentage string, or 'N/A'."""
            return f"{val * 100:.2f}%" if val is not None else "N/A"

        def fmt_num(val, decimals=2):
            return f"{val:.{decimals}f}" if val is not None else "N/A"

        result["ratios"] = {
            "PE (Price-to-Earnings)":   fmt_num(info.get("trailingPE")),
            "PBV (Price-to-Book)":       fmt_num(info.get("priceToBook")),
            "ROE (Return on Equity)":    fmt_pct(info.get("returnOnEquity")),
            "Debt-to-Equity":            fmt_num(info.get("debtToEquity")),
            "Net Profit Margin":         fmt_pct(info.get("profitMargins")),
        }

        # ── 3. Historical price data (1 year) ────────────────────────
        history = stock.history(period="1y")
        if history.empty:
            result["error"] = f"No historical price data available for **{ticker}**."
        else:
            result["history"] = history

    except Exception as exc:
        result["error"] = f"An error occurred while fetching data: {exc}"

    return result


# ──────────────────────────────────────────────
# Streamlit UI helpers
# ──────────────────────────────────────────────

def render_ratios(ratios: dict):
    """Display financial ratios in a 3-column metric grid."""
    cols = st.columns(3)
    for i, (label, value) in enumerate(ratios.items()):
        cols[i % 3].metric(label=label, value=value)


def render_price_chart(history: pd.DataFrame, ticker: str):
    """Render an interactive candlestick + volume chart with Plotly."""
    fig = go.Figure()

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=history.index,
            open=history["Open"],
            high=history["High"],
            low=history["Low"],
            close=history["Close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        )
    )

    fig.update_layout(
        title=f"{ticker} – 1-Year Price History",
        xaxis_title="Date",
        yaxis_title="Price (IDR)",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=480,
        margin=dict(l=10, r=10, t=50, b=10),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Volume bar chart below
    st.markdown("**Volume**")
    vol_df = history[["Volume"]].copy()
    st.bar_chart(vol_df, height=160)


# ──────────────────────────────────────────────
# Main app
# ──────────────────────────────────────────────

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

    ticker = data["ticker"]
    basic = data["basic"]
    ratios = data["ratios"]
    history = data["history"]

    # ── Header ───────────────────────────────────────────────────────
    st.title(basic["longName"])
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.caption(f"🏷 Ticker: `{ticker}`")
        st.caption(f"🏢 Sector: **{basic['sector']}**")
    with col_h2:
        if not history.empty:
            latest_close = history["Close"].iloc[-1]
            prev_close = history["Close"].iloc[-2] if len(history) > 1 else latest_close
            pct_change = (latest_close - prev_close) / prev_close * 100
            st.metric(
                label="Last Close (IDR)",
                value=f"Rp {latest_close:,.0f}",
                delta=f"{pct_change:+.2f}%",
            )

    st.divider()

    # ── Financial ratios ─────────────────────────────────────────────
    st.subheader("📊 Financial Ratios")
    render_ratios(ratios)

    st.divider()

    # ── Price chart ──────────────────────────────────────────────────
    st.subheader("📉 Price History (1 Year)")
    render_price_chart(history, ticker)

    # ── Raw data expander ─────────────────────────────────────────────
    with st.expander("📋 Raw Historical Data"):
        fmt_hist = history[["Open", "High", "Low", "Close", "Volume"]].copy()
        fmt_hist.index = fmt_hist.index.strftime("%Y-%m-%d")
        st.dataframe(fmt_hist.sort_index(ascending=False), use_container_width=True)


if __name__ == "__main__":
    main()
