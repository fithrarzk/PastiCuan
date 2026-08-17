"""Gated decision policy. Evidence stays separate; missing data is never neutral."""

from __future__ import annotations

import pandas as pd

from analysis.contracts import DataQualityReport, DecisionLabel, GateResult


def _clip(value: float) -> float:
    return float(max(0, min(100, value)))


def _fmt_price(value) -> str:
    return "N/A" if value is None or pd.isna(value) else f"Rp {value:,.0f}"


def _backtest_evidence(backtest: dict | None) -> float | None:
    if not backtest or backtest.get("error") or not backtest.get("costs_configured"):
        return None
    s = backtest.get("summary", {})
    if s.get("total_trades", 0) < 30 or s.get("sample_sessions", 0) < 5 * 252:
        return None
    pf, expectancy = s.get("profit_factor"), s.get("expectancy")
    if pf is None or expectancy is None:
        return None
    return _clip(50 + (s.get("win_rate", 50) - 50) * .35 + (min(pf, 2) - 1) * 25)


def _liquidity_evidence(liquidity: dict | None) -> float | None:
    value = (liquidity or {}).get("avg_value")
    if value is None:
        return None
    if value >= 25_000_000_000:
        return 90.0
    if value >= 10_000_000_000:
        return 75.0
    if value >= 3_000_000_000:
        return 60.0
    if value >= 1_000_000_000:
        return 45.0
    return 20.0


def _evidence_description(score: float | None) -> str:
    if score is None:
        return "Unavailable"
    if score >= 70:
        return "Supportive research evidence"
    if score >= 50:
        return "Mixed research evidence"
    return "Weak research evidence"


def build_decision_report(
    tech: dict,
    fund: dict,
    bands: dict | None = None,
    seasonality: dict | None = None,
    backtest: dict | None = None,
    liquidity: dict | None = None,
    *,
    data_quality: DataQualityReport | None = None,
    model_validated: bool = False,
    shadow_sessions: int = 0,
    validation_run_id: str | None = None,
    action_policy_enabled: bool = False,
) -> dict:
    """Return a policy label only after every mandatory gate passes.

    ``final_score`` is retained as a compatibility field but deliberately stays
    unavailable: long-horizon business evidence and short-horizon setup evidence
    are not commensurate quantities.
    """
    tech_score = tech.get("technical_score")
    fund_score = fund.get("fundamental_score")
    backtest_score = _backtest_evidence(backtest)
    liquidity_score = _liquidity_evidence(liquidity)
    rr = tech.get("risk_reward")
    components = {
        "technical": float(tech_score) if tech_score is not None else None,
        "fundamental": float(fund_score) if fund_score is not None else None,
        "backtest": backtest_score,
        "risk_reward": _clip(35 + min(float(rr), 3) / 3 * 55) if rr is not None else None,
        "liquidity": liquidity_score,
    }
    weights = {"technical": .35, "fundamental": .25, "backtest": .20,
               "risk_reward": .12, "liquidity": .08}
    present = {k: v for k, v in components.items() if v is not None}
    denominator = sum(weights[k] for k in present)
    # v4 does not blend business quality and short-horizon timing into one
    # number.  Retain components for display while the legacy final score is
    # deliberately unavailable.
    final_score = None
    coverage_pct = denominator * 100

    dq = data_quality
    liquidity_pass = (liquidity or {}).get("avg_value") is not None and liquidity["avg_value"] >= 1_000_000_000
    gates = [
        GateResult("data_quality", bool(dq and dq.usable),
                   "fresh, non-quarantined data with at least 70% mandatory coverage"),
        GateResult("fundamental_source", bool(fund.get("authoritative_source")),
                   "official or licensed point-in-time fundamentals required"),
        GateResult("cost_profile", bool(backtest and backtest.get("costs_configured")),
                   "configured commissions, levies, spread and slippage required"),
        GateResult("liquidity", liquidity_pass, "average traded value must be at least IDR 1bn"),
        GateResult("validation", model_validated, "untouched holdout and causality suite must pass"),
        GateResult("shadow_release", shadow_sessions >= 60,
                   f"60 completed shadow sessions required; observed {shadow_sessions}"),
        GateResult("action_policy", False,
                   "live action eligibility is not supported by the current research policy"),
    ]
    failed = [g for g in gates if g.mandatory and not g.passed]
    if dq is None or dq.quarantined or not dq.fresh:
        label = DecisionLabel.WAIT_FOR_DATA
    elif failed:
        label = DecisionLabel.RESEARCH_ONLY
    else:
        # v4 is a research system. Preserve evidence labels without exposing a
        # code path that can be enabled into a trading action by configuration.
        label = DecisionLabel.RESEARCH_ONLY

    warnings = [f"Gate failed — {g.name}: {g.reason}" for g in failed]
    warnings.extend(fund.get("risk_flags", []))
    if rr is None or rr < 1:
        warnings.append("Risk/reward is unavailable or below 1.0R.")
    if backtest and backtest.get("research_only"):
        warnings.append("Backtest is gross research output; net evidence is unavailable without broker costs.")

    strongest = max(present, key=present.get) if present else None
    primary = (
        f"Separate business and setup evidence. Strongest available section: "
        f"{strongest.replace('_', ' ')} ({present[strongest]:.0f}/100)."
        if strongest else "No sufficient evidence sections are available."
    )
    entry = tech.get("entry_zone", ("N/A", "N/A"))
    return {
        "final_score": final_score,
        "final_verdict": label.value,
        "action": None,
        "evidence_label": _evidence_description(final_score),
        "decision_components": components,
        "coverage_pct": coverage_pct,
        "primary_reason": primary,
        "warnings": list(dict.fromkeys(warnings)),
        "gates": [g.__dict__ for g in gates],
        "formula_version": "decision-gates-v2",
        "validation_run_id": validation_run_id,
        "action_policy_enabled": False,
        "action_plan": {
            "entry_zone": f"{entry[0]} - {entry[1]}" if entry else "N/A",
            "stop_loss": _fmt_price(tech.get("stop_loss")),
            "take_profit": _fmt_price(tech.get("take_profit")),
            "risk_reward": f"{rr:.2f}R" if rr is not None else "N/A",
            "profile": tech.get("profile_label", "N/A"),
            "horizon": tech.get("horizon", "N/A"),
        },
    }
