"""Tab 1: Dashboard & AI Analyst."""

import streamlit as st

from analysis.ai import generate_ai_analysis, get_ai_provider_status
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
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:16px;'>Key Statistics</h3>",
                unsafe_allow_html=True)
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
        c2.metric("52-Week High", f"Rp {high52:,.0f}")
    if low52:
        c3.metric("52-Week Low",  f"Rp {low52:,.0f}")
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
        st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:16px;'>Fundamental Ratios</h3>",
                    unsafe_allow_html=True)
        render_ratios_table(ratios, fund)
    with col_t:
        st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:16px;'>Technical Indicators</h3>",
                    unsafe_allow_html=True)
        render_technical_panel(tech)

    st.divider()

    # ── AI Analysis ───────────────────────────────────────────────────────────
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:4px;'>AI Research Report</h3>",
                unsafe_allow_html=True)
    provider_status = get_ai_provider_status()
    if provider_status["ready"]:
        st.caption(f"{provider_status['label']} — {provider_status['message']}")
    else:
        st.warning(
            f"{provider_status['label']} — {provider_status['message']} "
            "Click Generate to use the deterministic local fallback."
        )

    if st.session_state.get("ai_result"):
        st.caption("Analysis cached — click Regenerate to refresh.")
        st.markdown(
            f"<div style='line-height:1.7;font-size:0.875rem;color:#F5F5F7;'>"
            f"{st.session_state['ai_result']}</div>",
            unsafe_allow_html=True,
        )

    btn_label = (
        "Regenerate Analysis"
        if st.session_state.get("ai_result")
        else "Generate AI Analysis"
    )
    if st.button(btn_label, type="primary", key="ai_btn"):
        with st.spinner("Generating analysis…"):
            result = generate_ai_analysis(
                fund, tech, ticker,
                bands=bands,
                seasonality=seasonality,
                comparison_summary=st.session_state.get("comparison_summary"),
            )
        st.session_state["ai_result"] = result
        st.rerun()
