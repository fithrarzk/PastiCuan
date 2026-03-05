import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
        "info": {},
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

        result["info"] = info

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
# Technical Analysis
# ──────────────────────────────────────────────

def analyze_technical(df: pd.DataFrame) -> dict:
    """
    Calculates technical indicators from OHLCV price history.

    Indicators
    ----------
    - RSI (14-day Wilder's smoothing)
    - SMA 50 and SMA 200
    - Support & Resistance from last 3 months' highs/lows
    - ATR (14-day Average True Range)
    """
    df = df.copy()
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    # ── RSI (14) ─────────────────────────────────────────────────────
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    rsi_val = df["RSI"].iloc[-1] if not df["RSI"].isna().all() else None
    if rsi_val is None:
        rsi_signal = "N/A"
    elif rsi_val >= 70:
        rsi_signal = "🔴 Overbought (RSI ≥ 70)"
    elif rsi_val <= 30:
        rsi_signal = "🟢 Oversold (RSI ≤ 30)"
    else:
        rsi_signal = "🟡 Neutral (30 – 70)"

    # ── SMA 50 & SMA 200 ─────────────────────────────────────────────
    df["SMA50"]  = close.rolling(50).mean()
    df["SMA200"] = close.rolling(200).mean()

    sma50_val  = df["SMA50"].iloc[-1]  if not df["SMA50"].isna().all()  else None
    sma200_val = df["SMA200"].iloc[-1] if not df["SMA200"].isna().all() else None

    if sma50_val is not None and sma200_val is not None:
        if sma50_val > sma200_val:
            sma_signal = "🟢 Golden Cross — SMA50 above SMA200 (Bullish)"
        else:
            sma_signal = "🔴 Death Cross — SMA50 below SMA200 (Bearish)"
    else:
        sma_signal = "⚪ Insufficient data for SMA200 signal"

    # ── Support & Resistance (last 3 months) ─────────────────────────
    cutoff    = df.index[-1] - pd.DateOffset(months=3)
    df_3m     = df.loc[df.index >= cutoff]

    support_val    = float(df_3m["Low"].min())  if not df_3m.empty else None
    resistance_val = float(df_3m["High"].max()) if not df_3m.empty else None

    current_price = float(close.iloc[-1])
    if support_val and resistance_val:
        rng = resistance_val - support_val
        pos = (current_price - support_val) / rng * 100 if rng > 0 else 50
        if pos <= 25:
            sr_signal = "🟢 Near Support — potential bounce zone"
        elif pos >= 75:
            sr_signal = "🔴 Near Resistance — potential reversal zone"
        else:
            sr_signal = "🟡 Mid-range between Support and Resistance"
    else:
        sr_signal = "N/A"

    # ── ATR (14) ─────────────────────────────────────────────────────
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low,
         (high - prev_close).abs(),
         (low  - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()

    atr_val     = df["ATR"].iloc[-1] if not df["ATR"].isna().all() else None
    atr_pct_val = (atr_val / current_price * 100) if atr_val else None

    if atr_pct_val is None:
        atr_signal = "N/A"
    elif atr_pct_val >= 3.0:
        atr_signal = "🔴 High Volatility"
    elif atr_pct_val >= 1.5:
        atr_signal = "🟡 Moderate Volatility"
    else:
        atr_signal = "🟢 Low Volatility"

    return {
        "rsi": rsi_val,         "rsi_signal": rsi_signal,
        "sma50": sma50_val,     "sma200": sma200_val,   "sma_signal": sma_signal,
        "support": support_val, "resistance": resistance_val, "sr_signal": sr_signal,
        "atr": atr_val,         "atr_pct": atr_pct_val, "atr_signal": atr_signal,
        "df": df,
    }


# ──────────────────────────────────────────────
# Fundamental Analysis
# ──────────────────────────────────────────────

# Sector-specific PE and PBV benchmarks calibrated for the IDX / Indonesian market.
# Format: { sector_keyword: { "pe": (low_max, high_min), "pbv": (low_max, high_min) } }
_SECTOR_BENCHMARKS = {
    "financial services": {"pe": (8,  15),  "pbv": (1.0, 2.5)},
    "bank":               {"pe": (8,  15),  "pbv": (1.0, 2.5)},
    "technology":         {"pe": (20, 40),  "pbv": (3.0, 8.0)},
    "consumer defensive": {"pe": (12, 25),  "pbv": (2.0, 5.0)},
    "consumer staples":   {"pe": (12, 25),  "pbv": (2.0, 5.0)},
    "consumer cyclical":  {"pe": (10, 20),  "pbv": (1.5, 4.0)},
    "healthcare":         {"pe": (15, 30),  "pbv": (2.0, 5.0)},
    "energy":             {"pe": (8,  15),  "pbv": (1.0, 2.5)},
    "basic materials":    {"pe": (8,  15),  "pbv": (1.0, 2.5)},
    "industrials":        {"pe": (10, 20),  "pbv": (1.5, 3.0)},
    "utilities":          {"pe": (10, 18),  "pbv": (1.0, 2.0)},
    "real estate":        {"pe": (10, 20),  "pbv": (0.8, 1.5)},
    "communication":      {"pe": (12, 25),  "pbv": (2.0, 4.0)},
    "default":            {"pe": (10, 20),  "pbv": (1.5, 3.0)},
}


def _get_sector_benchmark(sector: str) -> tuple:
    """Return (benchmark_dict, matched_label) for a given sector string."""
    sector_lower = sector.lower()
    for key, bench in _SECTOR_BENCHMARKS.items():
        if key != "default" and key in sector_lower:
            return bench, key.title()
    return _SECTOR_BENCHMARKS["default"], "General / Default"


def _classify(value, low_max: float, high_min: float) -> str:
    """Classify a ratio value as Low / Fair / High relative to sector thresholds."""
    if value is None:
        return "N/A"
    if value < low_max:
        return "🟢 Low"
    if value > high_min:
        return "🔴 High"
    return "🟡 Fair"


def analyze_fundamental(info: dict, sector: str) -> dict:
    """
    Evaluates PE and PBV against sector-specific IDX benchmarks and
    returns a valuation verdict.

    Parameters
    ----------
    info   : raw yfinance .info dict
    sector : sector string from yfinance (e.g. 'Financial Services')
    """
    pe_val  = info.get("trailingPE")
    pbv_val = info.get("priceToBook")

    bench, matched_sector = _get_sector_benchmark(sector)
    pe_low,  pe_high  = bench["pe"]
    pbv_low, pbv_high = bench["pbv"]

    pe_label  = _classify(pe_val,  pe_low,  pe_high)
    pbv_label = _classify(pbv_val, pbv_low, pbv_high)

    # Overall verdict
    labels = {pe_label, pbv_label} - {"N/A"}
    if not labels:
        overall = "⚪ Insufficient data for valuation verdict"
    elif labels == {"🟢 Low"}:
        overall = "🟢 Potentially Undervalued"
    elif labels == {"🔴 High"}:
        overall = "🔴 Potentially Overvalued"
    elif labels <= {"🟡 Fair", "🟢 Low"}:
        overall = "🟡 Fairly Valued"
    elif "🔴 High" in labels and "🟢 Low" in labels:
        overall = "🟡 Mixed Signals — one ratio cheap, one expensive"
    elif "🔴 High" in labels:
        overall = "🔴 Leaning Overvalued"
    else:
        overall = "🟢 Leaning Undervalued"

    return {
        "sector_matched": matched_sector,
        "pe_value":  pe_val,   "pe_label":  pe_label,
        "pe_range":  f"Low < {pe_low}  |  Fair {pe_low}–{pe_high}  |  High > {pe_high}",
        "pbv_value": pbv_val,  "pbv_label": pbv_label,
        "pbv_range": f"Low < {pbv_low}  |  Fair {pbv_low}–{pbv_high}  |  High > {pbv_high}",
        "overall":   overall,
    }


# ──────────────────────────────────────────────
# Streamlit UI helpers
# ──────────────────────────────────────────────

def render_ratios(ratios: dict):
    """Display financial ratios in a 3-column metric grid."""
    cols = st.columns(3)
    for i, (label, value) in enumerate(ratios.items()):
        cols[i % 3].metric(label=label, value=value)


def render_price_chart(tech: dict, ticker: str):
    """Candlestick + SMA 50/200 + Support/Resistance lines + RSI sub-plot + Volume."""
    df = tech["df"]

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.72, 0.28],
        vertical_spacing=0.03,
        subplot_titles=(f"{ticker} – 1-Year Price + SMAs", "RSI (14)"),
    )

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"],
            low=df["Low"],   close=df["Close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ), row=1, col=1,
    )

    # SMA 50
    fig.add_trace(
        go.Scatter(x=df.index, y=df["SMA50"], name="SMA 50",
                   line=dict(color="#f0a500", width=1.5)), row=1, col=1,
    )

    # SMA 200
    fig.add_trace(
        go.Scatter(x=df.index, y=df["SMA200"], name="SMA 200",
                   line=dict(color="#7c83fd", width=1.5)), row=1, col=1,
    )

    # Support line
    if tech["support"]:
        fig.add_hline(
            y=tech["support"], line_dash="dot", line_color="#4caf50", line_width=1,
            annotation_text=f"Support  Rp {tech['support']:,.0f}",
            annotation_position="bottom right", row=1, col=1,
        )

    # Resistance line
    if tech["resistance"]:
        fig.add_hline(
            y=tech["resistance"], line_dash="dot", line_color="#ef5350", line_width=1,
            annotation_text=f"Resistance  Rp {tech['resistance']:,.0f}",
            annotation_position="top right", row=1, col=1,
        )

    # RSI
    fig.add_trace(
        go.Scatter(x=df.index, y=df["RSI"], name="RSI (14)",
                   line=dict(color="#ba68c8", width=1.5)), row=2, col=1,
    )
    fig.add_hline(y=70, line_dash="dash", line_color="#ef5350", line_width=1, row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#26a69a", line_width=1, row=2, col=1)

    fig.update_yaxes(title_text="Price (IDR)", row=1, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=600,
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Volume**")
    st.bar_chart(df[["Volume"]], height=140)


def render_technical_summary(tech: dict):
    """4-column metric grid + two signal info boxes for technical indicators."""
    rsi_val    = f"{tech['rsi']:.1f}"        if tech["rsi"]    else "N/A"
    sma50_val  = f"Rp {tech['sma50']:,.0f}"  if tech["sma50"]  else "N/A"
    sma200_val = f"Rp {tech['sma200']:,.0f}" if tech["sma200"] else "N/A"
    atr_val    = (
        f"Rp {tech['atr']:,.0f} ({tech['atr_pct']:.1f}%)"
        if tech["atr"] else "N/A"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("RSI (14)",      rsi_val,    tech["rsi_signal"],  delta_color="off")
    c2.metric("SMA 50",        sma50_val)
    c3.metric("SMA 200",       sma200_val)
    c4.metric("ATR (14 days)", atr_val,    tech["atr_signal"],  delta_color="off")

    col_a, col_b = st.columns(2)
    col_a.info(f"**Trend Signal:** {tech['sma_signal']}")
    with col_b:
        if tech["support"] and tech["resistance"]:
            sr_text = (
                f"Support: **Rp {tech['support']:,.0f}** &nbsp;|&nbsp; "
                f"Resistance: **Rp {tech['resistance']:,.0f}**\n\n"
                f"{tech['sr_signal']}"
            )
        else:
            sr_text = "N/A"
        st.info(f"**Price Position:** {sr_text}")


def render_fundamental_analysis(fund: dict):
    """PE / PBV valuation metrics with sector benchmark context."""
    st.caption(f"Sector benchmark applied: **{fund['sector_matched']}**")

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "PE Ratio",
        f"{fund['pe_value']:.2f}" if fund["pe_value"] else "N/A",
        fund["pe_label"], delta_color="off", help=fund["pe_range"],
    )
    c2.metric(
        "PBV Ratio",
        f"{fund['pbv_value']:.2f}" if fund["pbv_value"] else "N/A",
        fund["pbv_label"], delta_color="off", help=fund["pbv_range"],
    )
    c3.metric("Overall Verdict", "", fund["overall"], delta_color="off")

    with st.expander("📐 Sector Benchmark Ranges"):
        st.markdown(
            f"| Ratio | Range |\n|---|---|\n"
            f"| **PE** | {fund['pe_range']} |\n"
            f"| **PBV** | {fund['pbv_range']} |"
        )


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
    info = data["info"]
    sector = basic["sector"]

    # Run analyses
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

    # ── Fundamental Valuation ──────────────────────────────────────────
    st.subheader("🏦 Fundamental Valuation")
    render_fundamental_analysis(fund)

    st.divider()

    # ── Technical Analysis summary ────────────────────────────────────
    st.subheader("📡 Technical Indicators")
    render_technical_summary(tech)

    st.divider()

    # ── Price chart (candlestick + SMA + RSI + Support/Resistance) ───
    st.subheader("📉 Price History (1 Year)")
    render_price_chart(tech, ticker)

    # ── Raw data expander ─────────────────────────────────────────────
    with st.expander("📋 Raw Historical Data"):
        fmt_hist = history[["Open", "High", "Low", "Close", "Volume"]].copy()
        fmt_hist.index = fmt_hist.index.strftime("%Y-%m-%d")
        st.dataframe(fmt_hist.sort_index(ascending=False), use_container_width=True)


if __name__ == "__main__":
    main()
