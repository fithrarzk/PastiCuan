"""Point-in-time input validation. Invalid observations are quarantined."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from analysis.contracts import DataQualityReport, QualityIssue


JAKARTA = ZoneInfo("Asia/Jakarta")


def completed_eod_history(history: pd.DataFrame, as_of: datetime | None = None) -> pd.DataFrame:
    """Return candles that could be known after a completed IDX session.

    A date-only daily candle for the current Jakarta date is excluded before
    16:15 WIB. Holiday membership belongs to the stored market-session table;
    this compatibility path makes no weekday/calendar claims.
    """
    if history is None or history.empty:
        return pd.DataFrame()
    now = as_of or datetime.now(JAKARTA)
    if now.tzinfo is None:
        now = now.replace(tzinfo=JAKARTA)
    else:
        now = now.astimezone(JAKARTA)
    result = history.copy().sort_index()
    last = pd.Timestamp(result.index[-1])
    last_date = last.tz_convert(JAKARTA).date() if last.tzinfo else last.date()
    if last_date == now.date() and (now.hour, now.minute) < (16, 15):
        result = result.iloc[:-1]
    return result


def validate_ohlcv(history: pd.DataFrame, as_of: datetime | None = None) -> DataQualityReport:
    issues: list[QualityIssue] = []
    required = {"Open", "High", "Low", "Close", "Volume"}
    if history is None or history.empty:
        issues.append(QualityIssue("OHLCV_EMPTY", "No completed OHLCV observations are available."))
        return DataQualityReport("F", 0, False, True, issues=issues)
    missing = required - set(history.columns)
    if missing:
        issues.append(QualityIssue("OHLCV_COLUMNS", f"Missing columns: {', '.join(sorted(missing))}"))
        return DataQualityReport("F", 0, False, True, issues=issues)

    df = completed_eod_history(history, as_of)
    duplicated = df.index.duplicated(keep=False)
    if duplicated.any():
        issues.append(QualityIssue("DUPLICATE_SESSION", "Duplicate market-session timestamps found."))
    numeric = df[["Open", "High", "Low", "Close", "Volume"]]
    if numeric.isna().any(axis=None):
        issues.append(QualityIssue("MISSING_OHLCV", "OHLCV contains missing values."))
    bad_range = (df["High"] < df[["Open", "Close", "Low"]].max(axis=1)) | (
        df["Low"] > df[["Open", "Close", "High"]].min(axis=1)
    )
    if bad_range.any():
        issues.append(QualityIssue("INVALID_OHLC_RANGE", "High/low does not enclose open and close."))
    if (numeric[["Open", "High", "Low", "Close"]] <= 0).any(axis=None) or (numeric["Volume"] < 0).any():
        issues.append(QualityIssue("INVALID_OHLCV_SIGN", "Prices must be positive and volume non-negative."))

    last = pd.Timestamp(df.index[-1]) if not df.empty else None
    now = as_of or datetime.now(JAKARTA)
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo and last is not None and last.tzinfo is None:
        last = last.tz_localize(JAKARTA)
    elif not now_ts.tzinfo and last is not None and last.tzinfo:
        now_ts = now_ts.tz_localize(JAKARTA)
    age_days = (now_ts.normalize() - last.normalize()).days if last is not None else 999
    fresh = 0 <= age_days <= 7
    if age_days < 0:
        issues.append(QualityIssue("FUTURE_PRICE", "Latest price timestamp is after the analysis time."))
    if age_days > 7:
        issues.append(QualityIssue("STALE_PRICE", f"Latest completed price is {age_days} calendar days old."))
    quarantined = any(i.code != "STALE_PRICE" for i in issues)
    coverage = max(0.0, 100.0 - 20.0 * len(issues))
    grade = "A" if not issues else ("C" if not quarantined else "F")
    return DataQualityReport(
        grade, coverage, fresh, quarantined,
        price_timestamp=last.isoformat() if last is not None else None,
        issues=issues,
    )


def split_adjusted_ohlcv(history: pd.DataFrame) -> pd.DataFrame:
    """Adjust prices for splits only; dividends remain separate cash flows."""
    if history is None or history.empty:
        return pd.DataFrame()
    result = history.copy().sort_index()
    if "Stock Splits" not in result:
        return result
    ratios = pd.to_numeric(result["Stock Splits"], errors="coerce").fillna(0).replace(0, 1.0)
    # For each row apply splits strictly after that session. The ex-date price
    # is already post-split and therefore excludes its own ratio.
    future_factor = ratios.iloc[::-1].cumprod().iloc[::-1].shift(-1, fill_value=1.0)
    for column in ("Open", "High", "Low", "Close"):
        if column in result:
            result[column] = result[column] / future_factor
    if "Volume" in result:
        result["Volume"] = result["Volume"] * future_factor
    return result
