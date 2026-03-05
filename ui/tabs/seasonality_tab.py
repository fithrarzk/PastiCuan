"""Tab 4: Monthly seasonality analysis."""

import streamlit as st
import plotly.graph_objects as go


def render_seasonality_tab(seasonality: dict, ticker: str) -> None:
    avg   = seasonality["monthly_avg"]
    pos   = seasonality["monthly_pos_pct"]
    names = seasonality["month_names"]
    best  = seasonality["best_month"]
    worst = seasonality["worst_month"]

    if avg.empty:
        st.warning(
            "Insufficient history for seasonality — need at least 2 years of data.",
            icon="⚠️",
        )
        return

    # ── Summary metrics ───────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    if best:
        c1.metric("Best Month (avg)", names[best - 1], f"{avg[best]:+.2f}%")
    if worst:
        c2.metric("Worst Month (avg)", names[worst - 1], f"{avg[worst]:+.2f}%")
    years = int(seasonality["monthly_count"].max()) if not seasonality["monthly_count"].empty else 0
    c3.metric("Years of Data", years)

    st.divider()

    # ── Average monthly return bar chart ──────────────────────────────────────
    months_all = list(range(1, 13))
    avg_vals   = [avg.get(m, 0.0) for m in months_all]
    pos_vals   = [pos.get(m, 0.0) for m in months_all]
    bar_colors = ["#26a69a" if v >= 0 else "#ef5350" for v in avg_vals]

    fig = go.Figure(go.Bar(
        x=names, y=avg_vals,
        marker_color=bar_colors,
        text=[f"{v:+.2f}%" for v in avg_vals],
        textposition="outside",
        hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        title=f"{ticker} — Average Monthly Return by Calendar Month",
        template="plotly_dark", height=420,
        yaxis_title="Avg Return (%)",
        margin=dict(l=10, r=10, t=50, b=10),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Win-rate bar chart ────────────────────────────────────────────────────
    st.subheader("📅 Positive-Month Win Rate (%)")
    fig2 = go.Figure(go.Bar(
        x=names, y=pos_vals,
        marker_color=["#29b6f6"] * 12,
        text=[f"{v:.0f}%" for v in pos_vals],
        textposition="outside",
        hovertemplate="%{x}: %{y:.1f}% positive years<extra></extra>",
    ))
    fig2.add_hline(
        y=50, line_dash="dash", line_color="#ffffff", line_width=1,
        annotation_text="50% line", annotation_position="bottom right",
    )
    fig2.update_layout(
        template="plotly_dark", height=360,
        yaxis_title="Win Rate (%)", yaxis_range=[0, 115],
        margin=dict(l=10, r=10, t=20, b=10),
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── Year × Month heatmap ──────────────────────────────────────────────────
    st.subheader("🗓 Year × Month Return Heatmap")
    monthly_ret = seasonality["monthly_returns"]
    if not monthly_ret.empty:
        pivot = (
            monthly_ret.to_frame("ret")
            .assign(year=monthly_ret.index.year, month=monthly_ret.index.month)
            .pivot(index="year", columns="month", values="ret")
        )
        pivot.columns = [names[m - 1] for m in pivot.columns]
        fig3 = go.Figure(go.Heatmap(
            z=pivot.values,
            x=list(pivot.columns),
            y=[str(y) for y in pivot.index],
            colorscale="RdYlGn", zmid=0,
            text=[[f"{v:.1f}%" if v == v else "" for v in row] for row in pivot.values],
            texttemplate="%{text}",
            hovertemplate="Year %{y} %{x}: %{z:.2f}%<extra></extra>",
            colorbar=dict(title="Return %"),
        ))
        fig3.update_layout(
            template="plotly_dark",
            height=max(300, 30 * len(pivot)),
            margin=dict(l=10, r=10, t=20, b=10),
            xaxis_title="Month", yaxis_title="Year",
        )
        st.plotly_chart(fig3, use_container_width=True)
