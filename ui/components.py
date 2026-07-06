import streamlit as st
import pandas as pd


def render_ratios_table(ratios: dict, fund: dict) -> None:
    """Display fundamental ratios in a clean table with valuation verdict."""
    rows = []
    for label, value in ratios.items():
        rows.append({"Metric": label, "Value": value})

    pe_display  = f"{fund['pe_value']:.2f}" if fund["pe_value"] else "N/A"
    pbv_display = f"{fund['pbv_value']:.2f}" if fund["pbv_value"] else "N/A"

    rows.append({"Metric": "—", "Value": "—"})
    rows.append({"Metric": "PE Valuation", "Value": f"{pe_display}  {fund['pe_label']}"})
    rows.append({"Metric": "PBV Valuation", "Value": f"{pbv_display}  {fund['pbv_label']}"})
    rows.append({"Metric": "Overall Verdict", "Value": fund["overall"]})

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Metric": st.column_config.TextColumn("Metric", width="medium"),
            "Value":  st.column_config.TextColumn("Value",  width="medium"),
        },
    )

    with st.expander("Sector Benchmarks"):
        st.markdown(
            f"| Ratio | Range |\n|---|---|\n"
            f"| **PE** | {fund['pe_range']} |\n"
            f"| **PBV** | {fund['pbv_range']} |"
        )


def render_technical_panel(tech: dict) -> None:
    """Render technical indicators in a compact panel for a column layout."""
    score = tech.get("technical_score")
    confidence = tech.get("confidence")
    score_display = f"{score:.0f}/100" if score is not None else "N/A"
    confidence_display = f"{confidence:.0f}% confidence" if confidence is not None else "N/A"
    st.metric(
        "Adaptive Technical Score",
        score_display,
        f"{tech.get('recommendation', 'N/A')} · {confidence_display}",
        delta_color="off",
    )
    st.caption(f"{tech.get('profile_label', 'General')} · {tech.get('horizon', 'N/A')}")

    c1, c2 = st.columns(2)
    rsi_period = tech.get("rsi_period", 14)
    rsi_val = f"{tech['rsi']:.1f}" if tech.get("rsi") is not None else "N/A"
    atr_val = (
        f"Rp {tech['atr']:,.0f} ({tech['atr_pct']:.1f}%)"
        if tech.get("atr") is not None and tech.get("atr_pct") is not None else "N/A"
    )
    c1.metric(f"RSI ({rsi_period})", rsi_val, tech.get("rsi_signal", "N/A"), delta_color="off")
    c2.metric("ATR (14d)", atr_val, tech["atr_signal"], delta_color="off")

    c3, c4 = st.columns(2)
    fast_period = tech.get("fast_ma_period", 50)
    slow_period = tech.get("slow_ma_period", 200)
    fast_ma_val = f"Rp {tech['fast_ma']:,.0f}" if tech.get("fast_ma") is not None else "N/A"
    slow_ma_val = f"Rp {tech['slow_ma']:,.0f}" if tech.get("slow_ma") is not None else "N/A"
    c3.metric(f"MA {fast_period}", fast_ma_val)
    c4.metric(f"MA {slow_period}", slow_ma_val)

    # MACD
    if tech.get("macd") is not None:
        macd_display      = f"{tech['macd']:.2f}"
        macd_hist_display = f"{tech['macd_hist']:+.2f}" if tech.get("macd_hist") is not None else "N/A"
        c5, c6 = st.columns(2)
        macd_params = tech.get("macd_params", (12, 26, 9))
        c5.metric(f"MACD {macd_params}", macd_display, tech.get("macd_signal", "N/A"), delta_color="off")
        c6.metric("Histogram", macd_hist_display)

    # Trend signal
    st.markdown(
        f"<div style='font-size:0.82rem;color:#8E8E93;padding:8px 0;line-height:1.5;'>"
        f"<strong style='color:#F5F5F7;'>Trend</strong>&nbsp; {tech['sma_signal']}</div>",
        unsafe_allow_html=True,
    )

    # Support / Resistance
    if tech.get("support") is not None and tech.get("resistance") is not None:
        sc1, sc2 = st.columns(2)
        sc1.metric("Support",    f"Rp {tech['support']:,.0f}")
        sc2.metric("Resistance", f"Rp {tech['resistance']:,.0f}")
        st.markdown(
            f"<div style='font-size:0.82rem;color:#8E8E93;padding:8px 0;line-height:1.5;'>"
            f"<strong style='color:#F5F5F7;'>Position</strong>&nbsp; {tech['sr_signal']}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Support / Resistance data unavailable.")

    entry_zone = tech.get("entry_zone")
    if entry_zone:
        plan1, plan2, plan3 = st.columns(3)
        plan1.metric("Entry Zone", f"{entry_zone[0]} - {entry_zone[1]}")
        plan2.metric("Stop Loss", f"Rp {tech['stop_loss']:,.0f}" if tech.get("stop_loss") is not None else "N/A")
        rr = tech.get("risk_reward")
        rr_display = f"{rr:.2f}R" if rr is not None else "N/A"
        plan3.metric("Take Profit", f"Rp {tech['take_profit']:,.0f}" if tech.get("take_profit") is not None else "N/A", rr_display)


def render_fundamental_analysis(fund: dict) -> None:
    """Renders PE and PBV valuation metrics with sector benchmark context."""
    st.caption(f"Sector benchmark: {fund['sector_matched']}")

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

    with st.expander("Sector Benchmarks"):
        st.markdown(
            f"| Ratio | Range |\n|---|---|\n"
            f"| **PE** | {fund['pe_range']} |\n"
            f"| **PBV** | {fund['pbv_range']} |"
        )
