"""Versioned, JSON-safe contracts shared by every PastiCuan interface.

The contract deliberately keeps evidence sections separate.  Consumers may
render an action, but must never derive or mutate one themselves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
import json
from decimal import Decimal
import math
from typing import Any, cast


ANALYSIS_VERSION = "4.0.0-shadow"
CONTRACT_VERSION = "4.0"
FORMULA_VERSION = "idx-eod-v4-shadow"


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_MEANINGFUL = "NOT_MEANINGFUL"
    STALE = "STALE"
    QUARANTINED = "QUARANTINED"
    UNSUPPORTED_PROFILE = "UNSUPPORTED_PROFILE"


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
    as_of: str | None = None
    available_at: str | None = None
    source_class: str | None = None
    source_ids: tuple[str, ...] = ()
    coverage_pct: float = 0.0
    freshness: str = "UNKNOWN"
    warnings: tuple[str, ...] = ()


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
    buy_range: dict[str, Any]
    decision: dict[str, Any]
    gates: list[GateResult]
    warnings: list[str] = field(default_factory=list)
    action: str | None = None
    analysis_version: str = ANALYSIS_VERSION
    contract_version: str = CONTRACT_VERSION
    analysis_as_of: str | None = None
    signal_time: str | None = None
    earliest_execution_time: str | None = None
    snapshot_id: str | None = None
    model_version: str | None = None
    validation_run_id: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = _json_safe(asdict(self))
        # v2 compatibility aliases remain until Streamlit and Telegram have
        # fully migrated to the v4 timing fields.
        payload["as_of"] = payload.get("analysis_as_of") or payload["as_of"]
        return payload

    def to_json(self) -> str:
        return strict_json_dumps(self.to_dict(), separators=(",", ":"))


@dataclass
class ScanBundle:
    as_of: str
    requested_tickers: list[str]
    candidates: list[dict[str, Any]]
    excluded: list[dict[str, str]]
    warnings: list[str] = field(default_factory=list)
    mode: str = "UNAVAILABLE"
    snapshot_id: str | None = None
    session_date: str | None = None
    universe: str = "LQ45"
    universe_coverage_pct: float = 0.0
    quant_snapshot_id: str | None = None
    source_summary: dict[str, Any] = field(default_factory=dict)
    formula_version: str = "research-scan-v2"
    analysis_version: str = ANALYSIS_VERSION
    policy_label: str = "RESEARCH_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


def _json_safe(value: Any) -> Any:
    """Convert pandas/numpy/datetime values without inventing replacements."""
    if value.__class__.__name__ in {"NAType", "NaTType"}:
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return float(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not math.isfinite(value):
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
    # DataFrames stay out of the serialized evidence contract.
    if value.__class__.__name__ in {"DataFrame", "Series"}:
        return None
    if hasattr(value, "tolist"):
        return _json_safe(value.tolist())
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return str(value)


def strict_json_dumps(value: Any, **kwargs: Any) -> str:
    """Serialize a contract without allowing NaN or infinity JSON tokens."""
    options = {"sort_keys": True, "allow_nan": False}
    options.update(kwargs)
    options["allow_nan"] = False
    dumps = cast(Any, json.dumps)
    return dumps(_json_safe(value), **options)
