import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def render_price_chart(tech: dict, ticker: str) -> None:
    """
    Renders an interactive Plotly chart with:
    - Candlestick price (row 1)
    - SMA 50 and SMA 200 overlay (row 1)
    - Dotted Support and Resistance lines (row 1)
    - RSI (14) sub-plot (row 2)
    - Volume bar chart (below figure)

    Parameters
    ----------
    tech   : output dict from analyze_technical()
    ticker : resolved ticker string used as the chart title
    """
    df = tech["df"]

    has_macd = "MACD" in df.columns and not df["MACD"].isna().all()

    if has_macd:
        row_heights = [0.55, 0.22, 0.23]
        titles = (f"{ticker} – Price + SMAs", "RSI (14)", "MACD (12, 26, 9)")
    else:
        row_heights = [0.72, 0.28]
        titles = (f"{ticker} – Price + SMAs", "RSI (14)")

    fig = make_subplots(
        rows=3 if has_macd else 2, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.03,
        subplot_titles=titles,
    )

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"], high=df["High"],
            low=df["Low"],   close=df["Close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ), row=1, col=1,
    )

    # SMA 50
    fig.add_trace(
        go.Scatter(x=df.index, y=df["SMA50"], name="SMA 50",
                   line=dict(color="#f0a500", width=1.5)), row=1, col=1,
    )

    # SMA 200
    fig.add_trace(
        go.Scatter(x=df.index, y=df["SMA200"], name="SMA 200",
                   line=dict(color="#7c83fd", width=1.5)), row=1, col=1,
    )

    # Support line
    if tech["support"]:
        fig.add_hline(
            y=tech["support"], line_dash="dot", line_color="#4caf50", line_width=1,
            annotation_text=f"Support  Rp {tech['support']:,.0f}",
            annotation_position="bottom right", row=1, col=1,
        )

    # Resistance line
    if tech["resistance"]:
        fig.add_hline(
            y=tech["resistance"], line_dash="dot", line_color="#ef5350", line_width=1,
            annotation_text=f"Resistance  Rp {tech['resistance']:,.0f}",
            annotation_position="top right", row=1, col=1,
        )

    # RSI
    fig.add_trace(
        go.Scatter(x=df.index, y=df["RSI"], name="RSI (14)",
                   line=dict(color="#ba68c8", width=1.5)), row=2, col=1,
    )
    fig.add_hline(y=70, line_dash="dash", line_color="#ef5350", line_width=1, row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#26a69a", line_width=1, row=2, col=1)

    # ── MACD subplot (row 3) ──────────────────────────────────────────────
    if has_macd:
        # MACD histogram as colored bars
        hist_colors = [
            "#26a69a" if v >= 0 else "#ef5350"
            for v in df["MACD_Hist"].fillna(0)
        ]
        fig.add_trace(
            go.Bar(
                x=df.index, y=df["MACD_Hist"], name="Histogram",
                marker_color=hist_colors, showlegend=False,
            ), row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["MACD"], name="MACD",
                line=dict(color="#29b6f6", width=1.5),
            ), row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=df["MACD_Signal"], name="Signal",
                line=dict(color="#ff8f00", width=1.5),
            ), row=3, col=1,
        )
        fig.add_hline(y=0, line_dash="solid", line_color="#555", line_width=0.8, row=3, col=1)
        fig.update_yaxes(title_text="MACD", row=3, col=1)

    fig.update_yaxes(title_text="Price (IDR)", row=1, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=750 if has_macd else 600,
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Volume**")
    st.bar_chart(df[["Volume"]], height=140)
