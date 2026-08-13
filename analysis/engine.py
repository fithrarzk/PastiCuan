"""Single orchestration path for Streamlit, Telegram, scanners and reports."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from analysis.backtest import BrokerCostProfile, backtest_technical_strategy
from analysis.contracts import AnalysisBundle, GateResult
from analysis.decision import build_decision_report
from analysis.fundamental import analyze_fundamental
from analysis.quant import compute_quant_factors
from analysis.seasonality import compute_seasonality
from analysis.technical import analyze_technical
from analysis.valuation_bands import compute_valuation_bands
from data.validation import completed_eod_history, split_adjusted_ohlcv, validate_ohlcv


def _liquidity(history: pd.DataFrame) -> dict[str, float | None]:
    if history is None or history.empty or not {"Close", "Volume"}.issubset(history.columns):
        return {"avg_volume": None, "avg_value": None, "window": "60 completed sessions"}
    window = history.tail(60)
    return {
        "avg_volume": float(window["Volume"].mean()),
        "avg_value": float((window["Close"] * window["Volume"]).mean()),
        "window": f"{len(window)} completed sessions",
        "formula_version": "liquidity-v2",
    }


def broker_costs_from_env() -> BrokerCostProfile | None:
    names = ["BROKER_BUY_COMMISSION", "BROKER_SELL_COMMISSION", "BROKER_SELL_LEVY",
             "BROKER_HALF_SPREAD", "BROKER_SLIPPAGE_BPS"]
    if not all(os.getenv(name) not in (None, "") for name in names):
        return None
    return BrokerCostProfile(
        name=os.getenv("BROKER_COST_PROFILE", "configured"),
        buy_commission=float(os.environ[names[0]]),
        sell_commission=float(os.environ[names[1]]),
        sell_tax_levy=float(os.environ[names[2]]),
        half_spread=float(os.environ[names[3]]),
        slippage_bps=float(os.environ[names[4]]),
        max_volume_participation=float(os.getenv("BROKER_MAX_VOLUME_PARTICIPATION", "0.05")),
    )


def run_analysis_bundle(
    data: dict[str, Any],
    *,
    broker_costs: BrokerCostProfile | None = None,
    include_backtest: bool = True,
) -> dict[str, Any]:
    """Build one immutable-output contract and compatibility section objects."""
    raw_history = data.get("history")
    history = completed_eod_history(raw_history)
    indicator_history = split_adjusted_ohlcv(history)
    quality = validate_ohlcv(history)
    ticker = data.get("ticker", "UNKNOWN")
    info = data.get("info") or {}
    sector = (data.get("basic") or {}).get("sector", "N/A")

    tech = analyze_technical(indicator_history, sector=sector, info=info)
    fund = analyze_fundamental(
        info, sector, quarterly_income=data.get("quarterly_income"),
        quarterly_balance=data.get("quarterly_balance"),
    )
    # Yahoo is permitted only as a visibly flagged market fallback. The
    # compatibility loader cannot establish filing publication timestamps.
    source_meta = data.get("fundamental_source") or {}
    source_class = source_meta.get("source_class", "yahoo_fallback")
    fund["source"] = source_meta.get("provider", "Yahoo fallback")
    fund["source_url"] = source_meta.get("source_url")
    fund["authoritative_source"] = source_class in {"official", "licensed"}
    fund["publication_timestamp"] = source_meta.get("published_at")
    quant = compute_quant_factors(
        info, history, sector, data.get("quarterly_income"), data.get("quarterly_balance")
    )
    bands = compute_valuation_bands(
        history, data.get("quarterly_income"), data.get("quarterly_balance"), info
    )
    seasonality = compute_seasonality(history)
    costs = broker_costs if broker_costs is not None else broker_costs_from_env()
    backtest = (
        backtest_technical_strategy(history, sector=sector, info=info, broker_costs=costs)
        if include_backtest else {
            "error": "Backtest skipped for the low-latency request path.",
            "summary": {}, "signal_stats": {}, "setup_confidence": None,
            "costs_configured": costs is not None, "research_only": True,
            "formula_version": "causal-backtest-v2", "trades": pd.DataFrame(),
            "equity_curve": pd.DataFrame(),
        }
    )
    liquidity = _liquidity(history)
    validated = os.getenv("MODEL_VALIDATED", "false").lower() == "true"
    shadow_sessions = int(os.getenv("SHADOW_COMPLETED_SESSIONS", "0"))
    decision = build_decision_report(
        tech, fund, bands=bands, seasonality=seasonality, backtest=backtest,
        liquidity=liquidity, data_quality=quality, model_validated=validated,
        shadow_sessions=shadow_sessions,
    )
    fund["decision_label"] = decision["final_verdict"]
    gates = [GateResult(**gate) for gate in decision["gates"]]
    as_of = quality.price_timestamp or pd.Timestamp.now(tz="Asia/Jakarta").isoformat()
    bundle = AnalysisBundle(
        ticker=ticker, as_of=as_of, horizon=tech.get("horizon", "EOD"),
        data_quality=quality, fundamental=fund,
        technical={k: v for k, v in tech.items() if k != "df"},
        quant=quant, backtest={k: v for k, v in backtest.items() if k not in {"trades", "equity_curve"}},
        decision=decision, gates=gates, warnings=decision["warnings"], action=decision["action"],
    )
    return {
        "bundle": bundle, "tech": tech, "fund": fund, "quant": quant,
        "bands": bands, "seasonality": seasonality, "backtest": backtest,
        "liquidity": liquidity, "decision": decision,
    }
