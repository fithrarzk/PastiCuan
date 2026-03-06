"""Tab 1: Dashboard & AI Analyst."""

import os

import streamlit as st

from analysis.ai import generate_ai_analysis
from ui.components import render_ratios_table, render_technical_panel


def render_dashboard_tab(
    data: dict,
    tech: dict,
    fund: dict,
    bands: dict | None = None,
    seasonality: dict | None = None,
) -> None:
    basic   = data["basic"]
    info    = data["info"]
    history = data["history"]
    ticker  = data["ticker"]
    ratios  = data["ratios"]

    # ── Key Statistics ────────────────────────────────────────────────────────
    st.subheader("📊 Key Statistics")
    c1, c2, c3, c4, c5 = st.columns(5)
    if not history.empty:
        latest = history["Close"].iloc[-1]
        prev   = history["Close"].iloc[-2] if len(history) > 1 else latest
        pct    = (latest - prev) / prev * 100
        c1.metric("Last Close (IDR)", f"Rp {latest:,.0f}", f"{pct:+.2f}%")
    high52 = basic.get("fiftyTwoWeekHigh")
    low52  = basic.get("fiftyTwoWeekLow")
    mc     = basic.get("marketCap")
    dy     = info.get("dividendYield")
    if high52:
        c2.metric("52W High", f"Rp {high52:,.0f}")
    if low52:
        c3.metric("52W Low",  f"Rp {low52:,.0f}")
    if mc:
        if mc >= 1e12:
            c4.metric("Market Cap", f"Rp {mc / 1e12:.1f}T")
        elif mc >= 1e9:
            c4.metric("Market Cap", f"Rp {mc / 1e9:.1f}B")
        else:
            c4.metric("Market Cap", f"Rp {mc:,.0f}")
    if dy:
        c5.metric("Dividend Yield", f"{dy * 100:.2f}%")

    st.divider()

    # ── Fundamental & Technical side-by-side ──────────────────────────────────
    col_f, col_t = st.columns(2, gap="large")
    with col_f:
        st.subheader("🏦 Fundamental Ratios")
        render_ratios_table(ratios, fund)
    with col_t:
        st.subheader("📡 Technical Indicators")
        render_technical_panel(tech)

    st.divider()

    # ── AI Analysis ───────────────────────────────────────────────────────────
    st.subheader("🤖 AI Analysis Report")
    if not os.environ.get("GEMINI_API_KEY"):
        st.info(
            "Set `GEMINI_API_KEY` in your `.env` file to enable AI analysis.",
            icon="🔑",
        )
        return

    if st.session_state.get("ai_result"):
        st.success(
            "Analysis loaded from cache — click **Regenerate** to refresh.",
            icon="💾",
        )
        st.markdown(st.session_state["ai_result"])

    btn_label = (
        "🔄 Regenerate Deep AI Analysis"
        if st.session_state.get("ai_result")
        else "🧠 Generate Deep AI Analysis"
    )
    if st.button(btn_label, type="primary", key="ai_btn"):
        with st.spinner("Contacting Gemini 2.0 Flash — this may take a moment …"):
            result = generate_ai_analysis(
                fund, tech, ticker,
                bands=bands,
                seasonality=seasonality,
                comparison_summary=st.session_state.get("comparison_summary"),
            )
        st.session_state["ai_result"] = result
        st.rerun()
