"""Versioned, JSON-safe contracts shared by every PastiCuan interface.

The contract deliberately keeps evidence sections separate.  Consumers may
render an action, but must never derive or mutate one themselves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
import json
from typing import Any


ANALYSIS_VERSION = "2.0.0-shadow"
FORMULA_VERSION = "idx-eod-v2"


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_MEANINGFUL = "NOT_MEANINGFUL"
    QUARANTINED = "QUARANTINED"


class DecisionLabel(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    WAIT_FOR_DATA = "WAIT_FOR_DATA"
    NO_VALIDATED_EDGE = "NO_VALIDATED_EDGE"
    ACTION_ELIGIBLE = "ACTION_ELIGIBLE"


@dataclass(frozen=True)
class SourceRef:
    provider: str
    source_url: str | None = None
    observed_at: str | None = None
    checksum: str | None = None
    authoritative: bool = False


@dataclass(frozen=True)
class Metric:
    name: str
    value: float | int | str | None
    status: Availability
    unit: str | None = None
    window: str | None = None
    formula_version: str = FORMULA_VERSION
    source: SourceRef | None = None
    inputs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityIssue:
    code: str
    message: str
    severity: str = "ERROR"
    field: str | None = None


@dataclass
class DataQualityReport:
    grade: str
    coverage_pct: float
    fresh: bool
    quarantined: bool
    price_timestamp: str | None = None
    publication_timestamp: str | None = None
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return not self.quarantined and self.fresh and self.coverage_pct >= 70


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    reason: str
    mandatory: bool = True


@dataclass
class AnalysisBundle:
    ticker: str
    as_of: str
    horizon: str
    data_quality: DataQualityReport
    fundamental: dict[str, Any]
    technical: dict[str, Any]
    quant: dict[str, Any]
    backtest: dict[str, Any]
    decision: dict[str, Any]
    gates: list[GateResult]
    warnings: list[str] = field(default_factory=list)
    action: str | None = None
    analysis_version: str = ANALYSIS_VERSION

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def _json_safe(value: Any) -> Any:
    """Convert pandas/numpy/datetime values without inventing replacements."""
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (value != value or abs(value) == float("inf")):
            return None
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    # DataFrames stay out of the serialized evidence contract.
    if value.__class__.__name__ in {"DataFrame", "Series"}:
        return None
    return str(value)

