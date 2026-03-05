"""Tab 5: Advanced Technical Chart."""

import streamlit as st

from ui.charts import render_price_chart


def render_technical_tab(tech: dict, ticker: str, history) -> None:
    st.subheader(f"📉 {ticker} — Technical Chart")
    render_price_chart(tech, ticker)
    with st.expander("📋 Raw Historical Data"):
        fmt = history[["Open", "High", "Low", "Close", "Volume"]].copy()
        fmt.index = fmt.index.strftime("%Y-%m-%d")
        st.dataframe(fmt.sort_index(ascending=False), use_container_width=True)
