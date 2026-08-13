"""Replaceable data-provider interfaces and provenance rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

import pandas as pd


SOURCE_PRIORITY = {"official": 1, "licensed": 2, "yahoo_fallback": 3}


@dataclass(frozen=True)
class ProviderResult:
    data: object
    provider: str
    source_class: str
    observed_at: datetime
    source_url: str | None = None
    checksum: str | None = None

    @property
    def authoritative(self) -> bool:
        return self.source_class == "official"


@runtime_checkable
class MarketPriceProvider(Protocol):
    def history(self, ticker: str, start: datetime, end: datetime) -> ProviderResult: ...


@runtime_checkable
class FundamentalProvider(Protocol):
    def facts(self, ticker: str, as_of: datetime) -> ProviderResult: ...


@runtime_checkable
class CorporateActionProvider(Protocol):
    def actions(self, ticker: str, start: datetime, end: datetime) -> ProviderResult: ...


@runtime_checkable
class FxProvider(Protocol):
    def rates(self, base: str, quote: str, start: datetime, end: datetime) -> ProviderResult: ...


@runtime_checkable
class PolicyRateProvider(Protocol):
    def observations(self, start: datetime, end: datetime) -> ProviderResult: ...


def choose_preferred(results: list[ProviderResult]) -> ProviderResult | None:
    """Select deterministically; unknown providers are always lowest priority."""
    if not results:
        return None
    return min(results, key=lambda r: (SOURCE_PRIORITY.get(r.source_class, 99), r.provider))

