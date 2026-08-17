"""Causal monthly cross-sectional quant portfolio validation."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from analysis.backtest import BrokerCostProfile


def _drawdown(returns: pd.Series) -> float:
    equity = (1 + returns.fillna(0)).cumprod()
    return float((equity / equity.cummax() - 1).min()) if not equity.empty else 0.0


def _performance(returns: pd.Series) -> dict:
    returns = returns.dropna()
    if returns.empty:
        return {"months": 0, "cagr": None, "volatility": None, "sharpe": None,
                "sortino": None, "max_drawdown": None, "total_return": None}
    years = max(len(returns) / 12, 1 / 12)
    total = float((1 + returns).prod() - 1)
    cagr = float((1 + total) ** (1 / years) - 1) if total > -1 else -1.0
    vol = float(returns.std(ddof=1) * math.sqrt(12)) if len(returns) > 1 else None
    downside = returns[returns < 0]
    downside_dev = float(np.sqrt((downside**2).mean()) * math.sqrt(12)) if len(downside) else None
    return {
        "months": int(len(returns)), "cagr": cagr,
        "volatility": vol,
        "sharpe": float(returns.mean() * 12 / vol) if vol else None,
        "sortino": float(returns.mean() * 12 / downside_dev) if downside_dev else None,
        "max_drawdown": _drawdown(returns), "total_return": total,
    }


def _monthly_forward_returns(bars: pd.DataFrame, rebalance_dates: list[pd.Timestamp], delay_sessions: int = 0) -> pd.DataFrame:
    required = {"date", "ticker", "open"}
    if bars is None or bars.empty or not required.issubset(bars.columns):
        return pd.DataFrame()
    frame = bars.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    frame["ticker"] = frame["ticker"].str.upper().str.replace(".JK", "", regex=False)
    frame["open"] = pd.to_numeric(frame["open"], errors="coerce")
    rows = []
    dates = sorted(pd.Timestamp(value).tz_localize(None) if pd.Timestamp(value).tzinfo else pd.Timestamp(value) for value in rebalance_dates)
    for start, end in zip(dates[:-1], dates[1:]):
        window = frame[(frame["date"] > start) & (frame["date"] <= end)].sort_values("date")
        after = frame[frame["date"] > end].sort_values("date")
        for ticker, group in window.groupby("ticker"):
            entries = group[group["open"] > 0]
            exits = after[(after["ticker"] == ticker) & (after["open"] > 0)]
            if len(entries) <= delay_sessions or len(exits) <= delay_sessions:
                continue
            entry_row = entries.iloc[delay_sessions]
            exit_row = exits.iloc[delay_sessions]
            rows.append({
                "rebalance_date": start, "ticker": ticker,
                "entry_date": entry_row["date"], "exit_date": exit_row["date"],
                "gross_return": float(exit_row["open"] / entry_row["open"] - 1),
            })
    return pd.DataFrame(rows)


def backtest_monthly_quant(
    scores: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    broker_costs: BrokerCostProfile,
    top_fraction: float = 0.20,
    execution_delay_sessions: int = 0,
) -> dict:
    """Test ranks known at month end using the next tradable opens."""
    broker_costs.validate()
    required = {"rebalance_date", "ticker", "composite_percentile"}
    if scores is None or scores.empty or not required.issubset(scores.columns):
        return {"status": "INSUFFICIENT_DATA", "reason": "Monthly score panel is missing."}
    panel = scores.copy()
    panel["rebalance_date"] = pd.to_datetime(panel["rebalance_date"]).dt.tz_localize(None)
    panel["ticker"] = panel["ticker"].str.upper().str.replace(".JK", "", regex=False)
    panel["composite_percentile"] = pd.to_numeric(panel["composite_percentile"], errors="coerce")
    panel = panel.dropna(subset=["composite_percentile"])
    dates = sorted(panel["rebalance_date"].unique())
    if len(dates) < 3:
        return {"status": "INSUFFICIENT_DATA", "reason": "At least three monthly ranks are required."}
    forwards = _monthly_forward_returns(bars, list(dates), execution_delay_sessions)
    merged = panel.merge(forwards, on=["rebalance_date", "ticker"], how="inner")
    if merged.empty:
        return {"status": "INSUFFICIENT_DATA", "reason": "No causal next-open returns could be formed."}

    round_trip = (broker_costs.buy_commission + broker_costs.sell_commission +
                  broker_costs.sell_tax_levy + 2 * broker_costs.half_spread +
                  2 * broker_costs.slippage_bps / 10_000)
    merged["net_return"] = (1 + merged["gross_return"]) * (1 - round_trip) - 1
    portfolio_rows, ic_rows = [], []
    for when, group in merged.groupby("rebalance_date"):
        cutoff = group["composite_percentile"].quantile(1 - top_fraction)
        selected = group[group["composite_percentile"] >= cutoff]
        if selected.empty:
            continue
        portfolio_rows.append({
            "rebalance_date": when,
            "strategy_return": float(selected["net_return"].mean()),
            "benchmark_return": float(group["net_return"].mean()),
            "positions": int(len(selected)), "eligible": int(len(group)),
        })
        ic = group["composite_percentile"].corr(group["gross_return"], method="spearman")
        if pd.notna(ic):
            ic_rows.append({"rebalance_date": when, "ic": float(ic)})
    monthly = pd.DataFrame(portfolio_rows).set_index("rebalance_date").sort_index()
    if monthly.empty:
        return {"status": "INSUFFICIENT_DATA", "reason": "No monthly portfolio was formed."}
    monthly["excess_return"] = monthly["strategy_return"] - monthly["benchmark_return"]
    strategy = _performance(monthly["strategy_return"])
    benchmark = _performance(monthly["benchmark_return"])
    excess = monthly["excess_return"]
    tracking_error = float(excess.std(ddof=1) * math.sqrt(12)) if len(excess) > 1 else None
    information_ratio = float(excess.mean() * 12 / tracking_error) if tracking_error else None
    ic_frame = pd.DataFrame(ic_rows)
    return {
        "status": "AVAILABLE", "monthly": monthly, "observations": merged,
        "strategy": strategy, "benchmark": benchmark,
        "net_excess_cagr": (strategy["cagr"] - benchmark["cagr"]
                            if strategy["cagr"] is not None and benchmark["cagr"] is not None else None),
        "information_ratio": information_ratio,
        "average_rank_ic": float(ic_frame["ic"].mean()) if not ic_frame.empty else None,
        "rank_ic_months": ic_frame["ic"].tolist() if not ic_frame.empty else [],
        "median_eligible_universe": float(monthly["eligible"].median()),
        "cost_rate_round_trip": round_trip,
        "formula_version": "monthly-lq45-next-open-v1",
    }


def assess_holdout(metrics: dict, *, usable_years: float, holdout_months: int,
                   higher_cost_positive: bool, delayed_entry_positive: bool,
                   deterministic_rebuild: bool) -> dict:
    """Frozen VALIDATED_RESEARCH acceptance policy."""
    ic_values = np.asarray(metrics.get("rank_ic_months") or [], dtype=float)
    if len(ic_values):
        rng = np.random.default_rng(20260818)
        bootstrap = rng.choice(ic_values, size=(2000, len(ic_values)), replace=True).mean(axis=1)
        ic_probability_positive = float((bootstrap > 0).mean())
    else:
        ic_probability_positive = 0.0
    strategy_dd = ((metrics.get("strategy") or {}).get("max_drawdown"))
    benchmark_dd = ((metrics.get("benchmark") or {}).get("max_drawdown"))
    drawdown_pass = (
        strategy_dd is not None and benchmark_dd is not None
        and float(strategy_dd) >= float(benchmark_dd) - .05
    )
    checks = {
        "history_years": usable_years >= 5,
        "holdout_months": holdout_months >= 24,
        "net_excess_return": (metrics.get("net_excess_cagr") or 0) > 0,
        "average_rank_ic": (metrics.get("average_rank_ic") or 0) > 0,
        "rank_ic_confidence": ic_probability_positive >= .90,
        "eligible_universe": (metrics.get("median_eligible_universe") or 0) >= 36,
        "information_ratio": (metrics.get("information_ratio") or 0) >= 0.30,
        "drawdown": drawdown_pass,
        "higher_cost": bool(higher_cost_positive),
        "delayed_entry": bool(delayed_entry_positive),
        "deterministic_rebuild": bool(deterministic_rebuild),
    }
    return {"passed": all(checks.values()), "checks": checks,
            "rank_ic_probability_positive": ic_probability_positive,
            "policy_version": "validated-research-v2"}
