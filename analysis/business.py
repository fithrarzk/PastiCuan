"""Profile-aware, point-in-time LQ45 business scoring.

Technical values deliberately do not enter this model.  General issuers and
banks are never compared with the wrong accounting model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


FORMULA_VERSION = "lq45-business-quality-v2"
GENERAL_WEIGHTS = {"quality": .35, "valuation": .30, "durability": .20, "resilience": .15}
GENERAL_DEFINITIONS = {
    "quality": {"roe": 1, "cash_conversion": 1, "accrual_ratio": -1},
    "valuation": {"earnings_yield": 1, "book_yield": 1, "dividend_yield": 1},
    "durability": {"earnings_growth_3y": 1, "earnings_stability": -1},
    "resilience": {"net_debt_to_equity": -1, "cash_to_equity": 1, "equity_positive": 1},
}
GENERAL_MINIMUM_INPUTS = {"quality": 3, "valuation": 2, "durability": 2, "resilience": 2}

BANK_WEIGHTS = {
    "bank_profitability": .30, "bank_asset_quality": .25,
    "bank_capital": .20, "bank_funding": .10, "bank_valuation": .15,
}
BANK_DEFINITIONS = {
    "bank_profitability": {"roe": 1, "roa": 1, "earnings_stability": -1},
    "bank_asset_quality": {"npl_ratio": -1, "credit_cost": -1, "allowance_coverage": 1},
    "bank_capital": {"capital_adequacy_ratio": 1, "equity_to_assets": 1},
    "bank_funding": {"loans_to_deposits": -1, "liquid_assets_to_deposits": 1},
    "bank_valuation": {"earnings_yield": 1, "book_yield": 1},
}
BANK_MINIMUM_INPUTS = {
    "bank_profitability": 2, "bank_asset_quality": 2,
    "bank_capital": 1, "bank_funding": 1, "bank_valuation": 2,
}

# Backwards-compatible public aliases used by reporting code.
WEIGHTS = GENERAL_WEIGHTS
DEFINITIONS = GENERAL_DEFINITIONS
MINIMUM_INPUTS = GENERAL_MINIMUM_INPUTS


def _percentile(values: pd.Series, direction: int) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().sum() < 5:
        return pd.Series(np.nan, index=values.index)
    low, high = numeric.quantile([.05, .95])
    ranked = numeric.clip(low, high).rank(pct=True, method="average") * 100
    return ranked if direction > 0 else 100 - ranked


def _score_profile(frame: pd.DataFrame, mask: pd.Series, definitions: dict,
                   weights: dict, minimum_inputs: dict) -> pd.Series:
    complete = pd.Series(False, index=frame.index)
    if not mask.any():
        return complete
    cohort = frame.loc[mask]
    for component, fields in definitions.items():
        raw = pd.DataFrame({field: pd.to_numeric(cohort.get(field), errors="coerce")
                            for field in fields}, index=cohort.index)
        ranked = pd.DataFrame({field: _percentile(raw[field], direction)
                               for field, direction in fields.items()}, index=cohort.index)
        input_count = raw.notna().sum(axis=1)
        valid = input_count >= minimum_inputs[component]
        frame.loc[cohort.index, f"{component}_input_count"] = input_count
        frame.loc[cohort.index, f"{component}_score"] = ranked.mean(axis=1).where(valid)
    component_columns = [f"{name}_score" for name in weights]
    complete.loc[cohort.index] = frame.loc[cohort.index, component_columns].notna().all(axis=1)
    complete &= frame["raw_fundamental_coverage_pct"] >= 80
    frame.loc[complete, "business_score"] = sum(
        frame.loc[complete, f"{name}_score"] * weight for name, weight in weights.items()
    )
    return complete


def compute_business_scores(universe: pd.DataFrame) -> dict:
    required = {"ticker", "sector"}
    if universe is None or universe.empty or not required.issubset(universe.columns):
        return {"status": "INSUFFICIENT_DATA", "reason": "Business-score universe is missing.",
                "scores": pd.DataFrame(), "formula_version": FORMULA_VERSION}
    frame = universe.copy()
    profile = frame.get("issuer_profile", pd.Series("GENERAL", index=frame.index)).astype(str).str.upper()
    profile = profile.replace({"FINANCIAL": "BANK", "GENERAL_COMPANY": "GENERAL", "": "UNVERIFIED"})
    frame["issuer_profile"] = profile
    frame["business_model"] = profile.map({"GENERAL": "GENERAL_V2", "BANK": "BANK_V1_SHADOW"}).fillna("NONE")

    general_fields = {field for group in GENERAL_DEFINITIONS.values() for field in group}
    bank_fields = {field for group in BANK_DEFINITIONS.values() for field in group}
    frame["raw_fundamental_coverage_pct"] = 0.0
    for value, fields in (("GENERAL", general_fields), ("BANK", bank_fields)):
        mask = profile.eq(value)
        if mask.any():
            raw = pd.DataFrame({field: pd.to_numeric(frame.loc[mask].get(field), errors="coerce")
                                for field in fields}, index=frame.index[mask])
            frame.loc[mask, "raw_fundamental_coverage_pct"] = raw.notna().mean(axis=1) * 100

    frame["business_score"] = np.nan
    general_complete = _score_profile(frame, profile.eq("GENERAL"), GENERAL_DEFINITIONS,
                                      GENERAL_WEIGHTS, GENERAL_MINIMUM_INPUTS)
    bank_complete = _score_profile(frame, profile.eq("BANK"), BANK_DEFINITIONS,
                                   BANK_WEIGHTS, BANK_MINIMUM_INPUTS)
    complete = general_complete | bank_complete
    frame["business_state"] = "LIMITED_HISTORY"
    frame.loc[~profile.isin({"GENERAL", "BANK"}), "business_state"] = "PROFILE_UNVERIFIED"
    frame.loc[complete & (frame["business_score"] < 60), "business_state"] = "WEAK_OR_EXPENSIVE"
    frame.loc[complete & frame["business_score"].between(60, 70, inclusive="left"), "business_state"] = "FAIR_BUSINESS"

    general_quality = frame.get("quality_score", pd.Series(np.nan, index=frame.index))
    general_value = frame.get("valuation_score", pd.Series(np.nan, index=frame.index))
    general_resilience = frame.get("resilience_score", pd.Series(np.nan, index=frame.index))
    bank_profitability = frame.get("bank_profitability_score", pd.Series(np.nan, index=frame.index))
    bank_value = frame.get("bank_valuation_score", pd.Series(np.nan, index=frame.index))
    bank_capital = frame.get("bank_capital_score", pd.Series(np.nan, index=frame.index))
    quality_candidate = complete & (frame["business_score"] >= 70) & (
        (profile.eq("GENERAL") & (general_quality >= 65) & (general_value >= 55) & (general_resilience >= 60))
        | (profile.eq("BANK") & (bank_profitability >= 60) & (bank_value >= 55) & (bank_capital >= 55))
    )
    frame.loc[quality_candidate, "business_state"] = "QUALITY_CANDIDATE"
    frame["business_rank"] = frame["business_score"].rank(ascending=False, method="min")

    component_columns = [f"{name}_score" for name in (*GENERAL_WEIGHTS, *BANK_WEIGHTS)]
    for column in component_columns:
        if column not in frame:
            frame[column] = np.nan
    history_source = frame.get("annual_history_years", pd.Series(0, index=frame.index))
    history = pd.to_numeric(history_source, errors="coerce").fillna(0).astype(int)
    frame["annual_history_years"] = history
    frame["history_confidence"] = history.map(lambda value: "FULL" if value >= 5 else ("PARTIAL" if value >= 3 else "LIMITED"))
    output = ["ticker", "issuer_profile", "business_model", "annual_history_years", "history_confidence",
              "business_score", "business_rank", "business_state", "raw_fundamental_coverage_pct",
              *component_columns]
    return {"status": "AVAILABLE", "scores": frame[output], "formula_version": FORMULA_VERSION,
            "weights": {"GENERAL": GENERAL_WEIGHTS, "BANK": BANK_WEIGHTS},
            "minimum_inputs": {"GENERAL": GENERAL_MINIMUM_INPUTS, "BANK": BANK_MINIMUM_INPUTS}}
