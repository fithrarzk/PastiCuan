"""Tab 3: Competitor side-by-side comparison."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf

from data.extended import get_comparison_data

_COLORS = ["#29b6f6", "#ef5350", "#26a69a", "#f0a500", "#ba68c8", "#ff8f00", "#7c83fd"]


def render_comparison_tab(main_ticker: str, period_yf: str) -> None:
    st.markdown(
        "Enter comma-separated competitor tickers to compare normalised price performance "
        "and key metrics side by side."
    )
    comp_input = st.text_input(
        "Competitor Tickers",
        placeholder="e.g. BBRI, BMRI, BNIS",
        help="IDX tickers separated by commas. '.JK' is appended automatically.",
        key="comparison_input",
    )
    if not comp_input.strip():
        st.info("Enter competitor tickers above to begin comparison.", icon="👆")
        return

    tickers_raw = [t.strip() for t in comp_input.split(",") if t.strip()]
    all_tickers  = [main_ticker] + tickers_raw

    with st.spinner("Fetching comparison data …"):
        hist_map = get_comparison_data(all_tickers, period=period_yf)

    if not hist_map:
        st.error("No data retrieved. Please check the tickers and try again.")
        return

    # ── Normalised performance chart ──────────────────────────────────────────
    st.subheader("📈 Normalised Price Performance (Base = 100)")
    fig = go.Figure()
    for i, (tkr, hist) in enumerate(hist_map.items()):
        close = hist["Close"]
        norm  = close / close.iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=close.index, y=norm, name=tkr,
            line=dict(color=_COLORS[i % len(_COLORS)], width=2),
            hovertemplate=f"{tkr}: %{{y:.1f}}<extra></extra>",
        ))
    fig.update_layout(
        template="plotly_dark", height=450,
        yaxis_title="Normalised Price (%)",
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Metrics table ─────────────────────────────────────────────────────────
    st.subheader("📊 Side-by-Side Performance Metrics")
    rows = []
    for tkr_raw in all_tickers:
        tkr_norm = tkr_raw.strip().upper()
        if not tkr_norm.endswith(".JK"):
            tkr_norm += ".JK"
        try:
            info = yf.Ticker(tkr_norm).info
            hist = hist_map.get(tkr_norm, pd.DataFrame())
            total_ret = (
                (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                if not hist.empty and len(hist) > 1
                else None
            )
            rows.append({
                "Ticker":           tkr_norm,
                "Company":          info.get("shortName") or tkr_norm,
                "Last Price (IDR)": f"Rp {info['previousClose']:,.0f}" if info.get("previousClose") else "N/A",
                "PE Ratio":         f"{info['trailingPE']:.2f}x"       if info.get("trailingPE")    else "N/A",
                "PBV Ratio":        f"{info['priceToBook']:.2f}x"      if info.get("priceToBook")   else "N/A",
                "ROE":              f"{info['returnOnEquity']*100:.2f}%" if info.get("returnOnEquity") else "N/A",
                f"Return ({period_yf})": f"{total_ret:+.2f}%" if total_ret is not None else "N/A",
            })
        except Exception:
            rows.append({"Ticker": tkr_norm, "Company": "Error fetching data"})

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
