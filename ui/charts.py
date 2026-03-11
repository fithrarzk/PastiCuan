import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_PLOTLY_FONT = dict(family="Inter, -apple-system, BlinkMacSystemFont, sans-serif",
                    color="#F5F5F7", size=12)
_PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=_PLOTLY_FONT,
    margin=dict(l=10, r=10, t=50, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                font=dict(size=11, color="#8E8E93")),
    xaxis=dict(showgrid=False, zeroline=False, linecolor="#38383A",
               tickfont=dict(color="#8E8E93", size=11)),
)
_PLOTLY_YAXIS = dict(gridcolor="#2C2C2E", gridwidth=0.5, zeroline=False,
                     linecolor="#38383A", tickfont=dict(color="#8E8E93", size=11))
_CONFIG = {"displayModeBar": False}


def render_price_chart(tech: dict, ticker: str) -> None:
    """
    Renders an interactive Plotly chart with:
    - Candlestick price (row 1)
    - SMA 50 and SMA 200 overlay (row 1)
    - Dotted Support and Resistance lines (row 1)
    - RSI (14) sub-plot (row 2)
    - MACD (12,26,9) sub-plot (row 3)
    - Volume bar chart (inline Plotly)
    """
    df = tech["df"]

    has_macd = "MACD" in df.columns and not df["MACD"].isna().all()

    if has_macd:
        row_heights = [0.55, 0.22, 0.23]
        titles = (f"{ticker} — Price", "RSI (14)", "MACD (12, 26, 9)")
    else:
        row_heights = [0.72, 0.28]
        titles = (f"{ticker} — Price", "RSI (14)")

    fig = make_subplots(
        rows=3 if has_macd else 2, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.03,
        subplot_titles=titles,
    )

    # Update subplot title font
    for ann in fig.layout.annotations:
        ann.font = dict(size=11, color="#8E8E93", family="Inter, sans-serif")

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"],
            low=df["Low"],   close=df["Close"],
            name="Price",
            increasing_line_color="#10B981",
            decreasing_line_color="#EF4444",
            increasing_fillcolor="#10B981",
            decreasing_fillcolor="#EF4444",
        ), row=1, col=1,
    )

    # SMA 50
    fig.add_trace(
        go.Scatter(x=df.index, y=df["SMA50"], name="SMA 50",
                   line=dict(color="#64748B", width=1.2)), row=1, col=1,
    )

    # SMA 200
    fig.add_trace(
        go.Scatter(x=df.index, y=df["SMA200"], name="SMA 200",
                   line=dict(color="#A78BFA", width=1.2)), row=1, col=1,
    )

    # Support line
    if tech["support"]:
        fig.add_hline(
            y=tech["support"], line_dash="dot", line_color="#10B981", line_width=1,
            annotation_text=f"Support  Rp {tech['support']:,.0f}",
            annotation_position="bottom right",
            annotation_font=dict(size=10, color="#10B981"),
            row=1, col=1,
        )

    # Resistance line
    if tech["resistance"]:
        fig.add_hline(
            y=tech["resistance"], line_dash="dot", line_color="#EF4444", line_width=1,
            annotation_text=f"Resistance  Rp {tech['resistance']:,.0f}",
            annotation_position="top right",
            annotation_font=dict(size=10, color="#EF4444"),
            row=1, col=1,
        )

    # RSI
    fig.add_trace(
        go.Scatter(x=df.index, y=df["RSI"], name="RSI",
                   line=dict(color="#8E8E93", width=1.2)), row=2, col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color="#EF4444", line_width=0.8, row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#10B981", line_width=0.8, row=2, col=1)

    # MACD subplot (row 3)
    if has_macd:
        hist_colors = [
            "#10B981" if v >= 0 else "#EF4444"
            for v in df["MACD_Hist"].fillna(0)
        ]
        fig.add_trace(
            go.Bar(
                x=df.index, y=df["MACD_Hist"], name="Histogram",
                marker_color=hist_colors, showlegend=False, opacity=0.7,
            ), row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["MACD"], name="MACD",
                line=dict(color="#F5F5F7", width=1.2),
            ), row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["MACD_Signal"], name="Signal",
                line=dict(color="#64748B", width=1.2),
            ), row=3, col=1,
        )
        fig.add_hline(y=0, line_dash="solid", line_color="#38383A", line_width=0.8, row=3, col=1)
        fig.update_yaxes(title_text="MACD", title_font=dict(size=10, color="#8E8E93"),
                         row=3, col=1, **_PLOTLY_YAXIS)

    fig.update_yaxes(title_text="Price (IDR)", title_font=dict(size=10, color="#8E8E93"),
                     row=1, col=1, **_PLOTLY_YAXIS)
    fig.update_yaxes(title_text="RSI", range=[0, 100],
                     title_font=dict(size=10, color="#8E8E93"),
                     row=2, col=1, **_PLOTLY_YAXIS)
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#38383A",
                     tickfont=dict(color="#8E8E93", size=11))

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=750 if has_macd else 600,
        **_PLOTLY_LAYOUT,
    )

    st.plotly_chart(fig, use_container_width=True, config=_CONFIG)

    # Volume — inline Plotly for consistent styling
    vol_fig = go.Figure(go.Bar(
        x=df.index, y=df["Volume"],
        marker_color="#C7C7CC", showlegend=False,
        hovertemplate="Vol: %{y:,.0f}<extra></extra>",
    ))
    vol_fig.update_layout(
        height=120,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_PLOTLY_FONT,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis=dict(gridcolor="#2C2C2E", gridwidth=0.5, zeroline=False,
                   tickfont=dict(color="#8E8E93", size=10)),
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(color="#8E8E93", size=10)),
    )
    st.caption("Volume")
    st.plotly_chart(vol_fig, use_container_width=True, config=_CONFIG)
