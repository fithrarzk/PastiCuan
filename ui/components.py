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
    c1, c2 = st.columns(2)
    rsi_val = f"{tech['rsi']:.1f}" if tech["rsi"] else "N/A"
    atr_val = (
        f"Rp {tech['atr']:,.0f} ({tech['atr_pct']:.1f}%)"
        if tech["atr"] else "N/A"
    )
    c1.metric("RSI (14)", rsi_val, tech["rsi_signal"], delta_color="off")
    c2.metric("ATR (14d)", atr_val, tech["atr_signal"], delta_color="off")

    c3, c4 = st.columns(2)
    sma50_val  = f"Rp {tech['sma50']:,.0f}"  if tech["sma50"]  else "N/A"
    sma200_val = f"Rp {tech['sma200']:,.0f}" if tech["sma200"] else "N/A"
    c3.metric("SMA 50",  sma50_val)
    c4.metric("SMA 200", sma200_val)

    # MACD
    if tech.get("macd") is not None:
        macd_display      = f"{tech['macd']:.2f}"
        macd_hist_display = f"{tech['macd_hist']:+.2f}" if tech.get("macd_hist") is not None else "N/A"
        c5, c6 = st.columns(2)
        c5.metric("MACD", macd_display, tech.get("macd_signal", "N/A"), delta_color="off")
        c6.metric("Histogram", macd_hist_display)

    # Trend signal
    st.markdown(
        f"<div style='font-size:0.82rem;color:#6E6E73;padding:8px 0;line-height:1.5;'>"
        f"<strong style='color:#1E1E1E;'>Trend</strong>&nbsp; {tech['sma_signal']}</div>",
        unsafe_allow_html=True,
    )

    # Support / Resistance
    if tech["support"] and tech["resistance"]:
        sc1, sc2 = st.columns(2)
        sc1.metric("Support",    f"Rp {tech['support']:,.0f}")
        sc2.metric("Resistance", f"Rp {tech['resistance']:,.0f}")
        st.markdown(
            f"<div style='font-size:0.82rem;color:#6E6E73;padding:8px 0;line-height:1.5;'>"
            f"<strong style='color:#1E1E1E;'>Position</strong>&nbsp; {tech['sr_signal']}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Support / Resistance data unavailable.")


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
