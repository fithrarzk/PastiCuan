"""Final decision engine combining technical, fundamental, and risk evidence."""

from __future__ import annotations

import pandas as pd


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(max(low, min(high, value)))


def _fmt_price(value) -> str:
    return "N/A" if value is None or pd.isna(value) else f"Rp {value:,.0f}"


def _score_from_backtest(backtest: dict | None) -> float:
    if not backtest or backtest.get("error"):
        return 50.0
    summary = backtest.get("summary", {})
    if summary.get("total_trades", 0) < 3:
        return 48.0
    score = 50.0
    score += (summary.get("win_rate", 0) - 50) * 0.45
    score += summary.get("average_return", 0) * 2.2
    pf = summary.get("profit_factor", 0)
    score += 18 if pf == float("inf") else max(-18, min(18, (pf - 1) * 22))
    score += max(-12, min(8, summary.get("max_drawdown", 0) * 0.35))
    return _clip(score)


def _score_from_bands(bands: dict | None) -> float:
    if not bands:
        return 50.0
    positions = []
    for key in ("pe", "pbv"):
        band = bands.get(key)
        if band and band.get("sd_position") is not None:
            positions.append(float(band["sd_position"]))
    if not positions:
        return 50.0
    avg_sd = sum(positions) / len(positions)
    return _clip(55 - avg_sd * 12)


def _score_from_seasonality(seasonality: dict | None) -> float:
    if not seasonality:
        return 50.0
    try:
        month = pd.Timestamp.today().month
        avg = seasonality.get("monthly_avg").get(month)
        win = seasonality.get("monthly_pos_pct").get(month)
    except Exception:
        return 50.0
    if avg is None or win is None or pd.isna(avg) or pd.isna(win):
        return 50.0
    return _clip(50 + float(avg) * 2 + (float(win) - 50) * 0.3)


def _score_from_risk_reward(tech: dict) -> float:
    rr = tech.get("risk_reward")
    if rr is None or pd.isna(rr):
        return 45.0
    return _clip(35 + min(float(rr), 3.0) / 3.0 * 55)


def _score_from_liquidity(liquidity: dict | None) -> float:
    if not liquidity:
        return 50.0
    avg_value = liquidity.get("avg_value")
    if avg_value is None:
        return 50.0
    if avg_value >= 25_000_000_000:
        return 90.0
    if avg_value >= 10_000_000_000:
        return 78.0
    if avg_value >= 3_000_000_000:
        return 62.0
    if avg_value >= 1_000_000_000:
        return 48.0
    return 30.0


def _verdict(score: float, warnings: list[str], technical_score: float | None, rr) -> str:
    severe = any("low liquidity" in warning.lower() for warning in warnings)
    if severe and score >= 58:
        return "Speculative Only"
    if rr is not None and rr < 0.8:
        return "Wait"
    if technical_score is not None and technical_score < 35:
        return "Avoid"
    if score >= 75:
        return "Strong Buy"
    if score >= 63:
        return "Buy on Weakness"
    if score >= 52:
        return "Hold"
    if score >= 42:
        return "Wait"
    return "Avoid"


def build_decision_report(
    tech: dict,
    fund: dict,
    bands: dict | None = None,
    seasonality: dict | None = None,
    backtest: dict | None = None,
    liquidity: dict | None = None,
) -> dict:
    """Blend all available evidence into a single explainable decision."""
    technical_score = tech.get("technical_score")
    fundamental_score = fund.get("fundamental_score")
    components = {
        "technical": float(technical_score) if technical_score is not None else 50.0,
        "fundamental": float(fundamental_score) if fundamental_score is not None else 50.0,
        "backtest": _score_from_backtest(backtest),
        "risk_reward": _score_from_risk_reward(tech),
        "valuation_bands": _score_from_bands(bands),
        "seasonality": _score_from_seasonality(seasonality),
        "liquidity": _score_from_liquidity(liquidity),
    }
    weights = {
        "technical": 0.30,
        "fundamental": 0.22,
        "backtest": 0.18,
        "risk_reward": 0.12,
        "valuation_bands": 0.07,
        "seasonality": 0.04,
        "liquidity": 0.07,
    }
    final_score = sum(components[key] * weights[key] for key in weights)

    warnings = []
    rr = tech.get("risk_reward")
    if rr is None or rr < 1.0:
        warnings.append("Risk/reward is below the preferred 1.0R threshold.")
    if liquidity and liquidity.get("avg_value") is not None and liquidity["avg_value"] < 1_000_000_000:
        warnings.append("Low liquidity: execution risk may be high.")
    if backtest and not backtest.get("error"):
        summary = backtest.get("summary", {})
        if summary.get("total_trades", 0) < 3:
            warnings.append("Backtest sample is small; treat historical confidence carefully.")
        elif summary.get("expectancy", 0) <= 0:
            warnings.append("Backtest expectancy is not positive.")
    for flag in fund.get("risk_flags", []):
        warnings.append(flag)

    final_verdict = _verdict(final_score, warnings, technical_score, rr)
    sorted_components = sorted(components.items(), key=lambda item: item[1], reverse=True)
    strongest = sorted_components[0]
    weakest = sorted_components[-1]
    primary_reason = (
        f"Strongest evidence is {strongest[0].replace('_', ' ')} ({strongest[1]:.0f}/100); "
        f"main drag is {weakest[0].replace('_', ' ')} ({weakest[1]:.0f}/100)."
    )

    entry_zone = tech.get("entry_zone", ("N/A", "N/A"))
    action_plan = {
        "entry_zone": f"{entry_zone[0]} - {entry_zone[1]}" if entry_zone else "N/A",
        "stop_loss": _fmt_price(tech.get("stop_loss")),
        "take_profit": _fmt_price(tech.get("take_profit")),
        "risk_reward": f"{rr:.2f}R" if rr is not None else "N/A",
        "profile": tech.get("profile_label", "N/A"),
        "horizon": tech.get("horizon", "N/A"),
    }

    return {
        "final_score": _clip(final_score),
        "final_verdict": final_verdict,
        "decision_components": components,
        "primary_reason": primary_reason,
        "warnings": warnings,
        "action_plan": action_plan,
    }
