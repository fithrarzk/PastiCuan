"""Validated policy shared by Filing orchestration and durable storage."""

from dataclasses import dataclass
import math


_RETRYABLE_FILING_ERRORS = frozenset(
    {
        ("TRANSIENT", "LEASE_EXPIRED"),
        ("PROVIDER", "PROVIDER_UNAVAILABLE"),
        ("DATABASE", "DATABASE_UNAVAILABLE"),
    }
)


def is_retryable_filing_error(error_class, error_summary) -> bool:
    """Return whether a stable Filing failure is explicitly retryable."""
    return (error_class, error_summary) in _RETRYABLE_FILING_ERRORS


@dataclass(frozen=True)
class FilingImportPolicy:
    """Immutable, validated bounds for one deterministic Filing shard."""

    shard_count: int = 1
    shard_index: int = 0
    run_id: str | None = None
    max_attempts: int = 3
    retry_backoff_seconds: float = 0
    time_budget_seconds: float = 1200
    per_item_reserve_seconds: float = 120

    def __post_init__(self) -> None:
        numeric_bounds = (
            self.retry_backoff_seconds,
            self.time_budget_seconds,
            self.per_item_reserve_seconds,
        )
        if (
            isinstance(self.shard_count, bool)
            or isinstance(self.shard_index, bool)
            or not isinstance(self.shard_count, int)
            or not isinstance(self.shard_index, int)
            or self.shard_count <= 0
            or self.shard_index < 0
            or self.shard_index >= self.shard_count
            or isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts <= 0
            or any(isinstance(value, bool) for value in numeric_bounds)
            or any(not isinstance(value, (int, float)) for value in numeric_bounds)
            or any(not math.isfinite(value) for value in numeric_bounds)
            or self.retry_backoff_seconds < 0
            or self.time_budget_seconds <= 0
            or self.per_item_reserve_seconds < 0
            or self.per_item_reserve_seconds >= self.time_budget_seconds
            or (self.run_id is not None and not str(self.run_id).strip())
        ):
            raise ValueError("invalid Filing import policy")
