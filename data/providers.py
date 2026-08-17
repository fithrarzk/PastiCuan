"""Replaceable data-provider interfaces and provenance rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Callable
from uuid import uuid4
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


class ProviderRouter:
    """Bounded provider fallback with observable attempts and a small circuit breaker."""

    def __init__(self, *, failure_threshold: int = 3, cooldown_seconds: float = 300,
                 record: Callable[[dict], None] | None = None):
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(1.0, cooldown_seconds)
        self.record = record
        self._health: dict[str, tuple[int, float]] = {}

    def run(self, capability: str, providers: list[tuple[str, str, Callable[[], ProviderResult]]]) -> ProviderResult:
        ordered = sorted(providers, key=lambda item: (SOURCE_PRIORITY.get(item[1], 99), item[0]))
        first_failed = None
        errors = []
        for provider, source_class, fetch in ordered:
            failures, disabled_until = self._health.get(provider, (0, 0.0))
            if disabled_until > monotonic():
                self._emit(provider, capability, source_class, "CIRCUIT_OPEN", 0, first_failed, None)
                continue
            started = monotonic()
            try:
                result = fetch()
                if not isinstance(result, ProviderResult):
                    raise TypeError("Provider did not return ProviderResult.")
                self._health[provider] = (0, 0.0)
                self._emit(provider, capability, source_class, "SUCCEEDED",
                           int((monotonic() - started) * 1000), first_failed, None)
                return result
            except Exception as exc:
                failures += 1
                self._health[provider] = (
                    failures,
                    monotonic() + self.cooldown_seconds if failures >= self.failure_threshold else 0.0,
                )
                first_failed = first_failed or provider
                errors.append(f"{provider}:{type(exc).__name__}")
                self._emit(provider, capability, source_class, "FAILED",
                           int((monotonic() - started) * 1000), None, type(exc).__name__)
        raise RuntimeError(f"No provider succeeded for {capability}: {', '.join(errors) or 'all circuits open'}")

    def _emit(self, provider: str, capability: str, source_class: str, status: str,
              latency_ms: int, fallback_from: str | None, error_type: str | None) -> None:
        if self.record:
            self.record({"id": str(uuid4()), "provider": provider, "capability": capability,
                         "source_class": source_class, "started_at": datetime.now(timezone.utc).isoformat(),
                         "completed_at": datetime.now(timezone.utc).isoformat(), "status": status,
                         "attempts": 1, "latency_ms": latency_ms, "fallback_from": fallback_from,
                         "error_type": error_type, "metadata": {}})
