"""Point-in-time historical PE and PBV reference bands."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _strip_index(index) -> pd.DatetimeIndex:
    values = pd.to_datetime(index)
    return values.tz_localize(None) if values.tz is not None else values


def _statement_row(statement: pd.DataFrame | None, candidates: list[str]) -> pd.Series | None:
    if statement is None or statement.empty:
        return None
    for candidate in candidates:
        if candidate in statement.index:
            row = pd.to_numeric(statement.loc[candidate], errors="coerce").dropna()
            row.index = _strip_index(row.index)
            return row.sort_index()
    return None


def _availability_map(value: Any) -> pd.Series:
    if value is None:
        return pd.Series(dtype="datetime64[ns]")
    if isinstance(value, dict):
        value = pd.Series(value)
    if not isinstance(value, pd.Series):
        return pd.Series(dtype="datetime64[ns]")
    result = pd.to_datetime(value, errors="coerce").dropna()
    result.index = _strip_index(result.index)
    return result.sort_index()


def _shares_for_periods(shares_history: pd.DataFrame | None, column: str) -> pd.DataFrame:
    if shares_history is None or shares_history.empty or column not in shares_history:
        return pd.DataFrame(columns=["period_end", "available_at", "shares"])
    frame = shares_history.copy()
    if "period_end" not in frame:
        frame["period_end"] = frame.index
    if "available_at" not in frame:
        return pd.DataFrame(columns=["period_end", "available_at", "shares"])
    frame = frame[["period_end", "available_at", column]].rename(columns={column: "shares"})
    frame["period_end"] = pd.to_datetime(frame["period_end"], errors="coerce").dt.tz_localize(None)
    frame["available_at"] = pd.to_datetime(frame["available_at"], errors="coerce").dt.tz_localize(None)
    frame["shares"] = pd.to_numeric(frame["shares"], errors="coerce")
    return frame.dropna().query("shares > 0").sort_values(["period_end", "available_at"])


def _pit_facts(row: pd.Series | None, availability: Any, shares: pd.DataFrame) -> pd.DataFrame:
    available = _availability_map(availability)
    if row is None or available.empty or shares.empty:
        return pd.DataFrame()
    facts = pd.DataFrame({"period_end": row.index, "value": row.values})
    facts["available_at"] = facts["period_end"].map(available)
    facts = facts.dropna().sort_values("period_end")
    merged = facts.merge(shares, on="period_end", how="inner", suffixes=("_fact", "_shares"))
    if merged.empty:
        return merged
    merged["available_at"] = merged[["available_at_fact", "available_at_shares"]].max(axis=1)
    return merged[["period_end", "value", "shares", "available_at"]].sort_values("period_end")


def _daily_multiple(close: pd.Series, facts: pd.DataFrame, *, ttm: bool) -> pd.DataFrame:
    if facts.empty:
        return pd.DataFrame()
    facts = facts.copy()
    if ttm:
        facts["per_share"] = facts["value"].rolling(4, min_periods=4).sum() / facts["shares"].rolling(4, min_periods=4).mean()
        available_ns = facts["available_at"].astype("int64").rolling(4, min_periods=4).max()
        facts["available_at"] = pd.to_datetime(available_ns, errors="coerce")
    else:
        facts["per_share"] = facts["value"] / facts["shares"]
    facts = facts.dropna(subset=["per_share", "available_at"])
    facts = facts[facts["per_share"] > 0].sort_values("available_at").drop_duplicates("available_at", keep="last")
    if facts.empty:
        return pd.DataFrame()
    prices = close.rename("close").reset_index()
    prices.columns = ["date", "close"]
    prices["date"] = pd.to_datetime(prices["date"]).dt.tz_localize(None)
    joined = pd.merge_asof(
        prices.sort_values("date"), facts[["available_at", "per_share"]],
        left_on="date", right_on="available_at", direction="backward",
    ).dropna()
    joined["multiple"] = joined["close"] / joined["per_share"]
    return joined[joined["multiple"] > 0].set_index("date")


def _bands(frame: pd.DataFrame, prefix: str) -> dict | None:
    if len(frame) < 8:
        return None
    multiple = frame["multiple"]
    mean, std, current = multiple.mean(), multiple.std(), multiple.iloc[-1]
    if pd.isna(std):
        return None
    per_share = frame["per_share"]
    return {
        "dates": frame.index, "close": frame["close"],
        "band_m2": per_share * (mean - 2 * std), "band_m1": per_share * (mean - std),
        "band_mean": per_share * mean, "band_p1": per_share * (mean + std),
        "band_p2": per_share * (mean + 2 * std),
        f"{prefix}_mean": round(float(mean), 2), f"{prefix}_std": round(float(std), 2),
        f"current_{prefix}": round(float(current), 2),
        "sd_position": round(float((current - mean) / std if std > 0 else 0), 2),
        "status": "AVAILABLE", "formula_version": "valuation-bands-pit-v4",
    }


def compute_valuation_bands(
    history: pd.DataFrame,
    quarterly_income: pd.DataFrame | None,
    quarterly_balance: pd.DataFrame | None,
    info: dict,
    *,
    income_available_at: Any = None,
    balance_available_at: Any = None,
    shares_history: pd.DataFrame | None = None,
) -> dict:
    """Build bands only from facts and shares actually available on each date.

    Yahoo statement period labels do not establish publication time, so the
    compatibility path intentionally returns unavailable bands until an
    official ingestion adapter supplies availability and historical shares.
    """
    result = {
        "pe": None, "pbv": None, "status": "INSUFFICIENT_POINT_IN_TIME_DATA",
        "formula_version": "valuation-bands-pit-v4",
        "warnings": ["Historical valuation bands require filing availability timestamps and historical shares."],
    }
    if history is None or history.empty or "Close" not in history:
        return result
    close = history["Close"].dropna().copy()
    close.index = _strip_index(close.index)
    income = _statement_row(quarterly_income, ["Net Income", "Net Income From Continuing Operations", "NetIncome", "Net Income Common Stockholders"])
    equity = _statement_row(quarterly_balance, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest", "Total Stockholders Equity", "Total Equity"])
    income_facts = _pit_facts(income, income_available_at, _shares_for_periods(shares_history, "weighted_average_shares"))
    equity_facts = _pit_facts(equity, balance_available_at, _shares_for_periods(shares_history, "period_end_shares"))
    result["pe"] = _bands(_daily_multiple(close, income_facts, ttm=True), "pe")
    result["pbv"] = _bands(_daily_multiple(close, equity_facts, ttm=False), "pbv")
    if result["pe"] or result["pbv"]:
        result["status"] = "AVAILABLE"
        result["warnings"] = []
    return result
