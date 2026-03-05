"""Tab 2: Historical PE & PBV Standard Deviation Bands."""

import streamlit as st
import plotly.graph_objects as go

_BAND_COLORS = {
    "band_m2":   "#ef5350",
    "band_m1":   "#ff8f00",
    "band_mean": "#29b6f6",
    "band_p1":   "#ff8f00",
    "band_p2":   "#ef5350",
}
_BAND_LABELS = {
    "band_m2":   "-2 SD",
    "band_m1":   "-1 SD",
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


def _sd_label(sd_pos):
    if sd_pos is None:
        return "N/A"
    sign = "+" if sd_pos >= 0 else ""
    return f"{sign}{sd_pos:.2f} SD"


def _band_chart(band_data: dict, ratio_name: str, ticker: str):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=band_data["dates"], y=band_data["close"],
        name="Price", line=dict(color="#ffffff", width=2),
        hovertemplate="Rp %{y:,.0f}<extra></extra>",
    ))
    for key in ["band_m2", "band_m1", "band_mean", "band_p1", "band_p2"]:
        fig.add_trace(go.Scatter(
            x=band_data["dates"], y=band_data[key],
            name=_BAND_LABELS[key],
            line=dict(color=_BAND_COLORS[key], width=1.2, dash=_BAND_DASH[key]),
            hovertemplate=f"{_BAND_LABELS[key]}: Rp %{{y:,.0f}}<extra></extra>",
        ))
    fig.update_layout(
        title=f"{ticker} — Historical {ratio_name} Valuation Bands",
        template="plotly_dark", height=500,
        yaxis_title="Price (IDR)", xaxis_title="",
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        hovermode="x unified",
    )
    return fig


def render_valuation_tab(bands: dict, ticker: str) -> None:
    st.markdown(
        "The stock price is plotted against **Mean ±1 SD / ±2 SD** valuation bands, "
        "derived from historical quarterly earnings and book value data."
    )

    # ── PE Bands ──────────────────────────────────────────────────────────────
    st.subheader("📐 PE Valuation Bands")
    pe = bands.get("pe")
    if pe:
        m1, m2, m3 = st.columns(3)
        m1.metric("Historical Mean PE", f"{pe['pe_mean']:.2f}x")
        m2.metric("1 SD", f"±{pe['pe_std']:.2f}x")
        m3.metric("Current PE Position", f"{pe['current_pe']:.2f}x",
                  _sd_label(pe["sd_position"]), delta_color="off")
        sd = pe["sd_position"]
        if sd <= -2:
            st.success(f"🟢 Currently at **{_sd_label(sd)}** — deeply undervalued vs history")
        elif sd <= -1:
            st.info(f"🔵 Currently at **{_sd_label(sd)}** — below average valuation")
        elif sd >= 2:
            st.error(f"🔴 Currently at **{_sd_label(sd)}** — significantly overvalued vs history")
        elif sd >= 1:
            st.warning(f"🟠 Currently at **{_sd_label(sd)}** — above average valuation")
        else:
            st.info(f"⚪ Currently at **{_sd_label(sd)}** — near historical mean")
        st.plotly_chart(_band_chart(pe, "PE", ticker), use_container_width=True)
    else:
        st.warning(
            "PE band data unavailable — requires sufficient quarterly earnings history.",
            icon="⚠️",
        )

    st.divider()

    # ── PBV Bands ─────────────────────────────────────────────────────────────
    st.subheader("📐 PBV Valuation Bands")
    pbv = bands.get("pbv")
    if pbv:
        m1, m2, m3 = st.columns(3)
        m1.metric("Historical Mean PBV", f"{pbv['pbv_mean']:.2f}x")
        m2.metric("1 SD", f"±{pbv['pbv_std']:.2f}x")
        m3.metric("Current PBV Position", f"{pbv['current_pbv']:.2f}x",
                  _sd_label(pbv["sd_position"]), delta_color="off")
        sd_p = pbv["sd_position"]
        if sd_p <= -2:
            st.success(f"🟢 Currently at **{_sd_label(sd_p)}** — deeply undervalued vs history")
        elif sd_p <= -1:
            st.info(f"🔵 Currently at **{_sd_label(sd_p)}** — below average book value multiple")
        elif sd_p >= 2:
            st.error(f"🔴 Currently at **{_sd_label(sd_p)}** — significantly overvalued vs history")
        elif sd_p >= 1:
            st.warning(f"🟠 Currently at **{_sd_label(sd_p)}** — above average book value multiple")
        else:
            st.info(f"⚪ Currently at **{_sd_label(sd_p)}** — near historical mean")
        st.plotly_chart(_band_chart(pbv, "PBV", ticker), use_container_width=True)
    else:
        st.warning(
            "PBV band data unavailable — requires sufficient quarterly balance sheet history.",
            icon="⚠️",
        )
