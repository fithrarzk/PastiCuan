"""Derive point-in-time LQ45 factor inputs from canonical repository facts."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd


FLOW_CONCEPTS = {
    "net_income": {"net_income", "net_income_common_stockholders"},
    "operating_cash_flow": {"operating_cash_flow", "cash_flow_from_operations"},
    "operating_income": {"operating_income"},
    "basic_eps": {"basic_earnings_per_share"},
    "credit_impairment": {"credit_impairment_expense"},
}
STOCK_CONCEPTS = {
    "equity": {"stockholders_equity", "common_stock_equity", "total_equity"},
    "debt": {"total_debt", "short_and_long_term_debt"},
    "cash": {"cash_and_cash_equivalents", "cash_cash_equivalents_and_short_term_investments"},
    "assets": {"total_assets"},
    "loans": {"gross_loans"},
    "deposits": {"customer_deposits"},
    "loan_allowance": {"loan_loss_allowance"},
    "impaired_loans": {"impaired_loans"},
    "capital_adequacy_ratio": {"capital_adequacy_ratio"},
}


def _scaled(row: dict) -> float:
    return float(row["value"]) * (10 ** int(row.get("scale") or 0))


def _concept_rows(facts: list[dict], names: set[str]) -> list[dict]:
    return sorted(
        [row for row in facts if str(row.get("normalized_concept", "")).lower() in names],
        key=lambda row: str(row.get("period_end")),
    )


def _ttm(facts: list[dict], names: set[str]) -> float | None:
    rows = []
    for row in _concept_rows(facts, names):
        if not row.get("period_start"):
            continue
        duration = (pd.Timestamp(row["period_end"]) - pd.Timestamp(row["period_start"])).days
        duration_class = str(row.get("duration_class") or "").upper()
        if duration_class in {"QTD", "YTD", "FY"}:
            rows.append({**row, "_duration": duration, "_class": duration_class})
    by_period = {}
    for row in rows:
        by_period[(str(row.get("period_start")), str(row["period_end"]))] = row
    rows = sorted(by_period.values(), key=lambda row: str(row["period_end"]))

    # IDX interim statements are normally cumulative YTD. Build TTM as the
    # latest annual result + current YTD - comparable prior-year YTD.
    annuals = [row for row in rows if row["_class"] == "FY"]
    interims = [row for row in rows if row["_class"] == "YTD"]
    for current in reversed(interims):
        annual = next((row for row in reversed(annuals)
                       if pd.Timestamp(row["period_end"]) < pd.Timestamp(current["period_end"])), None)
        prior = next((row for row in reversed(interims)
                      if row.get("fiscal_quarter") == current.get("fiscal_quarter")
                      and row.get("fiscal_year") == (current.get("fiscal_year") or 0) - 1
                      and 330 <= (pd.Timestamp(current["period_end"]) - pd.Timestamp(row["period_end"])).days <= 400), None)
        if annual is not None and prior is not None:
            return _scaled(annual) + _scaled(current) - _scaled(prior)

    # Some canonical feeds provide discrete quarters instead of cumulative YTD.
    quarters = [row for row in rows if row["_class"] == "QTD"]
    latest = quarters[-4:]
    if len(latest) == 4 and all(
        60 <= (pd.Timestamp(right["period_end"]) - pd.Timestamp(left["period_end"])).days <= 120
        for left, right in zip(latest, latest[1:])
    ):
        return sum(_scaled(row) for row in latest)
    return _scaled(annuals[-1]) if annuals else None


def _latest(facts: list[dict], names: set[str]) -> float | None:
    rows = _concept_rows(facts, names)
    return _scaled(rows[-1]) if rows else None


def _reported_ratio(value: float | None) -> float | None:
    """Normalize a disclosed percentage while preserving decimal ratios."""
    if value is None:
        return None
    return value / 100 if abs(value) > 1 else value


def _annual_values(facts: list[dict], names: set[str]) -> list[float]:
    rows = [row for row in _concept_rows(facts, names) if str(row.get("duration_class") or "").upper() == "FY"]
    return [_scaled(row) for row in rows]


def _adjusted_close(bars: list[dict], actions: list[dict]) -> pd.Series:
    if not bars:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(bars)
    frame.index = pd.to_datetime(frame["session_date"])
    close = pd.to_numeric(frame["close"], errors="coerce").dropna().sort_index()
    splits = {pd.Timestamp(row["ex_date"]): float(row["ratio"])
              for row in actions if row["action_type"] == "SPLIT" and row.get("ratio")}
    if not splits:
        return close
    ratios = pd.Series(1.0, index=close.index)
    for date, ratio in splits.items():
        if date in ratios.index:
            ratios.loc[date] = ratio
    future = ratios.iloc[::-1].cumprod().iloc[::-1].shift(-1, fill_value=1.0)
    return close / future


def _market_features(close: pd.Series) -> dict:
    returns = close.pct_change().dropna()
    result = {"return_6m_skip_1m": None, "return_12m_skip_1m": None,
              "realized_volatility": None, "downside_deviation": None}
    if len(close) > 146:
        result["return_6m_skip_1m"] = float(close.iloc[-21] / close.iloc[-147] - 1)
    if len(close) > 272:
        result["return_12m_skip_1m"] = float(close.iloc[-21] / close.iloc[-273] - 1)
    if len(returns) >= 60:
        window = returns.tail(252)
        result["realized_volatility"] = float(window.std() * np.sqrt(252))
        result["downside_deviation"] = float(np.sqrt((window.clip(upper=0) ** 2).mean()) * np.sqrt(252))
    return result


def build_factor_inputs(repository, as_of: str, *, index_code: str = "LQ45") -> pd.DataFrame:
    cutoff = pd.Timestamp(as_of)
    cutoff_date = cutoff.tz_convert(None) if cutoff.tzinfo is not None else cutoff
    rows = []
    for issuer in repository.constituent_issuers_as_of(index_code, str(cutoff.date())):
        issuer_id = issuer["id"]
        facts = repository.facts_as_of(issuer_id, as_of)
        bars = repository.market_bars_as_of(issuer_id, as_of)
        actions = repository.corporate_actions_as_of(issuer_id, as_of)
        shares = repository.shares_as_of(issuer_id, as_of)
        close = _adjusted_close(bars, actions)
        latest_price = float(close.iloc[-1]) if not close.empty else None
        issuer_currency = str(issuer.get("currency") or "IDR").upper()
        usable_facts = []
        currency_status = "AVAILABLE"
        fx_source_ids = set()
        for fact in facts:
            fact_currency = str(fact.get("currency") or issuer_currency).upper()
            if fact_currency == issuer_currency:
                usable_facts.append(fact)
                continue
            rate_type = "AVERAGE" if str(fact.get("period_type") or "").upper() == "DURATION" else "SPOT"
            rate = repository.fx_rate_as_of(
                fact_currency, issuer_currency, str(fact["period_end"]), as_of, rate_type=rate_type,
            )
            if not rate:
                currency_status = "INSUFFICIENT_DATA"
                usable_facts = []
                break
            converted = dict(fact)
            converted["value"] = float(fact["value"]) * float(rate["rate"])
            converted["currency"] = issuer_currency
            usable_facts.append(converted)
            if rate.get("checksum"):
                fx_source_ids.add(str(rate["checksum"]))
        net_income = _ttm(usable_facts, FLOW_CONCEPTS["net_income"])
        basic_eps = _ttm(usable_facts, FLOW_CONCEPTS["basic_eps"])
        if shares:
            share_count = float(shares["period_end_shares"])
            share_count_source = "official_shares_history"
        elif net_income is not None and basic_eps is not None and abs(basic_eps) > 1e-12:
            # IDX taxonomy exposes profit and basic EPS but not a universal
            # period-end share-count concept. Their ratio is the disclosed
            # weighted-average share count, used transparently as a fallback.
            share_count = abs(net_income / basic_eps)
            share_count_source = "idx_xbrl_implied_weighted_average"
        else:
            share_count = None
            share_count_source = "unavailable"
        market_cap = latest_price * share_count if latest_price and share_count else None
        operating_cash = _ttm(usable_facts, FLOW_CONCEPTS["operating_cash_flow"])
        equity = _latest(usable_facts, STOCK_CONCEPTS["equity"])
        debt = _latest(usable_facts, STOCK_CONCEPTS["debt"])
        cash = _latest(usable_facts, STOCK_CONCEPTS["cash"])
        annual_income = _annual_values(usable_facts, FLOW_CONCEPTS["net_income"])
        earnings_growth_3y = None
        earnings_stability = None
        if len(annual_income) >= 3 and annual_income[-3] > 0 and annual_income[-1] > 0:
            earnings_growth_3y = (annual_income[-1] / annual_income[-3]) ** (1 / 2) - 1
            mean_income = float(np.mean(annual_income[-3:]))
            if mean_income > 0:
                earnings_stability = float(np.std(annual_income[-3:], ddof=0) / mean_income)
        assets = _latest(usable_facts, STOCK_CONCEPTS["assets"])
        loans = _latest(usable_facts, STOCK_CONCEPTS["loans"])
        deposits = _latest(usable_facts, STOCK_CONCEPTS["deposits"])
        loan_allowance = _latest(usable_facts, STOCK_CONCEPTS["loan_allowance"])
        impaired_loans = _latest(usable_facts, STOCK_CONCEPTS["impaired_loans"])
        capital_adequacy = _latest(usable_facts, STOCK_CONCEPTS["capital_adequacy_ratio"])
        credit_impairment = _ttm(usable_facts, FLOW_CONCEPTS["credit_impairment"])
        accrual_ratio = (
            (net_income - operating_cash) / equity
            if net_income is not None and operating_cash is not None and equity and equity > 0 else None
        )
        net_debt_to_equity = (
            ((debt or 0) - (cash or 0)) / equity if equity and equity > 0 and (debt is not None or cash is not None) else None
        )
        cash_to_equity = cash / equity if cash is not None and equity and equity > 0 else None
        dividends = 0.0
        dividend_currency_complete = True
        for item in actions:
            if (item["action_type"] != "DIVIDEND" or item.get("cash_amount") is None
                    or not cutoff_date - timedelta(days=365) < pd.Timestamp(item["ex_date"]) <= cutoff_date):
                continue
            amount = float(item["cash_amount"])
            action_currency = str(item.get("currency") or issuer_currency).upper()
            if action_currency != issuer_currency:
                rate = repository.fx_rate_as_of(
                    action_currency, issuer_currency, str(item["ex_date"]), as_of, rate_type="SPOT",
                )
                if not rate:
                    dividend_currency_complete = False
                    continue
                amount *= float(rate["rate"])
                if rate.get("checksum"):
                    fx_source_ids.add(str(rate["checksum"]))
            dividends += amount
        issuer_profile = str(issuer.get("issuer_type") or "general").upper()
        if not issuer.get("profile_verified_at"):
            issuer_profile = "UNVERIFIED"
        elif issuer_profile == "GENERAL" and any(token in str(issuer.get("sector") or "").lower()
                                                for token in ("bank", "financial")):
            issuer_profile = "BANK"
        rows.append({
            "ticker": issuer["ticker"], "sector": issuer["sector"],
            "share_count_source": share_count_source,
            "issuer_profile": issuer_profile,
            "issuer_profile_source": issuer.get("profile_source_url"),
            "issuer_profile_checksum": issuer.get("profile_checksum"),
            "annual_history_years": len(annual_income),
            "currency_status": currency_status,
            "fx_source_ids": sorted(fx_source_ids),
            "earnings_yield": net_income / market_cap if net_income is not None and market_cap else None,
            "book_yield": equity / market_cap if equity is not None and market_cap else None,
            "dividend_yield": dividends / latest_price if latest_price and dividend_currency_complete else None,
            "roe": net_income / equity if net_income is not None and equity and equity > 0 else None,
            "roa": net_income / assets if net_income is not None and assets and assets > 0 else None,
            # ROIC requires a normalized tax provision and invested-capital
            # policy; remain unavailable rather than inventing a proxy.
            "roic": None,
            "cash_conversion": operating_cash / net_income if operating_cash is not None and net_income and net_income > 0 else None,
            "leverage": debt / equity if debt is not None and equity and equity > 0 else None,
            "accrual_ratio": accrual_ratio,
            "earnings_growth_3y": earnings_growth_3y,
            "earnings_stability": earnings_stability,
            "net_debt_to_equity": net_debt_to_equity,
            "cash_to_equity": cash_to_equity,
            "equity_positive": 1.0 if equity is not None and equity > 0 else (0.0 if equity is not None else None),
            "npl_ratio": impaired_loans / loans if impaired_loans is not None and loans and loans > 0 else None,
            "credit_cost": abs(credit_impairment) / loans if credit_impairment is not None and loans and loans > 0 else None,
            "allowance_coverage": loan_allowance / impaired_loans if loan_allowance is not None and impaired_loans and impaired_loans > 0 else None,
            "capital_adequacy_ratio": _reported_ratio(capital_adequacy),
            "equity_to_assets": equity / assets if equity is not None and assets and assets > 0 else None,
            "loans_to_deposits": loans / deposits if loans is not None and deposits and deposits > 0 else None,
            "liquid_assets_to_deposits": cash / deposits if cash is not None and deposits and deposits > 0 else None,
            **_market_features(close),
            "financial_periods": sorted({str(row.get("period_end")) for row in usable_facts if row.get("period_end")}),
            "source_documents": sorted({str(row.get("document_checksum")) for row in usable_facts
                                         if row.get("document_checksum")}),
            "source_urls": sorted({str(row.get("source_url")) for row in usable_facts if row.get("source_url")}),
        })
    return pd.DataFrame(rows)
