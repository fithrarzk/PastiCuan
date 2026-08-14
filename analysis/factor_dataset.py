"""Derive point-in-time LQ45 factor inputs from canonical repository facts."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd


FLOW_CONCEPTS = {
    "net_income": {"net_income", "net_income_common_stockholders"},
    "operating_cash_flow": {"operating_cash_flow", "cash_flow_from_operations"},
    "operating_income": {"operating_income"},
}
STOCK_CONCEPTS = {
    "equity": {"stockholders_equity", "common_stock_equity", "total_equity"},
    "debt": {"total_debt", "short_and_long_term_debt"},
    "cash": {"cash_and_cash_equivalents", "cash_cash_equivalents_and_short_term_investments"},
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
        if 60 <= duration <= 120:
            rows.append(row)
    by_period = {}
    for row in rows:
        by_period[str(row["period_end"])] = row
    latest = list(by_period.values())[-4:]
    return sum(_scaled(row) for row in latest) if len(latest) == 4 else None


def _latest(facts: list[dict], names: set[str]) -> float | None:
    rows = _concept_rows(facts, names)
    return _scaled(rows[-1]) if rows else None


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
        share_count = float(shares["period_end_shares"]) if shares else None
        market_cap = latest_price * share_count if latest_price and share_count else None
        net_income = _ttm(facts, FLOW_CONCEPTS["net_income"])
        operating_cash = _ttm(facts, FLOW_CONCEPTS["operating_cash_flow"])
        equity = _latest(facts, STOCK_CONCEPTS["equity"])
        debt = _latest(facts, STOCK_CONCEPTS["debt"])
        cash = _latest(facts, STOCK_CONCEPTS["cash"])
        dividends = sum(
            float(item["cash_amount"]) for item in actions
            if item["action_type"] == "DIVIDEND" and item.get("cash_amount") is not None
            and cutoff_date - timedelta(days=365) < pd.Timestamp(item["ex_date"]) <= cutoff_date
        )
        rows.append({
            "ticker": issuer["ticker"], "sector": issuer["sector"],
            "earnings_yield": net_income / market_cap if net_income is not None and market_cap else None,
            "book_yield": equity / market_cap if equity is not None and market_cap else None,
            "dividend_yield": dividends / latest_price if latest_price else None,
            "roe": net_income / equity if net_income is not None and equity and equity > 0 else None,
            # ROIC requires a normalized tax provision and invested-capital
            # policy; remain unavailable rather than inventing a proxy.
            "roic": None,
            "cash_conversion": operating_cash / net_income if operating_cash is not None and net_income and net_income > 0 else None,
            "leverage": debt / equity if debt is not None and equity and equity > 0 else None,
            **_market_features(close),
        })
    return pd.DataFrame(rows)
