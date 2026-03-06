"""Tab 2: Historical PE & PBV Standard Deviation Bands."""

import streamlit as st
import plotly.graph_objects as go

_BAND_COLORS = {
    "band_m2":   "rgba(239,68,68,0.7)",
    "band_m1":   "rgba(245,158,11,0.7)",
    "band_mean": "rgba(30,30,30,0.8)",
    "band_p1":   "rgba(245,158,11,0.7)",
    "band_p2":   "rgba(239,68,68,0.7)",
}
_BAND_LABELS = {
    "band_m2":   "−2 SD",
    "band_m1":   "−1 SD",
    "band_mean": "Mean",
    "band_p1":   "+1 SD",
    "band_p2":   "+2 SD",
}
_BAND_DASH = {
    "band_m2":   "dash",
    "band_m1":   "dot",
    "band_mean": "solid",
    "band_p1":   "dot",
    "band_p2":   "dash",
}
_CONFIG = {"displayModeBar": False}


def _sd_label(sd_pos):
    if sd_pos is None:
        return "N/A"
    sign = "+" if sd_pos >= 0 else ""
    return f"{sign}{sd_pos:.2f} SD"


def _band_chart(band_data: dict, ratio_name: str, ticker: str):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=band_data["dates"], y=band_data["close"],
        name="Price", line=dict(color="#1E1E1E", width=1.5),
        hovertemplate="Rp %{y:,.0f}<extra></extra>",
    ))
    for key in ["band_m2", "band_m1", "band_mean", "band_p1", "band_p2"]:
        fig.add_trace(go.Scatter(
            x=band_data["dates"], y=band_data[key],
            name=_BAND_LABELS[key],
            line=dict(color=_BAND_COLORS[key], width=1.0, dash=_BAND_DASH[key]),
            hovertemplate=f"{_BAND_LABELS[key]}: Rp %{{y:,.0f}}<extra></extra>",
        ))
    fig.update_layout(
        title=dict(text=f"{ticker} — Historical {ratio_name} Valuation Bands",
                   font=dict(size=13, color="#1E1E1E", family="Inter, sans-serif")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=500,
        font=dict(family="Inter, -apple-system, sans-serif", color="#1E1E1E", size=12),
        yaxis=dict(title="Price (IDR)", gridcolor="#F0F0F0", gridwidth=0.5,
                   zeroline=False, linecolor="#E5E5E5",
                   tickfont=dict(color="#6E6E73", size=11)),
        xaxis=dict(title="", showgrid=False, zeroline=False, linecolor="#E5E5E5",
                   tickfont=dict(color="#6E6E73", size=11)),
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                    font=dict(size=11, color="#6E6E73")),
        hovermode="x unified",
    )
    return fig


def render_valuation_tab(bands: dict, ticker: str) -> None:
    st.caption(
        "Stock price plotted against Mean ±1 SD / ±2 SD valuation bands, "
        "derived from historical quarterly earnings and book value data."
    )

    # ── PE Bands ──────────────────────────────────────────────────────────────
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#1E1E1E;margin-bottom:16px;'>PE Valuation Bands</h3>",
                unsafe_allow_html=True)
    pe = bands.get("pe")
    if pe:
        m1, m2, m3 = st.columns(3)
        m1.metric("Historical Mean PE", f"{pe['pe_mean']:.2f}x")
        m2.metric("1 SD", f"±{pe['pe_std']:.2f}x")
        m3.metric("Current PE Position", f"{pe['current_pe']:.2f}x",
                  _sd_label(pe["sd_position"]), delta_color="off")
        sd = pe["sd_position"]
        if sd <= -2:
            st.success(f"Currently at **{_sd_label(sd)}** — deeply undervalued vs history")
        elif sd <= -1:
            st.info(f"Currently at **{_sd_label(sd)}** — below average valuation")
        elif sd >= 2:
            st.error(f"Currently at **{_sd_label(sd)}** — significantly overvalued vs history")
        elif sd >= 1:
            st.warning(f"Currently at **{_sd_label(sd)}** — above average valuation")
        else:
            st.info(f"Currently at **{_sd_label(sd)}** — near historical mean")
        st.plotly_chart(_band_chart(pe, "PE", ticker), use_container_width=True, config=_CONFIG)
    else:
        st.warning("PE band data unavailable — requires sufficient quarterly earnings history.")

    st.divider()

    # ── PBV Bands ─────────────────────────────────────────────────────────────
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#1E1E1E;margin-bottom:16px;'>PBV Valuation Bands</h3>",
                unsafe_allow_html=True)
    pbv = bands.get("pbv")
    if pbv:
        m1, m2, m3 = st.columns(3)
        m1.metric("Historical Mean PBV", f"{pbv['pbv_mean']:.2f}x")
        m2.metric("1 SD", f"±{pbv['pbv_std']:.2f}x")
        m3.metric("Current PBV Position", f"{pbv['current_pbv']:.2f}x",
                  _sd_label(pbv["sd_position"]), delta_color="off")
        sd_p = pbv["sd_position"]
        if sd_p <= -2:
            st.success(f"Currently at **{_sd_label(sd_p)}** — deeply undervalued vs history")
        elif sd_p <= -1:
            st.info(f"Currently at **{_sd_label(sd_p)}** — below average book value multiple")
        elif sd_p >= 2:
            st.error(f"Currently at **{_sd_label(sd_p)}** — significantly overvalued vs history")
        elif sd_p >= 1:
            st.warning(f"Currently at **{_sd_label(sd_p)}** — above average book value multiple")
        else:
            st.info(f"Currently at **{_sd_label(sd_p)}** — near historical mean")
        st.plotly_chart(_band_chart(pbv, "PBV", ticker), use_container_width=True, config=_CONFIG)
    else:
        st.warning("PBV band data unavailable — requires sufficient quarterly balance sheet history.")
