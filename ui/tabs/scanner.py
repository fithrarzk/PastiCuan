"""Watchlist scanner backed by the same contract as Telegram."""

import pandas as pd
import streamlit as st

from analysis.scanner import DEFAULT_SCAN_TICKERS, normalize_scan_tickers, run_scan
from analysis.presentation import scan_view


def _normalize_input(value: str) -> list[str]:
    tickers, _ = normalize_scan_tickers(value.split(","))
    return tickers


def render_scanner_tab(period_yf: str) -> None:
    st.caption(
        "Rank 5–10 IDX stocks with technical, fundamental, cross-sectional quant, "
        "valuation-range, and liquidity evidence. Results remain research-only."
    )
    ticker_input = st.text_area(
        "Watchlist Tickers",
        value=", ".join(DEFAULT_SCAN_TICKERS),
        height=80,
        help="Comma-separated IDX tickers; the scan is capped at 10 names for free-tier reliability.",
    )
    if not st.button("Run Research Scanner", type="primary"):
        return

    tickers = _normalize_input(ticker_input)
    if not tickers:
        st.warning("Enter at least one valid ticker.")
        return

    with st.spinner(f"Analyzing {len(tickers)} stocks..."):
        scan_period = period_yf if period_yf in {"1y", "2y", "3y"} else "3y"
        bundle = scan_view(run_scan(tickers, period=scan_period))

    rows = []
    for item in bundle["candidates"]:
        preferred = item.get("preferred_range")
        rows.append({
            "Rank": item["rank"],
            "Ticker": item["display_ticker"],
            "Price": item["current_price"],
            "Research Composite": round(item["composite_score"], 1),
            "Technical": round(item["technical_score"], 1) if item.get("technical_score") is not None else None,
            "Fundamental": round(item["fundamental_score"], 1) if item.get("fundamental_score") is not None else None,
            "Quant Percentile": round(item["quant_percentile"], 1) if item.get("quant_percentile") is not None else None,
            "Quant Scope": item["quant_scope"],
            "Preferred Low": preferred.get("low") if preferred else None,
            "Preferred High": preferred.get("high") if preferred else None,
            "Risk/Reward": round(item["risk_reward"], 2) if item.get("risk_reward") is not None else None,
            "Coverage": round(item["coverage_pct"], 0),
            "Data Grade": item["data_grade"],
            "Policy": item["policy_label"],
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No ticker passed the mandatory data, coverage, and liquidity gates.")

    if bundle["warnings"]:
        for warning in bundle["warnings"]:
            st.warning(warning)
    if bundle["excluded"]:
        st.subheader("Excluded")
        st.dataframe(pd.DataFrame(bundle["excluded"]), use_container_width=True, hide_index=True)
    st.caption(
        f"As of {bundle['as_of']} · {bundle['formula_version']} · {bundle['analysis_version']}"
    )
