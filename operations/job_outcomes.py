"""Stable, redacted outcomes for scheduled research jobs.

This module is intentionally independent from database and provider clients.  A
job can therefore report a deterministic result even when its infrastructure
boundary is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from analysis.contracts import _json_safe


class Outcome(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    NOOP = "NOOP"
    WAITING = "WAITING"
    UNAVAILABLE = "UNAVAILABLE"
    POLICY_GATE = "POLICY_GATE"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class PersistedStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


EXIT_CODES = {
    Outcome.SUCCEEDED: 0,
    Outcome.NOOP: 0,
    Outcome.WAITING: 10,
    Outcome.UNAVAILABLE: 20,
    Outcome.POLICY_GATE: 30,
    Outcome.INFRASTRUCTURE: 40,
}

PERSISTED_STATUSES = {
    Outcome.SUCCEEDED: PersistedStatus.SUCCEEDED,
    Outcome.NOOP: PersistedStatus.SUCCEEDED,
    Outcome.WAITING: PersistedStatus.DEGRADED,
    Outcome.UNAVAILABLE: PersistedStatus.DEGRADED,
    Outcome.POLICY_GATE: PersistedStatus.FAILED,
    Outcome.INFRASTRUCTURE: PersistedStatus.FAILED,
}

# Public names make the machine contract discoverable to workflow adapters.
OUTCOME_EXIT_CODES = EXIT_CODES
OUTCOME_PERSISTED_STATUSES = PERSISTED_STATUSES
OutcomeCode = Outcome


@dataclass(frozen=True)
class JobOutcome:
    """Allowlisted information safe for reports, metrics, and stdout."""

    outcome: Outcome
    code: str
    stage: str
    retryable: bool
    summary: str
    action: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.outcome]

    @property
    def persisted_status(self) -> str:
        return PERSISTED_STATUSES[self.outcome].value

    def to_dict(self) -> dict[str, Any]:
        return _json_safe({
            "outcome": self.outcome.value,
            "code": self.code,
            "stage": self.stage,
            "retryable": self.retryable,
            "summary": self.summary,
            "action": self.action,
            "details": self.details,
            "exit_code": self.exit_code,
            "persisted_status": self.persisted_status,
        })


class OutcomeFailure(Exception):
    """Typed failure used instead of classifying exception text."""

    def __init__(self, result: JobOutcome):
        self.result = result
        super().__init__(result.code)


def outcome(
    kind: Outcome,
    code: str,
    stage: str,
    *,
    retryable: bool,
    summary: str,
    action: str,
    details: dict[str, Any] | None = None,
) -> JobOutcome:
    return JobOutcome(kind, code, stage, retryable, summary, action, details or {})


def unknown_failure(stage: str) -> JobOutcome:
    return outcome(
        Outcome.INFRASTRUCTURE, "UNKNOWN_FAILURE", stage, retryable=False,
        summary="The research job encountered an unexpected infrastructure failure.",
        action="Inspect the redacted stage result and incident record.",
    )


def infrastructure_failure(exc: Exception, stage: str) -> JobOutcome:
    """Classify known boundary types without inspecting exception messages."""
    sqlstate = getattr(exc, "pgcode", None) or getattr(exc, "sqlstate", None)
    if sqlstate in {"57014", "55P03"} or isinstance(exc, TimeoutError):
        return outcome(
            Outcome.INFRASTRUCTURE, "DATABASE_TIMEOUT", stage, retryable=True,
            summary="A required infrastructure operation timed out.",
            action="Retry within the bounded operational policy.",
        )
    if sqlstate:
        return outcome(
            Outcome.INFRASTRUCTURE, "DATABASE_ERROR", stage, retryable=False,
            summary="A required database operation failed.",
            action="Inspect the redacted stage result and database health.",
        )
    if isinstance(exc, ImportError):
        return outcome(
            Outcome.INFRASTRUCTURE, "DEPENDENCY_MISSING", stage, retryable=False,
            summary="A required runtime dependency is unavailable.",
            action="Restore the pinned job dependency and rerun.",
        )
    if isinstance(exc, (OSError, IOError)):
        return outcome(
            Outcome.INFRASTRUCTURE, "FILESYSTEM_ERROR", stage, retryable=False,
            summary="A required filesystem operation failed.",
            action="Inspect the runner workspace and rerun.",
        )
    return unknown_failure(stage)


def exit_code_for(value: Outcome | JobOutcome | str) -> int:
    if isinstance(value, JobOutcome):
        return value.exit_code
    return EXIT_CODES[Outcome(value)]


# Names used by integrations are explicit aliases, not separate contracts.
OperationalOutcome = Outcome
OutcomeResult = JobOutcome
