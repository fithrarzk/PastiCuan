import streamlit as st


def render_ratios(ratios: dict) -> None:
    """Display fundamental financial ratios in a 3-column metric grid."""
    cols = st.columns(3)
    for i, (label, value) in enumerate(ratios.items()):
        cols[i % 3].metric(label=label, value=value)


def render_technical_summary(tech: dict) -> None:
    """
    Renders a 4-column indicator metric grid (RSI, SMA50, SMA200, ATR)
    followed by two info boxes for the Trend Signal and Price Position.

    Parameters
    ----------
    tech : output dict from analyze_technical()
    """
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
                f"Support: **Rp {tech['support']:,.0f}** \u00a0|\u00a0 "
                f"Resistance: **Rp {tech['resistance']:,.0f}**\n\n"
                f"{tech['sr_signal']}"
            )
        else:
            sr_text = "N/A"
        st.info(f"**Price Position:** {sr_text}")


def render_fundamental_analysis(fund: dict) -> None:
    """
    Renders PE and PBV valuation metrics with sector benchmark context
    and an overall verdict.

    Parameters
    ----------
    fund : output dict from analyze_fundamental()
    """
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
