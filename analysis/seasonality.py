"""Monthly seasonality analysis from historical price data."""

import pandas as pd

from data.validation import split_adjusted_ohlcv


def compute_seasonality(history: pd.DataFrame, *, minimum_observations: int = 8) -> dict:
    """Compute monthly average returns and win-rate from historical prices."""
    adjusted = split_adjusted_ohlcv(history)
    df = adjusted[["Close"]].copy()
    df.index = pd.to_datetime(df.index)
    try:
        df.index = df.index.tz_localize(None)
    except TypeError:
        df.index = df.index.tz_convert(None)

    monthly = df["Close"].resample("ME").last()
    monthly_returns = monthly.pct_change() * 100
    monthly_returns = monthly_returns.dropna()

    months_num      = monthly_returns.index.month
    monthly_avg     = monthly_returns.groupby(months_num).mean()
    monthly_std     = monthly_returns.groupby(months_num).std()
    monthly_count   = monthly_returns.groupby(months_num).count()
    monthly_pos_pct = monthly_returns.groupby(months_num).apply(
        lambda x: (x > 0).mean() * 100 if len(x) > 0 else 0.0
    )
    monthly_median = monthly_returns.groupby(months_num).median()
    standard_error = monthly_std / monthly_count.pow(.5)
    ci95_low = monthly_avg - 1.96 * standard_error
    ci95_high = monthly_avg + 1.96 * standard_error
    eligible = monthly_count >= minimum_observations

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    return {
        "monthly_avg":     monthly_avg,
        "monthly_std":     monthly_std,
        "monthly_count":   monthly_count,
        "monthly_pos_pct": monthly_pos_pct,
        "monthly_returns": monthly_returns,
        "monthly_median": monthly_median,
        "ci95_low": ci95_low,
        "ci95_high": ci95_high,
        "eligible": eligible,
        "minimum_observations": minimum_observations,
        "month_names":     month_names,
        "best_month": int(monthly_avg[eligible].idxmax()) if eligible.any() else None,
        "worst_month": int(monthly_avg[eligible].idxmin()) if eligible.any() else None,
    }
