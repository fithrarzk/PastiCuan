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


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(max(low, min(high, value)))


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_lower_better(value, good: float, bad: float) -> float | None:
    value = _safe_float(value)
    if value is None:
        return None
    if value <= good:
        return 85.0
    if value >= bad:
        return 25.0
    return _clip(85 - (value - good) / (bad - good) * 60)


def _score_higher_better(value, weak: float, strong: float) -> float | None:
    value = _safe_float(value)
    if value is None:
        return None
    if value >= strong:
        return 85.0
    if value <= weak:
        return 25.0
    return _clip(25 + (value - weak) / (strong - weak) * 60)


def _sector_style(sector: str) -> str:
    sector_lower = (sector or "").lower()
    if "financial" in sector_lower or "bank" in sector_lower:
        return "bank"
    if any(key in sector_lower for key in ["energy", "materials", "mining", "coal", "oil"]):
        return "commodity"
    if "technology" in sector_lower:
        return "growth"
    if any(key in sector_lower for key in ["consumer defensive", "staples", "utilities", "healthcare"]):
        return "defensive"
    if "real estate" in sector_lower or "property" in sector_lower:
        return "property"
    return "general"


def _growth_from_statement(statement, candidates: list[str]) -> float | None:
    if statement is None or getattr(statement, "empty", True):
        return None
    row = None
    for candidate in candidates:
        if candidate in statement.index:
            row = statement.loc[candidate]
            break
    if row is None:
        return None
    series = row.dropna().sort_index()
    if len(series) < 8:
        return None
    recent = series.tail(4).sum()
    previous = series.iloc[-8:-4].sum()
    if previous == 0:
        return None
    return float((recent / abs(previous) - 1) * 100)


def _component_average(values: list[float | None], fallback: float = 50.0) -> float:
    valid = [v for v in values if v is not None]
    if not valid:
        return fallback
    return float(sum(valid) / len(valid))


def _fundamental_verdict(score: float, risk_flags: list[str]) -> str:
    if score >= 75 and not risk_flags:
        return "🟢 High Quality / Attractive"
    if score >= 65:
        return "🟢 Fundamentally Supportive"
    if score >= 52:
        return "🟡 Fair / Watchlist"
    if score >= 42:
        return "🟠 Mixed Fundamentals"
    return "🔴 Weak Fundamental Risk"


def analyze_fundamental(
    info: dict,
    sector: str,
    quarterly_income=None,
    quarterly_balance=None,
) -> dict:
    """
    Evaluates valuation and fundamental quality against sector-specific IDX
    benchmarks and returns an explainable score.

    Parameters
    ----------
    info   : raw yfinance .info dict
    sector : sector string from yfinance (e.g. 'Financial Services')

    Returns
    -------
    dict with pe/pbv labels, benchmark ranges, and an overall verdict string.
    """
    info = info or {}
    pe_val = info.get("trailingPE")
    pbv_val = info.get("priceToBook")
    dividend_yield = info.get("dividendYield")
    roe = info.get("returnOnEquity")
    roa = info.get("returnOnAssets")
    margin = info.get("profitMargins")
    debt_to_equity = info.get("debtToEquity")
    revenue_growth = info.get("revenueGrowth")
    earnings_growth = info.get("earningsGrowth")

    statement_revenue_growth = _growth_from_statement(
        quarterly_income,
        ["Total Revenue", "Revenue", "Operating Revenue"],
    )
    statement_income_growth = _growth_from_statement(
        quarterly_income,
        ["Net Income", "Net Income Common Stockholders", "NetIncome"],
    )

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

    style = _sector_style(sector)

    valuation_score = _component_average(
        [
            _score_lower_better(pe_val, pe_low, pe_high * 1.35),
            _score_lower_better(pbv_val, pbv_low, pbv_high * 1.35),
            _score_higher_better(dividend_yield, 0.0, 0.05),
        ]
    )

    profitability_score = _component_average(
        [
            _score_higher_better(roe, 0.05, 0.18),
            _score_higher_better(roa, 0.02, 0.08),
            _score_higher_better(margin, 0.04, 0.20),
        ]
    )

    growth_score = _component_average(
        [
            _score_higher_better(revenue_growth, -0.05, 0.18),
            _score_higher_better(earnings_growth, -0.05, 0.20),
            _score_higher_better(statement_revenue_growth, -5.0, 18.0),
            _score_higher_better(statement_income_growth, -5.0, 20.0),
        ]
    )

    leverage_good = 250 if style == "bank" else 60
    leverage_bad = 800 if style == "bank" else 180
    balance_sheet_score = _component_average(
        [_score_lower_better(debt_to_equity, leverage_good, leverage_bad)]
    )

    quality_values = [
        profitability_score,
        65 if statement_income_growth is not None and statement_income_growth > 0 else None,
        65 if statement_revenue_growth is not None and statement_revenue_growth > 0 else None,
    ]
    quality_score = _component_average(quality_values)

    weights = {
        "bank": {
            "valuation": 0.24,
            "profitability": 0.34,
            "growth": 0.12,
            "balance_sheet": 0.20,
            "quality": 0.10,
        },
        "commodity": {
            "valuation": 0.26,
            "profitability": 0.22,
            "growth": 0.12,
            "balance_sheet": 0.24,
            "quality": 0.16,
        },
        "growth": {
            "valuation": 0.16,
            "profitability": 0.22,
            "growth": 0.34,
            "balance_sheet": 0.12,
            "quality": 0.16,
        },
        "defensive": {
            "valuation": 0.24,
            "profitability": 0.26,
            "growth": 0.14,
            "balance_sheet": 0.16,
            "quality": 0.20,
        },
        "property": {
            "valuation": 0.24,
            "profitability": 0.18,
            "growth": 0.14,
            "balance_sheet": 0.30,
            "quality": 0.14,
        },
        "general": {
            "valuation": 0.25,
            "profitability": 0.25,
            "growth": 0.18,
            "balance_sheet": 0.17,
            "quality": 0.15,
        },
    }[style]

    components = {
        "valuation": valuation_score,
        "profitability": profitability_score,
        "growth": growth_score,
        "balance_sheet": balance_sheet_score,
        "quality": quality_score,
    }
    fundamental_score = sum(components[key] * weights[key] for key in components)

    quality_flags = []
    risk_flags = []
    if roe is not None and roe >= 0.15:
        quality_flags.append("ROE is strong relative to a broad IDX quality threshold.")
    if margin is not None and margin >= 0.15:
        quality_flags.append("Net margin is healthy.")
    if statement_revenue_growth is not None and statement_revenue_growth > 0:
        quality_flags.append("Trailing four-quarter revenue is growing.")
    if statement_income_growth is not None and statement_income_growth > 0:
        quality_flags.append("Trailing four-quarter net income is growing.")
    if debt_to_equity is not None and debt_to_equity > leverage_bad:
        risk_flags.append("Debt-to-equity is elevated for this sector profile.")
    if margin is not None and margin < 0:
        risk_flags.append("Net margin is negative.")
    if earnings_growth is not None and earnings_growth < -0.10:
        risk_flags.append("Earnings growth is contracting.")
    if pe_val is not None and pe_val > pe_high * 1.5 and growth_score < 60:
        risk_flags.append("Valuation is high without enough visible growth support.")

    fundamental_verdict = _fundamental_verdict(fundamental_score, risk_flags)

    return {
        "sector_matched": matched_sector,
        "pe_value":  pe_val,   "pe_label":  pe_label,
        "pe_range":  f"Low < {pe_low}  |  Fair {pe_low}–{pe_high}  |  High > {pe_high}",
        "pbv_value": pbv_val,  "pbv_label": pbv_label,
        "pbv_range": f"Low < {pbv_low}  |  Fair {pbv_low}–{pbv_high}  |  High > {pbv_high}",
        "overall":   overall,
        "sector_style": style,
        "dividend_yield": dividend_yield,
        "roe": roe,
        "roa": roa,
        "net_margin": margin,
        "debt_to_equity": debt_to_equity,
        "revenue_growth": revenue_growth,
        "earnings_growth": earnings_growth,
        "statement_revenue_growth": statement_revenue_growth,
        "statement_income_growth": statement_income_growth,
        "fundamental_score": _clip(fundamental_score),
        "fundamental_components": components,
        "quality_flags": quality_flags,
        "risk_flags": risk_flags,
        "fundamental_verdict": fundamental_verdict,
    }
