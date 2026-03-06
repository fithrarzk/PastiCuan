"""Tab 3: Competitor side-by-side comparison."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf

from data.extended import get_comparison_data

_COLORS = ["#29b6f6", "#ef5350", "#26a69a", "#f0a500", "#ba68c8", "#ff8f00", "#7c83fd"]


def render_comparison_tab(main_ticker: str, period_yf: str) -> None:
    st.markdown(
        "Enter comma-separated competitor tickers to compare normalised price performance "
        "and key metrics side by side."
    )
    comp_input = st.text_input(
        "Competitor Tickers",
        placeholder="e.g. BBRI, BMRI, BNIS",
        help="IDX tickers separated by commas. '.JK' is appended automatically.",
        key="comparison_input",
    )
    if not comp_input.strip():
        st.info("Enter competitor tickers above to begin comparison.", icon="👆")
        return

    tickers_raw = [t.strip() for t in comp_input.split(",") if t.strip()]
    all_tickers  = [main_ticker] + tickers_raw

    with st.spinner("Fetching comparison data …"):
        hist_map = get_comparison_data(all_tickers, period=period_yf)

    if not hist_map:
        st.error("No data retrieved. Please check the tickers and try again.")
        return

    # ── Normalised performance chart ──────────────────────────────────────────
    st.subheader("📈 Normalised Price Performance (Base = 100)")
    fig = go.Figure()
    for i, (tkr, hist) in enumerate(hist_map.items()):
        close = hist["Close"]
        norm  = close / close.iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=close.index, y=norm, name=tkr,
            line=dict(color=_COLORS[i % len(_COLORS)], width=2),
            hovertemplate=f"{tkr}: %{{y:.1f}}<extra></extra>",
        ))
    fig.update_layout(
        template="plotly_dark", height=450,
        yaxis_title="Normalised Price (%)",
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Metrics table ─────────────────────────────────────────────────────────
    st.subheader("📊 Side-by-Side Performance Metrics")
    rows = []
    # Parallel raw-numeric dict for best-performer highlighting
    raw = []
    for tkr_raw in all_tickers:
        tkr_norm = tkr_raw.strip().upper()
        if not tkr_norm.endswith(".JK"):
            tkr_norm += ".JK"
        try:
            info = yf.Ticker(tkr_norm).info
            hist = hist_map.get(tkr_norm, pd.DataFrame())
            total_ret = (
                (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                if not hist.empty and len(hist) > 1
                else None
            )
            pe_v   = info.get("trailingPE")
            pbv_v  = info.get("priceToBook")
            roe_v  = info.get("returnOnEquity")
            dy_v   = info.get("dividendYield")
            npm_v  = info.get("profitMargins")

            rows.append({
                "Ticker":           tkr_norm,
                "Company":          info.get("shortName") or tkr_norm,
                "Last Price (IDR)": f"Rp {info['previousClose']:,.0f}" if info.get("previousClose") else "N/A",
                "PE":               f"{pe_v:.2f}x"          if pe_v  is not None else "N/A",
                "PBV":              f"{pbv_v:.2f}x"         if pbv_v is not None else "N/A",
                "ROE":              f"{roe_v*100:.2f}%"     if roe_v is not None else "N/A",
                "DY":               f"{dy_v*100:.2f}%"      if dy_v  is not None else "N/A",
                "NPM":              f"{npm_v*100:.2f}%"     if npm_v is not None else "N/A",
                f"Return ({period_yf})": f"{total_ret:+.2f}%" if total_ret is not None else "N/A",
            })
            raw.append({
                "PE": pe_v, "PBV": pbv_v,
                "ROE": roe_v, "DY": dy_v, "NPM": npm_v,
                "Return": total_ret,
            })
        except Exception:
            rows.append({"Ticker": tkr_norm, "Company": "Error fetching data"})
            raw.append({})

    if rows:
        display_df = pd.DataFrame(rows)

        # Determine best value per category (lowest PE/PBV, highest ROE/DY/NPM/Return)
        _LOWER_IS_BETTER = {"PE", "PBV"}
        _HIGHER_IS_BETTER = {"ROE", "DY", "NPM", "Return"}
        best_idx = {}
        for col in _LOWER_IS_BETTER | _HIGHER_IS_BETTER:
            vals = [(i, r.get(col)) for i, r in enumerate(raw) if r.get(col) is not None]
            if vals:
                if col in _LOWER_IS_BETTER:
                    best_idx[col] = min(vals, key=lambda x: x[1])[0]
                else:
                    best_idx[col] = max(vals, key=lambda x: x[1])[0]

        # Map raw col names to display col names
        col_map = {
            "PE": "PE", "PBV": "PBV", "ROE": "ROE",
            "DY": "DY", "NPM": "NPM", "Return": f"Return ({period_yf})",
        }

        def _highlight_best(df_style):
            styles = pd.DataFrame("", index=df_style.index, columns=df_style.columns)
            for raw_col, row_idx in best_idx.items():
                disp_col = col_map.get(raw_col, raw_col)
                if disp_col in styles.columns:
                    styles.at[row_idx, disp_col] = "background-color: #26a69a44; font-weight: bold"
            return styles

        styled = display_df.style.apply(_highlight_best, axis=None)
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # ── Build comparison summary for AI prompt ────────────────────────────
        summary_parts = []
        for raw_col, row_idx in best_idx.items():
            tkr_name = rows[row_idx].get("Ticker", "?")
            summary_parts.append(f"{tkr_name} has best {raw_col}")
        if summary_parts:
            st.session_state["comparison_summary"] = "; ".join(summary_parts)
