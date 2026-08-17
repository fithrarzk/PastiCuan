"""Tab 5: Advanced Technical Chart."""

import streamlit as st

from ui.charts import render_price_chart


def render_technical_tab(tech: dict, ticker: str, history) -> None:
    st.markdown(f"<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:16px;'>{ticker} — Technical Chart</h3>",
                unsafe_allow_html=True)
    score = tech.get("technical_score")
    confidence = tech.get("confidence")
    score_text = f"{score:.0f}/100" if score is not None else "N/A"
    confidence_text = f"{confidence:.0f}%" if confidence is not None else "N/A"
    c1, c2, c3 = st.columns(3)
    c1.metric("Technical Score", score_text, tech.get("recommendation", "N/A"), delta_color="off")
    c2.metric("Horizon", tech.get("horizon", "N/A"), tech.get("profile_label", "N/A"), delta_color="off")
    c3.metric("Confidence", confidence_text, tech.get("profile_reason", "N/A"), delta_color="off")

    render_price_chart(tech, ticker)

    st.divider()
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:8px;'>Adaptive Signal Breakdown</h3>",
                unsafe_allow_html=True)
    components = tech.get("score_components", {})
    if components:
        rows = [
            {"Component": name.title(), "Score": f"{value:.0f}/100"}
            for name, value in components.items()
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    entry_zone = tech.get("entry_zone")
    plan1, plan2, plan3, plan4 = st.columns(4)
    if entry_zone:
        plan1.metric("Entry Zone", f"{entry_zone[0]} - {entry_zone[1]}")
    plan2.metric("Stop Loss", f"Rp {tech['stop_loss']:,.0f}" if tech.get("stop_loss") is not None else "N/A")
    plan3.metric("Take Profit", f"Rp {tech['take_profit']:,.0f}" if tech.get("take_profit") is not None else "N/A")
    rr = tech.get("risk_reward")
    plan4.metric("Risk / Reward", f"{rr:.2f}R" if rr is not None else "N/A")

    # ── Observable volume evidence ──────────────────────────────────────────
    st.divider()
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:4px;'>Volume Evidence</h3>",
                unsafe_allow_html=True)
    st.caption(
        "Combines Money Flow Index (MFI) and On-Balance Volume (OBV) to assess "
        "whether price moves are confirmed by observed volume; it does not identify investor type."
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
