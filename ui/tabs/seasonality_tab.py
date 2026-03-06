"""Tab 4: Monthly seasonality analysis."""

import streamlit as st
import plotly.graph_objects as go

_CONFIG = {"displayModeBar": False}
_FONT   = dict(family="Inter, -apple-system, sans-serif", color="#1E1E1E", size=12)
_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=_FONT,
    margin=dict(l=10, r=10, t=50, b=10),
    showlegend=False,
    xaxis=dict(showgrid=False, zeroline=False, linecolor="#E5E5E5",
               tickfont=dict(color="#6E6E73", size=11)),
    yaxis=dict(gridcolor="#F0F0F0", gridwidth=0.5, zeroline=False,
               linecolor="#E5E5E5", tickfont=dict(color="#6E6E73", size=11)),
)


def render_seasonality_tab(seasonality: dict, ticker: str) -> None:
    avg   = seasonality["monthly_avg"]
    pos   = seasonality["monthly_pos_pct"]
    names = seasonality["month_names"]
    best  = seasonality["best_month"]
    worst = seasonality["worst_month"]

    if avg.empty:
        st.warning("Insufficient history for seasonality — need at least 2 years of data.")
        return

    # ── Summary metrics ───────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    if best:
        c1.metric("Best Month", names[best - 1], f"{avg[best]:+.2f}%")
    if worst:
        c2.metric("Worst Month", names[worst - 1], f"{avg[worst]:+.2f}%")
    years = int(seasonality["monthly_count"].max()) if not seasonality["monthly_count"].empty else 0
    c3.metric("Years of Data", years)

    st.divider()

    # ── Average monthly return bar chart ──────────────────────────────────────
    months_all = list(range(1, 13))
    avg_vals   = [avg.get(m, 0.0) for m in months_all]
    pos_vals   = [pos.get(m, 0.0) for m in months_all]
    bar_colors = ["#10B981" if v >= 0 else "#EF4444" for v in avg_vals]

    fig = go.Figure(go.Bar(
        x=names, y=avg_vals,
        marker_color=bar_colors, opacity=0.85,
        text=[f"{v:+.2f}%" for v in avg_vals],
        textposition="outside",
        textfont=dict(size=10, color="#6E6E73"),
        hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=f"{ticker} — Average Monthly Return",
                   font=dict(size=13, color="#1E1E1E", family="Inter, sans-serif")),
        height=400,
        yaxis_title="Avg Return (%)",
        **_LAYOUT,
    )
    st.plotly_chart(fig, use_container_width=True, config=_CONFIG)

    # ── Win-rate bar chart ────────────────────────────────────────────────────
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#1E1E1E;margin-bottom:16px;'>Monthly Win Rate</h3>",
                unsafe_allow_html=True)
    fig2 = go.Figure(go.Bar(
        x=names, y=pos_vals,
        marker_color="#64748B", opacity=0.75,
        text=[f"{v:.0f}%" for v in pos_vals],
        textposition="outside",
        textfont=dict(size=10, color="#6E6E73"),
        hovertemplate="%{x}: %{y:.1f}% positive years<extra></extra>",
    ))
    fig2.add_hline(
        y=50, line_dash="dot", line_color="#C7C7CC", line_width=1,
        annotation_text="50%", annotation_position="bottom right",
        annotation_font=dict(size=10, color="#6E6E73"),
    )
    fig2.update_layout(
        height=340,
        yaxis_title="Win Rate (%)",
        yaxis_range=[0, 115],
        **_LAYOUT,
    )
    st.plotly_chart(fig2, use_container_width=True, config=_CONFIG)

    # ── Year × Month heatmap ──────────────────────────────────────────────────
    st.markdown("<h3 style='font-size:1rem;font-weight:600;color:#1E1E1E;margin-bottom:16px;'>Year × Month Return Heatmap</h3>",
                unsafe_allow_html=True)
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
            textfont=dict(size=9),
            hovertemplate="Year %{y} %{x}: %{z:.2f}%<extra></extra>",
            colorbar=dict(title="Return %",
                          tickfont=dict(size=10, color="#6E6E73"),
                          titlefont=dict(size=11, color="#6E6E73")),
        ))
        fig3.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=_FONT,
            height=max(300, 28 * len(pivot)),
            margin=dict(l=10, r=10, t=20, b=10),
            xaxis=dict(title="Month", showgrid=False, zeroline=False,
                       tickfont=dict(color="#6E6E73", size=11)),
            yaxis=dict(title="Year", showgrid=False, zeroline=False,
                       tickfont=dict(color="#6E6E73", size=11)),
        )
        st.plotly_chart(fig3, use_container_width=True, config=_CONFIG)
