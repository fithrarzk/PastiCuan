"""Pure presentation model shared by Streamlit and Telegram."""

from __future__ import annotations


def decision_view(decision: dict) -> dict:
    components = decision.get("decision_components", {})
    return {
        "score": decision.get("final_score"),
        "label": decision.get("final_verdict", "WAIT_FOR_DATA"),
        "coverage_pct": decision.get("coverage_pct", 0),
        "technical": components.get("technical"),
        "fundamental": components.get("fundamental"),
        "backtest": components.get("backtest"),
        "liquidity": components.get("liquidity"),
        "reason": decision.get("primary_reason", ""),
        "warnings": list(decision.get("warnings", [])),
    }


def display_number(value, suffix="/100", decimals=1) -> str:
    return "N/A" if value is None else f"{value:.{decimals}f}{suffix}"

