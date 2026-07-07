"""Risk management helpers for position sizing."""


def calculate_position_size(
    entry,
    stop_loss,
    capital,
    risk_pct,
    lot_size: int = 100,
) -> dict:
    """Calculate IDX lot sizing from entry, stop loss, and risk budget."""
    try:
        entry = float(entry)
        stop_loss = float(stop_loss)
        capital = float(capital)
        risk_pct = float(risk_pct)
    except (TypeError, ValueError):
        return {
            "error": "Entry, stop loss, capital, and risk percent must be numeric.",
            "shares": 0,
            "lots": 0,
        }

    if lot_size <= 0:
        lot_size = 100
    if entry <= 0 or stop_loss <= 0 or capital <= 0 or risk_pct <= 0:
        return {
            "error": "Inputs must be greater than zero.",
            "shares": 0,
            "lots": 0,
        }

    risk_per_share = entry - stop_loss
    if risk_per_share <= 0:
        return {
            "error": "Stop loss must be below entry for a long position.",
            "shares": 0,
            "lots": 0,
        }

    max_loss = capital * risk_pct
    raw_shares = int(max_loss // risk_per_share)
    lots = raw_shares // lot_size
    shares = lots * lot_size
    position_value = shares * entry
    actual_risk = shares * risk_per_share

    return {
        "error": None,
        "shares": shares,
        "lots": lots,
        "position_value": position_value,
        "max_loss": max_loss,
        "actual_risk": actual_risk,
        "actual_risk_pct": actual_risk / capital * 100 if capital else None,
        "risk_per_share": risk_per_share,
        "cash_remaining": capital - position_value,
    }
