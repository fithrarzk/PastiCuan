"""Quality-first, point-in-time LQ45 business scoring.

Technical values deliberately do not enter this model.  It ranks available
business evidence; it does not estimate intrinsic value or management quality.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


FORMULA_VERSION = "lq45-business-quality-v1"
WEIGHTS = {"quality": .35, "valuation": .30, "durability": .20, "resilience": .15}
DEFINITIONS = {
    "quality": {"roe": 1, "cash_conversion": 1, "accrual_ratio": -1},
    "valuation": {"earnings_yield": 1, "book_yield": 1, "dividend_yield": 1},
    "durability": {"earnings_growth_3y": 1, "earnings_stability": -1},
    "resilience": {"net_debt_to_equity": -1, "cash_to_equity": 1, "equity_positive": 1},
}
MINIMUM_INPUTS = {"quality": 3, "valuation": 2, "durability": 2, "resilience": 2}


def _percentile(values: pd.Series, direction: int) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().sum() < 5:
        return pd.Series(np.nan, index=values.index)
    low, high = numeric.quantile([.05, .95])
    ranked = numeric.clip(low, high).rank(pct=True, method="average") * 100
    return ranked if direction > 0 else 100 - ranked


def compute_business_scores(universe: pd.DataFrame) -> dict:
    required = {"ticker", "sector"}
    if universe is None or universe.empty or not required.issubset(universe.columns):
        return {"status": "INSUFFICIENT_DATA", "reason": "Business-score universe is missing.",
                "scores": pd.DataFrame(), "formula_version": FORMULA_VERSION}
    frame = universe.copy()
    unsupported = frame.get("issuer_profile", pd.Series("GENERAL", index=frame.index)).astype(str).str.upper().ne("GENERAL")
    raw_columns = [column for group in DEFINITIONS.values() for column in group]
    raw = pd.DataFrame({column: pd.to_numeric(frame.get(column), errors="coerce")
                        for column in raw_columns}, index=frame.index)
    frame["raw_fundamental_coverage_pct"] = raw.notna().mean(axis=1) * 100
    valid_component = pd.DataFrame(index=frame.index)
    for component, definitions in DEFINITIONS.items():
        ranked = pd.DataFrame({column: _percentile(raw[column], direction)
                               for column, direction in definitions.items()}, index=frame.index)
        score = ranked.mean(axis=1, skipna=True)
        frame[f"{component}_input_count"] = raw[list(definitions)].notna().sum(axis=1)
        valid = frame[f"{component}_input_count"] >= MINIMUM_INPUTS[component]
        frame[f"{component}_score"] = score.where(valid)
        valid_component[component] = valid
    component_columns = [f"{name}_score" for name in WEIGHTS]
    complete = frame[component_columns].notna().all(axis=1) & (frame["raw_fundamental_coverage_pct"] >= 80) & ~unsupported
    frame["business_score"] = sum(frame[f"{name}_score"] * weight for name, weight in WEIGHTS.items()).where(complete)
    frame["business_state"] = "LIMITED_HISTORY"
    frame.loc[unsupported, "business_state"] = "UNSUPPORTED_PROFILE"
    frame.loc[complete & (frame["business_score"] < 60), "business_state"] = "WEAK_OR_EXPENSIVE"
    frame.loc[complete & frame["business_score"].between(60, 70, inclusive="left"), "business_state"] = "FAIR_BUSINESS"
    quality_candidate = (
        complete & (frame["business_score"] >= 70) & (frame["quality_score"] >= 65)
        & (frame["valuation_score"] >= 55) & (frame["resilience_score"] >= 60)
    )
    frame.loc[quality_candidate, "business_state"] = "QUALITY_CANDIDATE"
    frame["business_rank"] = frame["business_score"].rank(ascending=False, method="min")
    output = ["ticker", "business_score", "business_rank", "business_state",
              "raw_fundamental_coverage_pct", *component_columns]
    return {"status": "AVAILABLE", "scores": frame[output], "formula_version": FORMULA_VERSION,
            "weights": WEIGHTS, "minimum_inputs": MINIMUM_INPUTS}
