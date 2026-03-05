# Sector-specific PE and PBV benchmarks calibrated for the IDX / Indonesian market.
# Format: { sector_keyword: { "pe": (low_max, high_min), "pbv": (low_max, high_min) } }
SECTOR_BENCHMARKS = {
    "financial services": {"pe": (8,  15),  "pbv": (1.0, 2.5)},
    "bank":               {"pe": (8,  15),  "pbv": (1.0, 2.5)},
    "technology":         {"pe": (20, 40),  "pbv": (3.0, 8.0)},
    "consumer defensive": {"pe": (12, 25),  "pbv": (2.0, 5.0)},
    "consumer staples":   {"pe": (12, 25),  "pbv": (2.0, 5.0)},
    "consumer cyclical":  {"pe": (10, 20),  "pbv": (1.5, 4.0)},
    "healthcare":         {"pe": (15, 30),  "pbv": (2.0, 5.0)},
    "energy":             {"pe": (8,  15),  "pbv": (1.0, 2.5)},
    "basic materials":    {"pe": (8,  15),  "pbv": (1.0, 2.5)},
    "industrials":        {"pe": (10, 20),  "pbv": (1.5, 3.0)},
    "utilities":          {"pe": (10, 18),  "pbv": (1.0, 2.0)},
    "real estate":        {"pe": (10, 20),  "pbv": (0.8, 1.5)},
    "communication":      {"pe": (12, 25),  "pbv": (2.0, 4.0)},
    "default":            {"pe": (10, 20),  "pbv": (1.5, 3.0)},
}


def _get_sector_benchmark(sector: str) -> tuple:
    """Return (benchmark_dict, matched_label) for a given sector string."""
    sector_lower = sector.lower()
    for key, bench in SECTOR_BENCHMARKS.items():
        if key != "default" and key in sector_lower:
            return bench, key.title()
    return SECTOR_BENCHMARKS["default"], "General / Default"


def _classify(value, low_max: float, high_min: float) -> str:
    """Classify a ratio value as Low / Fair / High relative to sector thresholds."""
    if value is None:
        return "N/A"
    if value < low_max:
        return "🟢 Low"
    if value > high_min:
        return "🔴 High"
    return "🟡 Fair"


def analyze_fundamental(info: dict, sector: str) -> dict:
    """
    Evaluates PE and PBV against sector-specific IDX benchmarks
    and returns a valuation verdict.

    Parameters
    ----------
    info   : raw yfinance .info dict
    sector : sector string from yfinance (e.g. 'Financial Services')

    Returns
    -------
    dict with pe/pbv labels, benchmark ranges, and an overall verdict string.
    """
    pe_val  = info.get("trailingPE")
    pbv_val = info.get("priceToBook")

    bench, matched_sector = _get_sector_benchmark(sector)
    pe_low,  pe_high  = bench["pe"]
    pbv_low, pbv_high = bench["pbv"]

    pe_label  = _classify(pe_val,  pe_low,  pe_high)
    pbv_label = _classify(pbv_val, pbv_low, pbv_high)

    labels = {pe_label, pbv_label} - {"N/A"}
    if not labels:
        overall = "⚪ Insufficient data for valuation verdict"
    elif labels == {"🟢 Low"}:
        overall = "🟢 Potentially Undervalued"
    elif labels == {"🔴 High"}:
        overall = "🔴 Potentially Overvalued"
    elif labels <= {"🟡 Fair", "🟢 Low"}:
        overall = "🟡 Fairly Valued"
    elif "🔴 High" in labels and "🟢 Low" in labels:
        overall = "🟡 Mixed Signals — one ratio cheap, one expensive"
    elif "🔴 High" in labels:
        overall = "🔴 Leaning Overvalued"
    else:
        overall = "🟢 Leaning Undervalued"

    return {
        "sector_matched": matched_sector,
        "pe_value":  pe_val,   "pe_label":  pe_label,
        "pe_range":  f"Low < {pe_low}  |  Fair {pe_low}–{pe_high}  |  High > {pe_high}",
        "pbv_value": pbv_val,  "pbv_label": pbv_label,
        "pbv_range": f"Low < {pbv_low}  |  Fair {pbv_low}–{pbv_high}  |  High > {pbv_high}",
        "overall":   overall,
    }
