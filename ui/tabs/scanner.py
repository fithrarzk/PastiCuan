"""Immutable full-LQ45 scanner view backed by the same contract as Telegram."""

import pandas as pd
import streamlit as st

from analysis.presentation import scan_view
from analysis.scan_snapshots import get_scan_snapshot
from analysis.scanner import normalize_scan_tickers


def _normalize_input(value: str) -> list[str]:
    tickers, _ = normalize_scan_tickers(value.split(","))
    return tickers


def render_scanner_tab(_period_yf: str) -> None:
    st.caption(
        "Read the latest full-LQ45 end-of-day snapshot. Optional tickers only "
        "filter the frozen ranks; this page never recalculates a small universe."
    )
    ticker_input = st.text_area(
        "Optional ticker filter",
        value="",
        height=80,
        help="Leave blank for the full result, or enter up to 10 comma-separated LQ45 tickers.",
    )
    if not st.button("Load Research Snapshot", type="primary"):
        return

    tickers = _normalize_input(ticker_input)[:10] if ticker_input.strip() else None
    if ticker_input.strip() and not tickers:
        st.warning("No valid IDX ticker filter was found.")
        return
    with st.spinner("Loading the latest approved database snapshot..."):
        bundle = scan_view(get_scan_snapshot().to_bundle(tickers))

    st.caption(
        f"Mode {bundle['mode']} · Session {bundle['session_date'] or 'N/A'} · "
        f"LQ45 coverage {bundle['universe_coverage_pct']:.0f}% · "
        f"Snapshot {bundle['snapshot_id'] or 'unavailable'}"
    )

    rows = []
    for item in bundle["candidates"]:
        entry = item.get("entry_zone") or {}
        rows.append({
            "Rank": item["rank"],
            "Ticker": item["display_ticker"],
            "Price": item["current_price"],
            "Eligibility": item["eligibility"],
            "Business Score": round(item["ranking_score"], 1) if item.get("ranking_score") is not None else None,
            "Technical": round(item["technical_score"], 1) if item.get("technical_score") is not None else None,
            "Quant Percentile": round(item["quant_percentile"], 1) if item.get("quant_percentile") is not None else None,
            "Entry Low": entry.get("low"),
            "Entry High": entry.get("high"),
            "Risk/Reward": round(item["risk_reward"], 2) if item.get("risk_reward") is not None else None,
            "Coverage": round(item["coverage_pct"], 0),
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
    st.caption(f"Created {bundle['as_of']} · {bundle['formula_version']} · {bundle['analysis_version']}")
