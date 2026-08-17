"""Forward signal telemetry; this is observation, not a trading backtest."""

from __future__ import annotations

import math


ADJUSTMENT_VERSION = "stored-canonical-close-v1"


def evaluate_signal_window(signal: dict, horizon: int) -> dict | None:
    """Evaluate a signal after exactly ``horizon`` subsequent stored sessions.

    The first subsequent close is the reference. Corporate-action adjustment is
    expected to have happened in the canonical price series before this stage.
    """
    if horizon not in {5, 20, 60, 252}:
        raise ValueError("Unsupported signal horizon.")
    prices = []
    for row in signal.get("prices") or []:
        try:
            value = float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            prices.append({"session_date": str(row["session_date"]), "close": value})
    if len(prices) < horizon:
        return None
    window = prices[:horizon]
    reference = window[0]["close"]
    returns = [row["close"] / reference - 1 for row in window]
    return {
        "snapshot_id": signal["snapshot_id"],
        "issuer_id": signal["issuer_id"],
        "horizon_sessions": horizon,
        "evaluated_session": window[-1]["session_date"],
        "absolute_return": returns[-1],
        "benchmark_return": None,
        "excess_return": None,
        "maximum_favorable_excursion": max(returns),
        "maximum_adverse_excursion": min(returns),
        "status": "AVAILABLE",
        "adjustment_version": ADJUSTMENT_VERSION,
        "evidence": {
            "reference_session": window[0]["session_date"],
            "reference_close": reference,
            "business_state": signal.get("business_state"),
            "entry_state": signal.get("entry_state"),
            "business_score": signal.get("business_score"),
            "benchmark_status": "UNAVAILABLE",
        },
    }
