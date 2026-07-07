"""Decision tab combining scores, warnings, and position sizing."""

import os
from datetime import datetime

import pandas as pd
import streamlit as st

from analysis.risk import calculate_position_size


def _fmt_money(value) -> str:
    return "N/A" if value is None or pd.isna(value) else f"Rp {value:,.0f}"


def _append_journal_row(row: dict) -> str:
    path = os.path.join("data", "trade_journal.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    exists = os.path.exists(path)
    pd.DataFrame([row]).to_csv(path, mode="a", header=not exists, index=False)
    return path


def render_decision_tab(decision: dict, tech: dict, fund: dict, ticker: str) -> None:
    st.markdown(
        f"<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:16px;'>{ticker} — Decision Engine</h3>",
        unsafe_allow_html=True,
    )
    if not decision:
        st.warning("Decision report is unavailable.")
        return

    score = decision.get("final_score")
    c1, c2, c3 = st.columns(3)
    c1.metric("Final Score", f"{score:.0f}/100" if score is not None else "N/A", decision.get("final_verdict", "N/A"), delta_color="off")
    c2.metric("Technical", f"{tech.get('technical_score', 0):.0f}/100", tech.get("recommendation", "N/A"), delta_color="off")
    c3.metric("Fundamental", f"{fund.get('fundamental_score', 0):.0f}/100", fund.get("fundamental_verdict", "N/A"), delta_color="off")

    st.info(decision.get("primary_reason", "No primary reason available."))

    components = decision.get("decision_components", {})
    if components:
        rows = [
            {"Component": key.replace("_", " ").title(), "Score": f"{value:.0f}/100"}
            for key, value in components.items()
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    warnings = decision.get("warnings", [])
    if warnings:
        st.warning("\n".join(f"- {warning}" for warning in warnings))
    else:
        st.success("No major decision warnings from the current rule engine.")

    st.divider()
    st.markdown(
        "<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:8px;'>Action Plan</h3>",
        unsafe_allow_html=True,
    )
    action = decision.get("action_plan", {})
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Entry Zone", action.get("entry_zone", "N/A"))
    a2.metric("Stop Loss", action.get("stop_loss", "N/A"))
    a3.metric("Take Profit", action.get("take_profit", "N/A"))
    a4.metric("Risk / Reward", action.get("risk_reward", "N/A"))

    st.divider()
    st.markdown(
        "<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:8px;'>Position Sizing</h3>",
        unsafe_allow_html=True,
    )
    capital = st.number_input("Capital (IDR)", min_value=1_000_000, value=100_000_000, step=1_000_000)
    risk_pct_input = st.slider("Risk per Trade (%)", min_value=0.25, max_value=5.0, value=1.0, step=0.25)
    entry = tech.get("current_price")
    stop_loss = tech.get("stop_loss")
    sizing = calculate_position_size(entry, stop_loss, capital, risk_pct_input / 100)
    s1, s2, s3, s4 = st.columns(4)
    if sizing.get("error"):
        st.error(sizing["error"])
    else:
        s1.metric("Lots", f"{sizing['lots']:,.0f}")
        s2.metric("Shares", f"{sizing['shares']:,.0f}")
        s3.metric("Position Value", _fmt_money(sizing.get("position_value")))
        s4.metric("Actual Risk", _fmt_money(sizing.get("actual_risk")), f"{sizing.get('actual_risk_pct', 0):.2f}%")

    st.divider()
    st.markdown(
        "<h3 style='font-size:1rem;font-weight:600;color:#F5F5F7;margin-bottom:8px;'>Trade Journal</h3>",
        unsafe_allow_html=True,
    )
    notes = st.text_area("Notes", placeholder="Thesis, invalidation, or follow-up plan.", height=100)
    if st.button("Save Plan to Journal", type="primary"):
        row = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "ticker": ticker,
            "verdict": decision.get("final_verdict"),
            "final_score": decision.get("final_score"),
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": tech.get("take_profit"),
            "risk_reward": tech.get("risk_reward"),
            "capital": capital,
            "risk_pct": risk_pct_input,
            "lots": sizing.get("lots", 0),
            "notes": notes,
        }
        path = _append_journal_row(row)
        st.success(f"Saved to {path}")
