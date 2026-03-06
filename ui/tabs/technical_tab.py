"""Tab 5: Advanced Technical Chart."""

import streamlit as st

from ui.charts import render_price_chart


def render_technical_tab(tech: dict, ticker: str, history) -> None:
    st.subheader(f"📉 {ticker} — Technical Chart")
    render_price_chart(tech, ticker)

    # ── Smart Money Flow ────────────────────────────────────────────────────
    st.divider()
    st.subheader("🧐 Smart Money Flow")
    st.caption(
        "Combines **Money Flow Index (MFI)** and **On-Balance Volume (OBV)** to detect "
        "whether price moves are backed by institutional volume — a proxy for \"Market Maker\" activity."
    )

    mfi_val    = tech.get("mfi")
    obv_val    = tech.get("obv")
    mfi_signal = tech.get("mfi_signal", "N/A")
    obv_signal = tech.get("obv_signal", "N/A")
    sm_verdict = tech.get("smart_money", "N/A")

    col1, col2 = st.columns(2)
    mfi_display = f"{mfi_val:.1f}" if mfi_val is not None else "N/A"
    col1.metric("MFI (14)", mfi_display, mfi_signal, delta_color="off")

    if obv_val is not None:
        if abs(obv_val) >= 1e9:
            obv_display = f"{obv_val / 1e9:.2f}B"
        elif abs(obv_val) >= 1e6:
            obv_display = f"{obv_val / 1e6:.2f}M"
        else:
            obv_display = f"{obv_val:,.0f}"
    else:
        obv_display = "N/A"
    col2.metric("OBV", obv_display, obv_signal, delta_color="off")

    # Verdict box
    if "🟢" in sm_verdict:
        st.success(f"**Verdict:** {sm_verdict}", icon="🟢")
    elif "🔴" in sm_verdict:
        st.error(f"**Verdict:** {sm_verdict}", icon="🔴")
    elif "🟠" in sm_verdict:
        st.warning(f"**Verdict:** {sm_verdict}", icon="🟠")
    else:
        st.info(f"**Verdict:** {sm_verdict}", icon="🟡")

    st.divider()

    with st.expander("📋 Raw Historical Data"):
        fmt = history[["Open", "High", "Low", "Close", "Volume"]].copy()
        fmt.index = fmt.index.strftime("%Y-%m-%d")
        st.dataframe(fmt.sort_index(ascending=False), use_container_width=True)
