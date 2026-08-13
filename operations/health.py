"""Deterministic health checks suitable for a scheduler or status endpoint."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class HealthCheck:
    name: str
    healthy: bool
    detail: str


def assess_health(
    *,
    latest_completed_session: datetime | None,
    last_successful_ingestion: datetime | None,
    quarantined_records: int,
    provider_disagreements: int,
    failed_alerts: int,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    checks = [
        HealthCheck("market_data_freshness", bool(latest_completed_session and now - latest_completed_session <= timedelta(days=7)),
                    "latest completed LQ45 session must be no more than seven calendar days old"),
        HealthCheck("ingestion", bool(last_successful_ingestion and now - last_successful_ingestion <= timedelta(days=2)),
                    "scheduled ingestion must have succeeded within two days"),
        HealthCheck("validation", quarantined_records == 0,
                    f"{quarantined_records} records are quarantined"),
        HealthCheck("provider_agreement", provider_disagreements == 0,
                    f"{provider_disagreements} material discrepancies are unresolved"),
        HealthCheck("alert_delivery", failed_alerts == 0,
                    f"{failed_alerts} alert deliveries failed"),
    ]
    return {"healthy": all(check.healthy for check in checks), "checks": [asdict(check) for check in checks]}

