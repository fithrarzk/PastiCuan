"""Auditable statement normalization and per-share valuation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class GrowthResult:
    status: str
    percent: Decimal | None


def ytd_to_discrete(current_ytd: Decimal, prior_ytd_same_year: Decimal | None) -> Decimal:
    """Convert an interim cumulative fact to its discrete-quarter amount."""
    return current_ytd if prior_ytd_same_year is None else current_ytd - prior_ytd_same_year


def ttm(discrete_quarters: list[Decimal | None]) -> Decimal | None:
    """TTM is available only with four complete discrete quarters."""
    if len(discrete_quarters) != 4 or any(value is None for value in discrete_quarters):
        return None
    return sum(discrete_quarters, Decimal(0))  # type: ignore[arg-type]


def growth(current: Decimal | None, previous: Decimal | None) -> GrowthResult:
    if current is None or previous is None:
        return GrowthResult("INSUFFICIENT_DATA", None)
    if previous <= 0 < current:
        return GrowthResult("LOSS_TO_PROFIT", None)
    if current < 0 <= previous:
        return GrowthResult("PROFIT_TO_LOSS", None)
    if previous == 0:
        return GrowthResult("NOT_MEANINGFUL", None)
    return GrowthResult("AVAILABLE", (current / abs(previous) - 1) * Decimal(100))


def eps(net_income_ttm: Decimal | None, weighted_average_shares: Decimal | None) -> Decimal | None:
    if net_income_ttm is None or not weighted_average_shares or weighted_average_shares <= 0:
        return None
    return net_income_ttm / weighted_average_shares


def book_value_per_share(equity: Decimal | None, period_end_shares: Decimal | None) -> Decimal | None:
    if equity is None or not period_end_shares or period_end_shares <= 0:
        return None
    return equity / period_end_shares


def valuation_multiple(price: Decimal | None, per_share_value: Decimal | None) -> tuple[str, Decimal | None]:
    if price is None or per_share_value is None:
        return "INSUFFICIENT_DATA", None
    if per_share_value <= 0:
        return "NOT_MEANINGFUL", None
    return "AVAILABLE", price / per_share_value

