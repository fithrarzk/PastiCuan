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


def scan_view(scan) -> dict:
    """Return the exact scanner contract consumed by every interface."""
    value = scan.to_dict() if hasattr(scan, "to_dict") else dict(scan)
    return {
        "as_of": value.get("as_of"),
        "analysis_version": value.get("analysis_version"),
        "formula_version": value.get("formula_version"),
        "policy_label": value.get("policy_label", "RESEARCH_ONLY"),
        "requested_tickers": list(value.get("requested_tickers", [])),
        "candidates": list(value.get("candidates", [])),
        "excluded": list(value.get("excluded", [])),
        "warnings": list(value.get("warnings", [])),
    }
