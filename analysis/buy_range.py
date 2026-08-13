"""Auditable technical/fundamental price-range research.

This module produces price references, never an order recommendation.  A
preferred range exists only when the technical accumulation zone overlaps the
historical valuation reference.  Missing inputs stay missing.
"""

from __future__ import annotations

from math import isfinite
from statistics import median
from typing import Any


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) and result > 0 else None


def _last_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        value = value.dropna().iloc[-1]
    except AttributeError:
        try:
            value = value[-1]
        except (IndexError, KeyError, TypeError):
            pass
    return _number(value)


def _price_range(low: float | None, high: float | None) -> dict[str, float] | None:
    if low is None or high is None or low > high:
        return None
    return {"low": round(low, 2), "high": round(high, 2)}


def build_buy_range(
    tech: dict,
    fund: dict,
    bands: dict | None,
    *,
    data_usable: bool,
) -> dict:
    """Combine independently calculated technical and valuation references.

    Fundamental references use the latest -1 SD to historical-mean price from
    each meaningful PE/PBV model.  The median combines models without allowing
    one extreme model to dominate.  These are historical valuation references,
    not intrinsic-value estimates.
    """
    current = _number(tech.get("current_price"))
    support = _number(tech.get("support"))
    atr = _number(tech.get("atr"))
    technical = None
    if support is not None and current is not None:
        technical_high = min(current, support + 0.8 * atr) if atr is not None else current
        technical = _price_range(support, technical_high)

    models = []
    for name, status_key in (("PE", "pe_status"), ("PBV", "pbv_status")):
        if fund.get(status_key) != "AVAILABLE":
            continue
        band = (bands or {}).get(name.lower()) or {}
        low = _last_number(band.get("band_m1"))
        fair = _last_number(band.get("band_mean"))
        model_range = _price_range(low, fair)
        if model_range:
            models.append({"model": name, **model_range})

    valuation = None
    if models:
        valuation = _price_range(
            median(model["low"] for model in models),
            median(model["high"] for model in models),
        )

    preferred = None
    if technical and valuation:
        preferred = _price_range(
            max(technical["low"], valuation["low"]),
            min(technical["high"], valuation["high"]),
        )

    authoritative = bool(fund.get("authoritative_source"))
    if not data_usable:
        status = "WAIT_FOR_DATA"
    elif technical is None or valuation is None:
        status = "INSUFFICIENT_DATA"
    elif preferred is None:
        status = "NO_OVERLAP"
    else:
        status = "RESEARCH_ONLY"

    warnings = []
    if not authoritative:
        warnings.append(
            "Fundamentals are from a non-authoritative fallback; the valuation range is indicative only."
        )
    if valuation is None:
        warnings.append("A meaningful PE/PBV historical valuation reference is unavailable.")
    if technical is None:
        warnings.append("Support/current-price history is insufficient for a technical range.")
    if technical and valuation and preferred is None:
        warnings.append("Technical and valuation ranges do not overlap; no preferred range is published.")
    if preferred:
        warnings.append("A price entering the range is not confirmation; trend and volume can still invalidate it.")

    return {
        "status": status,
        "policy_label": "RESEARCH_ONLY" if status not in {"WAIT_FOR_DATA", "INSUFFICIENT_DATA"} else status,
        "current_price": current,
        "technical_range": technical,
        "valuation_reference_range": valuation,
        "preferred_range": preferred,
        "valuation_models": models,
        "stop_loss": _number(tech.get("stop_loss")),
        "technical_target": _number(tech.get("take_profit")),
        "risk_reward": tech.get("risk_reward"),
        "technical_confirmation": bool(
            tech.get("technical_score") is not None
            and float(tech["technical_score"]) >= 50
            and tech.get("rsi") is not None
            and float(tech["rsi"]) > 50
        ),
        "source": fund.get("source", "Unknown"),
        "authoritative_fundamentals": authoritative,
        "formula_version": "buy-range-overlap-v1",
        "definition": (
            "Preferred range = overlap of support-to-support+0.8ATR and the median "
            "latest PE/PBV -1SD-to-historical-mean price references."
        ),
        "warnings": warnings,
    }
