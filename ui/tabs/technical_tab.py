"""Tab 5: Advanced Technical Chart."""

import streamlit as st

from ui.charts import render_price_chart


def render_technical_tab(tech: dict, ticker: str, history) -> None:
    st.markdown(f"<h3 style='font-size:1rem;font-weight:600;color:#1E1E1E;margin-bottom:16px;'>{ticker} — Technical Chart</h3>",
                unsafe_allow_html=True)
    render_price_chart(tech, ticker)

    # ── Smart Money Flow ────────────────────────────────────────────────────
    st.divider()
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#1E1E1E;margin-bottom:4px;'>Smart Money Flow</h3>",
                unsafe_allow_html=True)
    st.caption(
        "Combines Money Flow Index (MFI) and On-Balance Volume (OBV) to assess "
        "whether price moves are supported by institutional volume."
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

    # Verdict box — strip emoji signals for display text
    verdict_text = sm_verdict
    if "🟢" in sm_verdict:
        st.success(f"Verdict: {verdict_text}")
    elif "🔴" in sm_verdict:
        st.error(f"Verdict: {verdict_text}")
    elif "🟠" in sm_verdict:
        st.warning(f"Verdict: {verdict_text}")
    else:
        st.info(f"Verdict: {verdict_text}")

    st.divider()

    with st.expander("Raw Historical Data"):
        fmt = history[["Open", "High", "Low", "Close", "Volume"]].copy()
        fmt.index = fmt.index.strftime("%Y-%m-%d")
        st.dataframe(fmt.sort_index(ascending=False), use_container_width=True)
