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


def _ttm_statement_value(statement, candidates: list[str]) -> float | None:
    """Sum four discrete quarterly facts; never fill a missing quarter."""
    if statement is None or getattr(statement, "empty", True):
        return None
    for candidate in candidates:
        if candidate not in statement.index:
            continue
        series = statement.loc[candidate].dropna().sort_index()
        if len(series) < 4:
            return None
        values = series.tail(4)
        if len(values) == 4:
            return float(values.sum())
    return None


def _component_average(values: list[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return float(sum(valid) / len(valid))


def _fundamental_verdict(score: float | None, risk_flags: list[str]) -> str:
    if score is None:
        return "⚪ INSUFFICIENT_DATA"
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
    quarterly_cashflow=None,
    peer_metrics: list[dict] | None = None,
    peer_scope: str = "sector",
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
    pe_raw = _safe_float(info.get("trailingPE"))
    pbv_raw = _safe_float(info.get("priceToBook"))
    # Negative earnings/equity multiples are mathematically defined but have
    # no useful "cheap/expensive" valuation interpretation.
    pe_status = "AVAILABLE" if pe_raw is not None and pe_raw > 0 else (
        "NOT_MEANINGFUL" if pe_raw is not None else "INSUFFICIENT_DATA"
    )
    pbv_status = "AVAILABLE" if pbv_raw is not None and pbv_raw > 0 else (
        "NOT_MEANINGFUL" if pbv_raw is not None else "INSUFFICIENT_DATA"
    )
    pe_val = pe_raw if pe_status == "AVAILABLE" else None
    pbv_val = pbv_raw if pbv_status == "AVAILABLE" else None
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
    operating_cash_flow_ttm = _ttm_statement_value(
        quarterly_cashflow,
        ["Operating Cash Flow", "Total Cash From Operating Activities", "Cash Flow From Continuing Operating Activities"],
    )
    free_cash_flow_ttm = _ttm_statement_value(
        quarterly_cashflow,
        ["Free Cash Flow"],
    )
    net_income_ttm = _ttm_statement_value(
        quarterly_income,
        ["Net Income", "Net Income Common Stockholders", "NetIncome"],
    )
    cash_conversion = (
        operating_cash_flow_ttm / net_income_ttm
        if operating_cash_flow_ttm is not None and net_income_ttm is not None and net_income_ttm > 0
        else None
    )
    market_cap = _safe_float(info.get("marketCap"))
    currency_alignment = info.get("_currency_alignment_status", "INSUFFICIENT_DATA")
    fcf_yield = (
        free_cash_flow_ttm / market_cap
        if free_cash_flow_ttm is not None and market_cap is not None and market_cap > 0
        and currency_alignment == "AVAILABLE"
        else None
    )
    operating_cash_flow_growth = _growth_from_statement(
        quarterly_cashflow,
        ["Operating Cash Flow", "Total Cash From Operating Activities", "Cash Flow From Continuing Operating Activities"],
    )

    # Point-in-time peer comparisons replace undocumented fixed ranges.  The
    # legacy benchmark table remains above solely for old imports; it is not
    # used by this analysis path.
    peers = peer_metrics or []
    min_peers = 5

    def peer_percentile(key: str, value: float | None) -> float | None:
        values = sorted(
            float(p[key]) for p in peers
            if p.get(key) is not None and float(p[key]) > 0
        )
        if value is None or len(values) < min_peers:
            return None
        return sum(v <= value for v in values) / len(values) * 100

    pe_pct = peer_percentile("pe", pe_val)
    pbv_pct = peer_percentile("pbv", pbv_val)
    scope_label = "Sector" if peer_scope == "sector" else "Scan-universe"
    pe_label = "N/A" if pe_status == "INSUFFICIENT_DATA" else (
        "NOT_MEANINGFUL" if pe_status == "NOT_MEANINGFUL" else
        ("Unavailable — peer sample < 5" if pe_pct is None else f"{scope_label} percentile {pe_pct:.0f}")
    )
    pbv_label = "N/A" if pbv_status == "INSUFFICIENT_DATA" else (
        "NOT_MEANINGFUL" if pbv_status == "NOT_MEANINGFUL" else
        ("Unavailable — peer sample < 5" if pbv_pct is None else f"{scope_label} percentile {pbv_pct:.0f}")
    )

    pct_values = [p for p in (pe_pct, pbv_pct) if p is not None]
    if not pct_values:
        overall = "⚪ Peer valuation unavailable"
    elif sum(pct_values) / len(pct_values) <= 30:
        overall = "🟢 Low relative valuation percentile"
    elif sum(pct_values) / len(pct_values) >= 70:
        overall = "🔴 High relative valuation percentile"
    else:
        overall = "🟡 Mid-range relative valuation percentile"

    style = _sector_style(sector)

    # A percentile is relative rank, not an absolute investment-quality score.
    valuation_score = _component_average(
        [
            100 - pe_pct if pe_pct is not None else None,
            100 - pbv_pct if pbv_pct is not None else None,
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

    leverage_good = 60
    leverage_bad = 180
    # Ordinary debt/equity is not a bank solvency measure. Bank-specific facts
    # (CAR/NPL/LDR/NIM) remain unavailable unless disclosed by an authoritative
    # provider rather than being approximated from Yahoo fields.
    balance_sheet_score = None if style == "bank" else _component_average(
        [_score_lower_better(debt_to_equity, leverage_good, leverage_bad)]
    )

    quality_values = [
        profitability_score,
        65 if statement_income_growth is not None and statement_income_growth > 0 else None,
        65 if statement_revenue_growth is not None and statement_revenue_growth > 0 else None,
        _score_higher_better(cash_conversion, 0.5, 1.2),
        70 if free_cash_flow_ttm is not None and free_cash_flow_ttm > 0 else (
            25 if free_cash_flow_ttm is not None else None
        ),
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
    available_components = {key: value for key, value in components.items() if value is not None}
    available_weight = sum(weights[key] for key in available_components)
    fundamental_score = (
        sum(available_components[key] * weights[key] for key in available_components) / available_weight
        if available_components and available_weight else None
    )
    coverage_pct = sum(weights[key] for key in available_components) * 100

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
    if cash_conversion is not None and cash_conversion >= 1:
        quality_flags.append("TTM operating cash flow covers reported net income.")
    if free_cash_flow_ttm is not None and free_cash_flow_ttm < 0:
        risk_flags.append("Reported TTM free cash flow is negative.")
    if free_cash_flow_ttm is not None and currency_alignment != "AVAILABLE":
        risk_flags.append("FCF yield is unavailable because reporting and market-price currencies are not aligned.")
    if style != "bank" and debt_to_equity is not None and debt_to_equity > leverage_bad:
        risk_flags.append("Debt-to-equity is elevated for this sector profile.")
    if margin is not None and margin < 0:
        risk_flags.append("Net margin is negative.")
    if earnings_growth is not None and earnings_growth < -0.10:
        risk_flags.append("Earnings growth is contracting.")
    if pe_pct is not None and pe_pct >= 85 and growth_score is not None and growth_score < 60:
        risk_flags.append("PE is in the highest peer quintile without enough visible growth support.")
    if style == "bank":
        risk_flags.append("Bank solvency metrics (CAR/NPL/LDR/NIM) require an official filing source.")

    fundamental_verdict = _fundamental_verdict(fundamental_score, risk_flags)

    return {
        "sector_matched": sector or "N/A",
        "pe_value": pe_raw, "pe_label": pe_label, "pe_status": pe_status,
        "pe_range": "Point-in-time sector percentile; minimum 5 peers",
        "pe_percentile": pe_pct,
        "pbv_value": pbv_raw, "pbv_label": pbv_label, "pbv_status": pbv_status,
        "pbv_range": "Point-in-time sector percentile; minimum 5 peers",
        "pbv_percentile": pbv_pct,
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
        "operating_cash_flow_ttm": operating_cash_flow_ttm,
        "free_cash_flow_ttm": free_cash_flow_ttm,
        "operating_cash_flow_growth": operating_cash_flow_growth,
        "cash_conversion": cash_conversion,
        "fcf_yield": fcf_yield,
        "fundamental_score": _clip(fundamental_score) if fundamental_score is not None else None,
        "coverage_pct": coverage_pct,
        "formula_version": "fundamental-pit-v3",
        "currency_alignment_status": currency_alignment,
        "peer_scope": peer_scope if pct_values else None,
        "fundamental_components": components,
        "quality_flags": quality_flags,
        "risk_flags": risk_flags,
        "fundamental_verdict": fundamental_verdict,
    }
