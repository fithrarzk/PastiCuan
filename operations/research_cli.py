"""Core research jobs. Intended for local use and GitHub Actions, not Railway."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import subprocess
import math
from tempfile import TemporaryDirectory
from uuid import uuid4
from typing import Any

import pandas as pd

from analysis.quant import compute_cross_sectional_factors
from analysis.business import compute_business_scores
from analysis.backtest import BrokerCostProfile
from analysis.quant_backtest import assess_holdout, backtest_monthly_quant
from analysis.factor_dataset import build_factor_inputs
from analysis.scan_v2 import (
    build_full_lq45_scan,
    market_refresh_summary,
    refresh_lq45_market_history,
)
from analysis.snapshots import ResearchSnapshot, load_snapshot, write_snapshot
from analysis.contracts import strict_json_dumps
from data.ingestion import acquire_artifact, read_manifest, upload_to_r2
from data.parsers import parse_canonical_csv
from data.idx_xbrl import parse_idx_xbrl, validate_official_idx_url
from data.idx_reports import discover_idx_xbrl_manifest
from operations.research_release import (
    DEFAULT_RELEASE_PATH,
    check_release_change,
    load_release,
    release_from_sources,
    release_provenance,
)
from operations.job_outcomes import (
    EvidenceUnavailable,
    JobOutcome,
    Outcome,
    OutcomeFailure,
    infrastructure_failure,
    outcome,
)


def _signed_snapshot(**values) -> ResearchSnapshot:
    base = ResearchSnapshot(**values)
    return ResearchSnapshot(
        **{**base.unsigned_dict(), "checksum": base.calculated_checksum()}
    )


def build_snapshot(
    input_path: str,
    output_path: str,
    effective_at: str,
    model_version: str,
    *,
    provenance: dict | None = None,
    formula_version: str | None = None,
) -> ResearchSnapshot:
    frame = pd.read_csv(input_path)
    result = compute_cross_sectional_factors(
        frame,
        as_of=effective_at,
        min_universe=10,
        allow_global_fallback=True,
    )
    if result["status"] != "AVAILABLE":
        raise EvidenceUnavailable()
    business = compute_business_scores(frame)
    business_map = {}
    if business["status"] == "AVAILABLE":
        business_map = {
            str(row["ticker"]).upper().replace(".JK", ""): row
            for row in json.loads(business["scores"].to_json(orient="records"))
        }
    rankings = {}
    evidence_columns = (
        "issuer_profile",
        "issuer_profile_source",
        "issuer_profile_checksum",
        "annual_history_years",
        "financial_periods",
        "source_documents",
        "source_urls",
        "share_count_source",
        "currency_status",
    )
    input_evidence = {
        str(row["ticker"]).upper().replace(".JK", ""): {
            key: row.get(key) for key in evidence_columns if key in frame.columns
        }
        for row in frame.to_dict("records")
    }
    for row in json.loads(result["scores"].to_json(orient="records")):
        ticker = str(row.pop("ticker")).upper().replace(".JK", "")
        rankings[ticker] = {
            **row,
            **input_evidence.get(ticker, {}),
            **{
                key: value
                for key, value in business_map.get(ticker, {}).items()
                if key != "ticker"
            },
        }
    warnings = list(result.get("warnings", []))
    if (
        "share_count_source" in frame
        and (frame["share_count_source"] == "idx_xbrl_implied_weighted_average").any()
    ):
        warnings.append(
            "Where official period-end shares were unavailable, market cap uses the weighted-average "
            "share count implied by official IDX XBRL profit and basic EPS."
        )
    snapshot = _signed_snapshot(
        snapshot_id=str(uuid4()),
        effective_at=effective_at,
        created_at=datetime.now(timezone.utc).isoformat(),
        model_version=model_version,
        model_status="CANDIDATE",
        constituents=sorted(rankings),
        rankings=rankings,
        warnings=warnings,
        sources=[provenance] if provenance else [],
        formula_version=formula_version or "lq45-cross-section-v4+business-quality-v2",
    )
    write_snapshot(snapshot, output_path, allow_candidate=True)
    return snapshot


def approve_snapshot(
    candidate_path: str, output_path: str, status: str, validation_run_id: str | None
) -> ResearchSnapshot:
    raw = Path(candidate_path).read_bytes()
    if candidate_path.endswith(".gz"):
        import gzip

        raw = gzip.decompress(raw)
    candidate = ResearchSnapshot(**json.loads(raw))
    candidate.validate(approved_only=False)
    if candidate.model_status != "CANDIDATE":
        raise ValueError("Only a candidate snapshot may be approved.")
    if status == "VALIDATED_RESEARCH" and not validation_run_id:
        raise ValueError("VALIDATED_RESEARCH requires a persisted validation run ID.")
    approved = _signed_snapshot(
        **{
            **candidate.unsigned_dict(),
            "model_status": status,
            "validation_run_id": validation_run_id,
        }
    )
    write_snapshot(approved, output_path)
    return approved


def ingest_manifest(
    path: str, *, archive_directory: str | None, use_r2: bool
) -> list[dict]:
    repository = None
    if os.getenv("SUPABASE_WRITER_DATABASE_URL"):
        from storage.database import connect_from_env
        from storage.repository import SnapshotRepository

        repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    report = []
    for source in read_manifest(path):
        artifact_id = None
        try:
            artifact, body = acquire_artifact(
                provider=source["provider"],
                source_class=source.get("source_class", "official"),
                artifact_type=source["artifact_type"],
                source_url=source["source_url"],
                published_at=source.get("published_at"),
                archive_directory=archive_directory,
            )
            if repository:
                artifact_id = repository.register_source_artifact(
                    artifact.to_dict(), parse_status="PENDING"
                )
            if use_r2:
                upload_to_r2(
                    artifact.object_key or artifact.checksum,
                    body,
                    content_type=artifact.content_type,
                )
            records = parse_canonical_csv(artifact.artifact_type, body)
            if repository:
                repository.import_canonical_records(
                    artifact.artifact_type,
                    records,
                    source_class=artifact.source_class,
                )
                if artifact_id is not None:
                    repository.set_artifact_status(artifact_id, "ACCEPTED")
            report.append(
                {
                    **artifact.to_dict(),
                    "status": "ACCEPTED",
                    "record_count": len(records),
                }
            )
        except Exception as exc:
            if repository and artifact_id:
                repository.set_artifact_status(artifact_id, "QUARANTINED")
                repository.record_ingestion_issue(
                    artifact_id, "PARSE_OR_ARCHIVE_FAILURE", str(exc)
                )
            report.append(
                {
                    "source_url": source.get("source_url"),
                    "status": "QUARANTINED",
                    "detail": str(exc),
                }
            )
    return report


def ingest_idx_xbrl_manifest(
    path: str, *, archive_directory: str | None, use_r2: bool
) -> list[dict]:
    """Acquire official IDX instances, archive originals, and import reviewed facts."""
    payload = json.loads(Path(path).read_text())
    filings = payload.get("filings", payload) if isinstance(payload, dict) else payload
    if not isinstance(filings, list):
        raise ValueError(
            "IDX filing manifest must be a list or contain a filings list."
        )
    if not filings:
        return []
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository

    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    report = []
    required = {"ticker", "source_url", "published_at", "filing_type", "period_end"}
    for source in filings:
        artifact_id = None
        try:
            missing = required - set(source)
            if missing:
                raise ValueError(
                    f"IDX filing manifest entry is missing: {', '.join(sorted(missing))}."
                )
            validate_official_idx_url(source["source_url"])
            artifact, body = acquire_artifact(
                provider="IDX",
                source_class="official",
                artifact_type="idx_xbrl_instance",
                source_url=source["source_url"],
                published_at=source["published_at"],
                archive_directory=archive_directory,
            )
            artifact_id = repository.register_source_artifact(
                artifact.to_dict(), parse_status="PENDING"
            )
            if use_r2:
                upload_to_r2(
                    artifact.object_key or artifact.checksum,
                    body,
                    content_type=artifact.content_type or "application/zip",
                )
            parsed = parse_idx_xbrl(
                body,
                ticker=source["ticker"],
                source_url=source["source_url"],
                published_at=source["published_at"],
                filing_type=source["filing_type"],
                filing_period_end=source["period_end"],
                document_checksum=artifact.checksum,
                object_key=artifact.object_key or artifact.checksum,
                audit_status=source.get("audit_status", "UNAUDITED"),
                restatement_version=int(source.get("restatement_version", 1)),
            )
            imported = repository.import_canonical_records(
                "statement_facts_csv",
                parsed["facts"],
                source_class="official",
            )
            profile_status = "UNVERIFIED"
            profile_label = parsed["diagnostics"].get("industry") or parsed[
                "diagnostics"
            ].get("sector")
            if profile_label:
                try:
                    profile_status = repository.verify_issuer_profile(
                        source["ticker"],
                        sector=profile_label,
                        source_url=source["source_url"],
                        checksum=artifact.checksum,
                        available_at=source["published_at"],
                    ).upper()
                except ValueError as profile_error:
                    repository.record_ingestion_issue(
                        artifact_id,
                        "ISSUER_PROFILE_REVIEW_REQUIRED",
                        str(profile_error),
                    )
            repository.set_artifact_status(artifact_id, "ACCEPTED")
            report.append(
                {
                    **artifact.to_dict(),
                    "ticker": source["ticker"],
                    "status": "ACCEPTED",
                    "record_count": imported,
                    "issuer_profile": profile_status,
                    "diagnostics": parsed["diagnostics"],
                }
            )
        except Exception as exc:
            if artifact_id:
                repository.set_artifact_status(artifact_id, "QUARANTINED")
                repository.record_ingestion_issue(
                    artifact_id, "IDX_XBRL_FAILURE", str(exc)
                )
            report.append(
                {
                    "ticker": source.get("ticker"),
                    "source_url": source.get("source_url"),
                    "status": "QUARANTINED",
                    "detail": str(exc),
                }
            )
    return report


def discover_idx_manifest(
    output_path: str,
    *,
    as_of: str,
    year: int,
    period: str,
    annual_start_year: int | None = None,
    annual_end_year: int | None = None,
) -> dict:
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository

    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    issuers = repository.constituent_issuers_as_of("LQ45", as_of.split("T", 1)[0])
    if len(issuers) != 45:
        raise ValueError(
            f"Official discovery requires exactly 45 effective LQ45 issuers; found {len(issuers)}."
        )
    manifest = discover_idx_xbrl_manifest(
        [issuer["ticker"] for issuer in issuers],
        year=year,
        period=period,
        annual_start_year=annual_start_year,
        annual_end_year=annual_end_year,
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(strict_json_dumps(manifest, indent=2))
    return manifest


def automatic_idx_period(as_of: str) -> tuple[int, str]:
    observed = pd.Timestamp(as_of)
    year, month = int(observed.year), int(observed.month)
    if month >= 11:
        return year, "tw3"
    if month >= 8:
        return year, "tw2"
    if month >= 5:
        return year, "tw1"
    return year - 1, "tw3"


def discovery_blockers(discovery: dict) -> list[str]:
    """Only missing current evidence blocks discovery.

    Historical manifests intentionally use today's LQ45 universe. Newer IPOs
    and spin-offs may have no filing in an earlier year, so annual gaps remain
    visible for human review but must not prevent creation of the review PR.
    """
    return list(discovery.get("current_period_missing") or [])


def candidate_readiness(snapshot: ResearchSnapshot) -> dict:
    """Enforce the scan's quant gate before a reviewed candidate can publish."""
    snapshot.validate(approved_only=False)
    expected = 45

    def finite_value(row: dict, key: str, fallback: str | None = None) -> float | None:
        value = row.get(key)
        if value is None and fallback:
            value = row.get(fallback)
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def row_eligible(row: dict) -> bool:
        factor_coverage = finite_value(row, "factor_coverage_pct", "coverage_pct") or 0
        raw_coverage = (
            finite_value(row, "raw_component_coverage_pct", "coverage_pct") or 0
        )
        return (
            finite_value(row, "composite_percentile") is not None
            and factor_coverage >= 75.0
            and raw_coverage >= 70.0
        )

    eligible = [
        ticker for ticker, row in snapshot.rankings.items() if row_eligible(row)
    ]
    scored = [
        ticker
        for ticker, row in snapshot.rankings.items()
        if finite_value(row, "composite_percentile") is not None
    ]
    factor_covered = [
        ticker
        for ticker, row in snapshot.rankings.items()
        if (finite_value(row, "factor_coverage_pct", "coverage_pct") or 0) >= 75.0
    ]
    raw_covered = [
        ticker
        for ticker, row in snapshot.rankings.items()
        if (finite_value(row, "raw_component_coverage_pct", "coverage_pct") or 0)
        >= 70.0
    ]
    factor_score_counts = {
        factor: sum(
            finite_value(row, factor) is not None for row in snapshot.rankings.values()
        )
        for factor in ("value", "quality", "momentum", "low_volatility")
    }
    factor_coverage_values = sorted(
        {
            value
            for row in snapshot.rankings.values()
            if (value := finite_value(row, "factor_coverage_pct", "coverage_pct"))
            is not None
        }
    )
    raw_coverage_values = sorted(
        {
            value
            for row in snapshot.rankings.values()
            if (
                value := finite_value(row, "raw_component_coverage_pct", "coverage_pct")
            )
            is not None
        }
    )
    required_eligible = math.ceil(expected * 0.90)
    accuracy_v2 = "business-quality-v2" in str(snapshot.formula_version)
    verified_profiles = [
        ticker
        for ticker, row in snapshot.rankings.items()
        if str(row.get("issuer_profile") or "").upper() in {"GENERAL", "BANK"}
        and row.get("issuer_profile_checksum")
    ]
    business_scored = [
        ticker
        for ticker, row in snapshot.rankings.items()
        if finite_value(row, "business_score") is not None
    ]
    checks = {
        "candidate_status": snapshot.model_status == "CANDIDATE",
        "exact_lq45_universe": len(snapshot.constituents) == expected,
        "rankings_match_constituents": set(snapshot.rankings)
        == set(snapshot.constituents),
        "eligible_quant_rows": len(eligible) >= required_eligible,
    }
    if accuracy_v2:
        checks["verified_issuer_profiles"] = len(verified_profiles) == expected
        checks["eligible_business_rows"] = len(business_scored) >= required_eligible
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "constituent_count": len(snapshot.constituents),
        "eligible_count": len(eligible),
        "scored_count": len(scored),
        "factor_coverage_75_count": len(factor_covered),
        "raw_coverage_70_count": len(raw_covered),
        "factor_score_counts": factor_score_counts,
        "factor_coverage_values": factor_coverage_values,
        "raw_coverage_values": raw_coverage_values,
        "verified_profile_count": len(verified_profiles),
        "business_scored_count": len(business_scored),
        "required_eligible_count": required_eligible,
    }


def check_candidate(path: str) -> dict:
    raw = Path(path).read_bytes()
    if path.endswith(".gz"):
        import gzip

        raw = gzip.decompress(raw)
    snapshot = ResearchSnapshot(**json.loads(raw))
    readiness = candidate_readiness(snapshot)
    if not readiness["ready"]:
        failed = ", ".join(
            key for key, passed in readiness["checks"].items() if not passed
        )
        raise ValueError(
            f"Candidate readiness failed: {failed}. Details: {strict_json_dumps(readiness)}"
        )
    return readiness


def publish_reviewed_shadow(candidate_path: str, output_path: str) -> dict:
    """Publish only a candidate already reviewed and merged to the trusted branch."""
    raw = Path(candidate_path).read_bytes()
    if candidate_path.endswith(".gz"):
        import gzip

        raw = gzip.decompress(raw)
    candidate = ResearchSnapshot(**json.loads(raw))
    readiness = candidate_readiness(candidate)
    if not readiness["ready"]:
        failed = ", ".join(
            key for key, passed in readiness["checks"].items() if not passed
        )
        raise ValueError(
            f"Candidate is not publishable: {failed}. Details: {strict_json_dumps(readiness)}"
        )
    approved = approve_snapshot(candidate_path, output_path, "SHADOW", None)
    snapshot_id = publish_snapshot(output_path)
    return {
        "published": True,
        "snapshot_id": snapshot_id,
        "readiness": readiness,
        "checksum": approved.checksum,
    }


def backup_database(output_path: str, upload: bool) -> None:
    database_url = os.getenv("SUPABASE_WRITER_DATABASE_URL")
    if not database_url:
        raise RuntimeError("SUPABASE_WRITER_DATABASE_URL is required.")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--file",
            str(destination),
            database_url,
        ],
        check=True,
    )
    if upload:
        key = os.getenv("BACKUP_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError(
                "BACKUP_ENCRYPTION_KEY is required before a database backup may leave the runner."
            )
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise RuntimeError(
                "Install requirements-jobs.txt for encrypted backups."
            ) from exc
        encrypted = Fernet(key.encode()).encrypt(destination.read_bytes())
        upload_to_r2(
            f"backups/{destination.name}.fernet",
            encrypted,
            content_type="application/octet-stream",
        )


def publish_snapshot(path: str) -> str:
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository

    return SnapshotRepository(
        lambda: connect_from_env(writer=True)
    ).publish_quant_snapshot(load_snapshot(path))


def build_daily_scan(output_path: str, *, use_r2: bool = False) -> dict:
    """Build and atomically publish the full-LQ45 EOD scan outside Railway."""
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository

    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    run: dict[str, Any] = {
        "id": run_id,
        "job_type": "DAILY_SCAN",
        "workflow_run_id": os.getenv("GITHUB_RUN_ID"),
        "started_at": started_at,
        "status": "RUNNING",
        "metrics": {},
    }
    repository.record_research_job(run)

    archive = None
    if use_r2:

        def archive(key, body):
            return upload_to_r2(key, body, content_type="application/gzip")

    try:
        snapshot = build_full_lq45_scan(repository, archive_callback=archive)
        payload = snapshot.to_dict()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(strict_json_dumps(payload, indent=2))
        if snapshot.mode == "UNAVAILABLE":
            repository.record_research_job(
                {
                    **run,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "status": "DEGRADED",
                    "output_checksum": snapshot.checksum,
                    "metrics": {
                        "mode": snapshot.mode,
                        "coverage_pct": snapshot.universe_coverage_pct,
                    },
                }
            )
            return {"published": False, "snapshot": payload}
        snapshot_id = repository.publish_scan_snapshot(snapshot)
        repository.record_research_job(
            {
                **run,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "status": "SUCCEEDED",
                "output_checksum": snapshot.checksum,
                "metrics": {
                    "mode": snapshot.mode,
                    "coverage_pct": snapshot.universe_coverage_pct,
                    "candidate_count": len(snapshot.candidates),
                },
            }
        )
        return {"published": True, "snapshot_id": snapshot_id, "snapshot": payload}
    except Exception as exc:
        repository.record_research_job(
            {
                **run,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "status": "FAILED",
                "error_type": type(exc).__name__,
            }
        )
        raise


def _required_migrations() -> list[str]:
    return sorted(
        path.name.removesuffix(".up.sql")
        for path in Path("storage/migrations").glob("*.up.sql")
    )


def _write_job_report(path: str, report: dict) -> bool:
    destination = Path(path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(strict_json_dumps(report, indent=2))
    except Exception:
        return False
    return True


def _report_with_outcome(report: dict, result: JobOutcome) -> dict:
    """Attach the stable contract while retaining legacy status consumers."""
    payload = dict(report)
    payload["outcome"] = result.to_dict()
    # Existing dashboards use WAITING/FAILED. The typed outcome is canonical;
    # this compatibility field can be removed after dashboard migration.
    payload["status"] = (
        "WAITING"
        if result.outcome is Outcome.WAITING
        else "FAILED"
        if result.outcome
        in {Outcome.UNAVAILABLE, Outcome.POLICY_GATE, Outcome.INFRASTRUCTURE}
        else result.outcome.value
    )
    return payload


def _report_write_failure(report: dict, repository, base_run: dict) -> dict:
    """Emit one redacted infrastructure result without retrying the bad path."""
    result = outcome(
        Outcome.INFRASTRUCTURE,
        "REPORT_WRITE_FAILED",
        "report",
        retryable=False,
        summary="The research report could not be written.",
        action="Inspect the runner workspace and rerun the job.",
    )
    fallback = _report_with_outcome(
        {"status": "RUNNING", "started_at": report.get("started_at"), "stages": {}},
        result,
    )
    print(
        strict_json_dumps(
            {key: value for key, value in fallback.items() if key != "stages"}
        )
    )
    fallback["_stdout_emitted"] = True
    try:
        repository.record_research_job(
            {
                **base_run,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "status": result.persisted_status,
                "metrics": {"outcome": result.to_dict()},
                "error_type": result.code,
            }
        )
    except Exception:
        pass
    return fallback


def _infrastructure(
    stage: str, code: str, *, retryable: bool = False, details: dict | None = None
) -> OutcomeFailure:
    return OutcomeFailure(
        outcome(
            Outcome.INFRASTRUCTURE,
            code,
            stage,
            retryable=retryable,
            summary="Research infrastructure is not ready for this refresh attempt.",
            action="Inspect the redacted stage result and incident record.",
            details=details,
        )
    )


def _preflight(repository, required: list[str]) -> dict:
    """Use the explicit ledger preflight, with compatibility for older fakes."""
    if hasattr(repository, "preflight_schema_migrations"):
        return repository.preflight_schema_migrations(required)
    applied = set(repository.applied_schema_migrations())
    missing = [name for name in required if name not in applied]
    return {
        "ok": not missing,
        "code": "REQUIRED_MIGRATION_MISSING" if missing else "LEDGER_READY",
        "missing_versions": missing,
    }


def _redacted_market_summary(summary: dict) -> dict:
    """Keep operational metrics while excluding provider detail and URLs."""
    allowed = {
        "ready",
        "session_date",
        "on_date",
        "coverage_pct",
        "membership_count",
        "imported_count",
        "session_age",
    }
    return {key: summary.get(key) for key in allowed if key in summary}


def _is_genuine_current_session_wait(market: dict) -> bool:
    """Only a complete, current universe may use the retryable timing outcome."""
    try:
        if int(market.get("membership_count", 0)) != 45:
            return False
        if market.get("session_age") is not None and int(market["session_age"]) > 1:
            return False
        return (
            market.get("session_date") == market.get("on_date")
            and 0.0 < float(market.get("coverage_pct", 0)) < 90.0
        )
    except (TypeError, ValueError):
        return False


def refresh_market_history(output_path: str, *, now: datetime | None = None) -> dict:
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository

    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    result = refresh_lq45_market_history(repository, now=now)
    summary = market_refresh_summary(result)
    _write_job_report(output_path, summary)
    return summary


def run_daily_research(
    output_path: str,
    *,
    release_path: str = DEFAULT_RELEASE_PATH,
    use_r2: bool = False,
    final_attempt: bool = False,
    now: datetime | None = None,
) -> dict:
    """Refresh, gate, sign and publish one approved SHADOW release."""
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository

    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    run_id = str(uuid4())
    started_at = observed.isoformat()
    base_run: dict[str, Any] = {
        "id": run_id,
        "job_type": "DAILY_RESEARCH",
        "workflow_run_id": os.getenv("GITHUB_RUN_ID"),
        "started_at": started_at,
        "status": "RUNNING",
        "metrics": {},
    }
    report: dict[str, Any] = {
        "status": "RUNNING",
        "started_at": started_at,
        "stages": {},
    }
    try:
        if not os.getenv("SUPABASE_WRITER_DATABASE_URL"):
            raise _infrastructure("preflight", "CONFIGURATION_MISSING")
        if not os.getenv("SNAPSHOT_ED25519_PRIVATE_KEY"):
            raise _infrastructure("preflight", "CONFIGURATION_MISSING")
        release = load_release(release_path)
        provenance = release_provenance(release_path)
        preflight = _preflight(repository, _required_migrations())
        if not preflight.get("ok"):
            raise _infrastructure(
                "preflight",
                preflight.get("code", "LEDGER_DATABASE_ERROR"),
                retryable=preflight.get("code")
                in {"LEDGER_TIMEOUT", "LEDGER_DATABASE_ERROR"},
                details={"missing_versions": preflight.get("missing_versions", [])},
            )
        repository.record_research_job(base_run)
        report.update(
            {
                "release_id": provenance["release_id"],
                "calculation_digest": provenance["calculation_digest"],
                "git_commit": provenance["git_commit"],
            }
        )
        report["stages"]["preflight"] = {
            "status": "SUCCEEDED",
            "missing_migrations": [],
        }

        market = refresh_lq45_market_history(repository, now=observed)
        market_summary = market_refresh_summary(market)
        safe_market_summary = _redacted_market_summary(market_summary)
        report["stages"]["market"] = safe_market_summary
        report["session_date"] = market_summary["session_date"]
        if not market["ready"]:
            waiting = not final_attempt and _is_genuine_current_session_wait(market)
            result = outcome(
                Outcome.WAITING if waiting else Outcome.UNAVAILABLE,
                "MARKET_SESSION_NOT_READY" if waiting else "EVIDENCE_UNAVAILABLE",
                "market",
                retryable=waiting,
                summary=(
                    "The current session is not complete yet."
                    if waiting
                    else "Required completed-session evidence is unavailable."
                ),
                action=(
                    "Wait for a completed session and run the next scheduled attempt."
                    if waiting
                    else "Complete required ingestion and rerun the refresh."
                ),
                details={
                    "session_date": safe_market_summary.get("session_date"),
                    "coverage_pct": safe_market_summary.get("coverage_pct"),
                },
            )
            report = _report_with_outcome(report, result)
            if not _write_job_report(output_path, report):
                return _report_write_failure(report, repository, base_run)
            repository.record_research_job(
                {
                    **base_run,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "status": result.persisted_status,
                    "input_checksum": provenance["calculation_digest"],
                    "metrics": {
                        "outcome": result.to_dict(),
                        "market": safe_market_summary,
                    },
                    "error_type": result.code,
                }
            )
            return report

        session_date = market["session_date"]
        provenance = release_provenance(release_path, market_session=session_date)
        latest_scan = repository.latest_scan_snapshot()
        latest_scan_release = (
            (latest_scan.source_summary or {}).get("research_release")
            if latest_scan
            else None
        ) or {}
        if (
            latest_scan
            and latest_scan.mode == "PRIMARY"
            and latest_scan.session_date == session_date
            and latest_scan_release.get("calculation_digest")
            == provenance["calculation_digest"]
        ):
            assert latest_scan is not None
            outcomes = evaluate_signal_outcomes()
            result = outcome(
                Outcome.NOOP,
                "ALREADY_CURRENT",
                "publication",
                retryable=False,
                summary="The verified primary scan is already current.",
                action="No publication was required.",
            )
            report.update(
                {
                    "quant_snapshot_id": latest_scan.quant_snapshot_id,
                    "scan_snapshot_id": latest_scan.snapshot_id,
                }
            )
            report["stages"]["outcomes"] = {"status": "SUCCEEDED", **outcomes}
            report = _report_with_outcome(report, result)
            if not _write_job_report(output_path, report):
                return _report_write_failure(report, repository, base_run)
            repository.record_research_job(
                {
                    **base_run,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "status": "SUCCEEDED",
                    "input_checksum": provenance["calculation_digest"],
                    "output_checksum": latest_scan.checksum,
                    "metrics": {
                        "outcome": result.to_dict(),
                        "session_date": session_date,
                    },
                }
            )
            return report

        latest_quant = repository.latest_approved_quant_snapshot()
        latest_release = (
            release_from_sources(latest_quant.sources if latest_quant else []) or {}
        )
        reuse_quant = bool(
            latest_quant
            and latest_release.get("calculation_digest")
            == provenance["calculation_digest"]
            and latest_release.get("market_session") == session_date
        )
        if reuse_quant:
            assert latest_quant is not None
            quant_snapshot_id = latest_quant.snapshot_id
            report["stages"]["quant"] = {
                "status": "REUSED",
                "snapshot_id": quant_snapshot_id,
            }
        else:
            with TemporaryDirectory(prefix="pasticuan-daily-") as temporary:
                candidate_path = str(Path(temporary) / "candidate.json.gz")
                approved_path = str(Path(temporary) / "approved-shadow.json.gz")
                try:
                    candidate = build_snapshot_from_database(
                        candidate_path,
                        observed.isoformat(),
                        release["model_version"],
                        provenance=provenance,
                        formula_version=release["formula_version"],
                    )
                except EvidenceUnavailable:
                    raise OutcomeFailure(
                        outcome(
                            Outcome.UNAVAILABLE,
                            "POINT_IN_TIME_EVIDENCE_UNAVAILABLE",
                            "quant",
                            retryable=True,
                            summary="Required point-in-time factor evidence is unavailable.",
                            action="Complete eligible ingestion and rerun the refresh.",
                        )
                    )
                readiness = candidate_readiness(candidate)
                if not readiness["ready"]:
                    failed = ", ".join(
                        key for key, passed in readiness["checks"].items() if not passed
                    )
                    raise OutcomeFailure(
                        outcome(
                            Outcome.POLICY_GATE,
                            "QUANT_READINESS_REJECTED",
                            "quant",
                            retryable=False,
                            summary="Candidate quant evidence did not pass the readiness policy.",
                            action="Review the failed readiness checks before rerunning.",
                            details={
                                "failed_checks": failed.split(", ") if failed else []
                            },
                        )
                    )
                approved = approve_snapshot(
                    candidate_path, approved_path, "SHADOW", None
                )
                quant_snapshot_id = repository.publish_quant_snapshot(approved)
                report["stages"]["quant"] = {
                    "status": "PUBLISHED",
                    "snapshot_id": quant_snapshot_id,
                    "checksum": approved.checksum,
                    "readiness": readiness,
                }

        archive = None
        if use_r2:

            def archive(key, body):
                return upload_to_r2(key, body, content_type="application/gzip")

        scan = build_full_lq45_scan(
            repository, market_refresh=market, archive_callback=archive
        )
        if scan.mode != "PRIMARY":
            report["partial_quant_snapshot_id"] = locals().get("quant_snapshot_id")
            raise OutcomeFailure(
                outcome(
                    Outcome.POLICY_GATE,
                    "SCAN_NOT_PRIMARY",
                    "scan",
                    retryable=False,
                    summary="The daily scan did not satisfy the PRIMARY publication gate.",
                    action="Resolve the disclosed scan gate failures before rerunning.",
                    details={
                        "mode": scan.mode,
                        "partial_quant_snapshot_id": locals().get("quant_snapshot_id"),
                    },
                )
            )
        scan_snapshot_id = repository.publish_scan_snapshot(scan)
        report["stages"]["scan"] = {
            "status": "PUBLISHED",
            "snapshot_id": scan_snapshot_id,
            "checksum": scan.checksum,
            "coverage_pct": scan.universe_coverage_pct,
            "candidate_count": len(scan.candidates),
        }
        outcomes = evaluate_signal_outcomes()
        report["stages"]["outcomes"] = {"status": "SUCCEEDED", **outcomes}
        result = outcome(
            Outcome.SUCCEEDED,
            "PUBLISHED",
            "publication",
            retryable=False,
            summary="Verified research was published successfully.",
            action="Retain the new last-good snapshot.",
        )
        report.update(
            {
                "quant_snapshot_id": quant_snapshot_id,
                "scan_snapshot_id": scan_snapshot_id,
            }
        )
        report = _report_with_outcome(report, result)
        if not _write_job_report(output_path, report):
            return _report_write_failure(report, repository, base_run)
        repository.record_research_job(
            {
                **base_run,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "status": "SUCCEEDED",
                "input_checksum": provenance["calculation_digest"],
                "output_checksum": scan.checksum,
                "metrics": {
                    "outcome": result.to_dict(),
                    "session_date": session_date,
                    "coverage_pct": scan.universe_coverage_pct,
                },
            }
        )
        return report
    except OutcomeFailure as exc:
        result = exc.result
        report = _report_with_outcome(report, result)
        if not _write_job_report(output_path, report):
            return _report_write_failure(report, repository, base_run)
        try:
            repository.record_research_job(
                {
                    **base_run,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "status": result.persisted_status,
                    "metrics": {"outcome": result.to_dict()},
                    "error_type": result.code,
                }
            )
        except Exception:
            pass
        return report
    except Exception as exc:
        result = infrastructure_failure(
            exc, next(reversed(report.get("stages", {})), "unknown")
        )
        report = _report_with_outcome(report, result)
        if not _write_job_report(output_path, report):
            return _report_write_failure(report, repository, base_run)
        try:
            repository.record_research_job(
                {
                    **base_run,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "status": result.persisted_status,
                    "metrics": {"outcome": result.to_dict()},
                    "error_type": result.code,
                }
            )
        except Exception:
            pass
        return report


def build_snapshot_from_database(
    output_path: str,
    effective_at: str,
    model_version: str,
    *,
    provenance: dict | None = None,
    formula_version: str | None = None,
) -> ResearchSnapshot:
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository

    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    frame = build_factor_inputs(repository, effective_at)
    if frame.empty:
        raise EvidenceUnavailable()
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".factor-inputs.csv")
    frame.to_csv(temporary, index=False)
    try:
        return build_snapshot(
            str(temporary),
            output_path,
            effective_at,
            model_version,
            provenance=provenance,
            formula_version=formula_version,
        )
    finally:
        temporary.unlink(missing_ok=True)


def rebuild_monthly_panel(
    start: str, end: str, scores_output: str, bars_output: str
) -> dict:
    """Reconstruct month-end ranks exclusively from facts available at each cutoff."""
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository

    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    score_rows = []
    month_ends = repository.completed_month_ends(start, end)
    for session_date in month_ends:
        as_of = f"{session_date}T16:15:00+07:00"
        frame = build_factor_inputs(repository, as_of)
        business = compute_business_scores(frame)
        if business["status"] != "AVAILABLE":
            continue
        for row in (
            business["scores"]
            .where(pd.notna(business["scores"]), None)
            .to_dict("records")
        ):
            if row.get("business_score") is not None:
                score_rows.append(
                    {
                        "rebalance_date": session_date,
                        "ticker": row["ticker"],
                        "composite_percentile": row["business_score"],
                        "coverage_pct": row["raw_fundamental_coverage_pct"],
                    }
                )
    scores = pd.DataFrame(score_rows)
    bars = pd.DataFrame(repository.validation_bars(start, end))
    if scores.empty or bars.empty:
        raise ValueError("Historical point-in-time scores or bars are unavailable.")
    Path(scores_output).parent.mkdir(parents=True, exist_ok=True)
    Path(bars_output).parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(scores_output, index=False)
    bars.to_csv(bars_output, index=False)
    return {
        "months": len(month_ends),
        "score_rows": len(scores),
        "bar_rows": len(bars),
        "scores_checksum": hashlib.sha256(Path(scores_output).read_bytes()).hexdigest(),
        "bars_checksum": hashlib.sha256(Path(bars_output).read_bytes()).hexdigest(),
    }


def validate_quant(
    scores_path: str,
    bars_path: str,
    output_path: str,
    *,
    persist: bool = False,
    model_version: str = "lq45-factor-v1",
    deterministic_rebuild: bool = False,
) -> dict:
    scores, bars = pd.read_csv(scores_path), pd.read_csv(bars_path)
    costs = BrokerCostProfile(
        os.getenv("BROKER_COST_PROFILE", "validation"),
        float(os.getenv("BROKER_BUY_COMMISSION", ".0015")),
        float(os.getenv("BROKER_SELL_COMMISSION", ".0025")),
        float(os.getenv("BROKER_SELL_LEVY", ".001")),
        float(os.getenv("BROKER_HALF_SPREAD", ".0005")),
        float(os.getenv("BROKER_SLIPPAGE_BPS", "5")),
    )
    dates = sorted(
        pd.to_datetime(scores["rebalance_date"]).dt.tz_localize(None).unique()
    )
    holdout_dates = dates[-25:] if len(dates) >= 25 else dates
    holdout = scores[
        pd.to_datetime(scores["rebalance_date"])
        .dt.tz_localize(None)
        .isin(holdout_dates)
    ]
    result = backtest_monthly_quant(holdout, bars, broker_costs=costs)
    if result.get("status") != "AVAILABLE":
        raise ValueError(result.get("reason", "Quant validation unavailable."))
    high_cost = BrokerCostProfile(
        f"{costs.name}-2x",
        costs.buy_commission * 2,
        costs.sell_commission * 2,
        costs.sell_tax_levy * 2,
        costs.half_spread * 2,
        costs.slippage_bps * 2,
    )
    stressed = backtest_monthly_quant(holdout, bars, broker_costs=high_cost)
    delayed = backtest_monthly_quant(
        holdout, bars, broker_costs=costs, execution_delay_sessions=1
    )
    usable_years = ((max(dates) - min(dates)).days / 365.25) if len(dates) > 1 else 0
    acceptance = assess_holdout(
        result,
        usable_years=usable_years,
        holdout_months=max(0, len(holdout_dates) - 1),
        higher_cost_positive=(stressed.get("net_excess_cagr") or 0) > 0,
        delayed_entry_positive=(delayed.get("net_excess_cagr") or 0) > 0,
        deterministic_rebuild=deterministic_rebuild,
    )
    summary = {
        key: value
        for key, value in result.items()
        if key not in {"monthly", "observations"}
    }
    payload = {"metrics": summary, "acceptance": acceptance}
    encoded = strict_json_dumps(payload, indent=2).encode()
    Path(output_path).write_bytes(encoded)
    if persist:
        from storage.database import connect_from_env
        from storage.repository import SnapshotRepository

        input_checksum = hashlib.sha256(
            Path(scores_path).read_bytes() + Path(bars_path).read_bytes()
        ).hexdigest()
        run_id = str(uuid4())
        persisted = SnapshotRepository(
            lambda: connect_from_env(writer=True)
        ).save_validation_run(
            run_id=run_id,
            model_version=model_version,
            input_checksum=input_checksum,
            metrics=summary,
            acceptance=acceptance,
            holdout_start=str(pd.Timestamp(holdout_dates[0]).date())
            if holdout_dates
            else None,
            holdout_end=str(pd.Timestamp(holdout_dates[-1]).date())
            if holdout_dates
            else None,
            output_checksum=hashlib.sha256(encoded).hexdigest(),
        )
        payload["validation_run_id"] = persisted
    return payload


def evaluate_signal_outcomes() -> dict:
    from analysis.outcomes import evaluate_signal_window
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository

    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    saved = 0
    pending = 0
    for signal in repository.pending_signal_windows():
        for horizon in signal["horizons"]:
            outcome = evaluate_signal_window(signal, horizon)
            if outcome is None:
                pending += 1
                continue
            repository.save_signal_outcome(outcome)
            saved += 1
    return {"saved": saved, "pending": pending, "formula_version": "signal-outcomes-v1"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pasticuan-research")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-snapshot")
    build.add_argument("--input", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--effective-at", required=True)
    build.add_argument("--model-version", default="lq45-factor-v1")
    approve = sub.add_parser("approve-snapshot")
    approve.add_argument("--candidate", required=True)
    approve.add_argument("--output", required=True)
    approve.add_argument(
        "--status", choices=["SHADOW", "VALIDATED_RESEARCH"], default="SHADOW"
    )
    approve.add_argument("--validation-run-id")
    build_db = sub.add_parser("build-snapshot-from-database")
    build_db.add_argument("--output", required=True)
    build_db.add_argument("--effective-at", required=True)
    build_db.add_argument("--model-version", default="lq45-factor-v1")
    ingest = sub.add_parser("ingest-manifest")
    ingest.add_argument("--manifest", required=True)
    ingest.add_argument("--report", required=True)
    ingest.add_argument("--archive-directory")
    ingest.add_argument("--r2", action="store_true")
    ingest_idx = sub.add_parser("ingest-idx-xbrl")
    ingest_idx.add_argument("--manifest", required=True)
    ingest_idx.add_argument("--report", required=True)
    ingest_idx.add_argument("--archive-directory")
    ingest_idx.add_argument("--r2", action="store_true")
    discover_idx = sub.add_parser("discover-idx-xbrl")
    discover_idx.add_argument("--output", required=True)
    discover_idx.add_argument("--as-of", required=True)
    discover_idx.add_argument("--year", type=int)
    discover_idx.add_argument(
        "--period", default="auto", choices=["auto", "tw1", "tw2", "tw3"]
    )
    discover_idx.add_argument("--annual-start-year", type=int)
    discover_idx.add_argument("--annual-end-year", type=int)
    backup = sub.add_parser("backup")
    backup.add_argument("--output", required=True)
    backup.add_argument("--r2", action="store_true")
    publish = sub.add_parser("publish-snapshot")
    publish.add_argument("--snapshot", required=True)
    publish_shadow = sub.add_parser("publish-reviewed-shadow")
    publish_shadow.add_argument("--candidate", required=True)
    publish_shadow.add_argument("--output", required=True)
    check = sub.add_parser("check-candidate")
    check.add_argument("--snapshot", required=True)
    validate = sub.add_parser("validate-quant")
    validate.add_argument("--scores", required=True)
    validate.add_argument("--bars", required=True)
    validate.add_argument("--output", required=True)
    validate.add_argument("--persist", action="store_true")
    validate.add_argument("--model-version", default="lq45-factor-v1")
    validate.add_argument("--deterministic-rebuild", action="store_true")
    daily_scan = sub.add_parser("build-daily-scan")
    daily_scan.add_argument("--output", required=True)
    daily_scan.add_argument("--r2", action="store_true")
    refresh_market = sub.add_parser("refresh-market-history")
    refresh_market.add_argument("--output", required=True)
    daily = sub.add_parser("run-daily-research")
    daily.add_argument("--output", required=True)
    daily.add_argument("--release", default=DEFAULT_RELEASE_PATH)
    daily.add_argument("--r2", action="store_true")
    daily.add_argument("--final-attempt", action="store_true")
    check_release = sub.add_parser("check-research-release")
    check_release.add_argument("--release", default=DEFAULT_RELEASE_PATH)
    check_release.add_argument("--base-ref")
    rebuild = sub.add_parser("rebuild-monthly-panel")
    rebuild.add_argument("--start", required=True)
    rebuild.add_argument("--end", required=True)
    rebuild.add_argument("--scores-output", required=True)
    rebuild.add_argument("--bars-output", required=True)
    sub.add_parser("evaluate-signal-outcomes")
    args = parser.parse_args(argv)
    if args.command == "build-snapshot":
        try:
            build_snapshot(
                args.input, args.output, args.effective_at, args.model_version
            )
        except EvidenceUnavailable:
            print(
                strict_json_dumps(
                    outcome(
                        Outcome.UNAVAILABLE,
                        "POINT_IN_TIME_EVIDENCE_UNAVAILABLE",
                        "quant",
                        retryable=True,
                        summary="Required point-in-time factor evidence is unavailable.",
                        action="Complete eligible ingestion and rerun the refresh.",
                    ).to_dict()
                )
            )
            return 20
    elif args.command == "approve-snapshot":
        approve_snapshot(
            args.candidate, args.output, args.status, args.validation_run_id
        )
    elif args.command == "build-snapshot-from-database":
        try:
            build_snapshot_from_database(
                args.output, args.effective_at, args.model_version
            )
        except EvidenceUnavailable:
            print(
                strict_json_dumps(
                    outcome(
                        Outcome.UNAVAILABLE,
                        "POINT_IN_TIME_EVIDENCE_UNAVAILABLE",
                        "quant",
                        retryable=True,
                        summary="Required point-in-time factor evidence is unavailable.",
                        action="Complete eligible ingestion and rerun the refresh.",
                    ).to_dict()
                )
            )
            return 20
    elif args.command == "ingest-manifest":
        report = ingest_manifest(
            args.manifest, archive_directory=args.archive_directory, use_r2=args.r2
        )
        Path(args.report).write_text(strict_json_dumps(report, indent=2))
        if any(item["status"] == "QUARANTINED" for item in report):
            return 2
    elif args.command == "ingest-idx-xbrl":
        report = ingest_idx_xbrl_manifest(
            args.manifest,
            archive_directory=args.archive_directory,
            use_r2=args.r2,
        )
        Path(args.report).write_text(strict_json_dumps(report, indent=2))
        if any(item["status"] == "QUARANTINED" for item in report):
            return 2
    elif args.command == "discover-idx-xbrl":
        year, period = (
            automatic_idx_period(args.as_of)
            if args.period == "auto"
            else (args.year or pd.Timestamp(args.as_of).year, args.period)
        )
        manifest = discover_idx_manifest(
            args.output,
            as_of=args.as_of,
            year=year,
            period=period,
            annual_start_year=args.annual_start_year,
            annual_end_year=args.annual_end_year,
        )
        missing = discovery_blockers(manifest["discovery"])
        print(strict_json_dumps(manifest["discovery"]))
        if missing:
            return 2
    elif args.command == "backup":
        backup_database(args.output, args.r2)
    elif args.command == "publish-snapshot":
        print(publish_snapshot(args.snapshot))
    elif args.command == "publish-reviewed-shadow":
        print(strict_json_dumps(publish_reviewed_shadow(args.candidate, args.output)))
    elif args.command == "check-candidate":
        print(strict_json_dumps(check_candidate(args.snapshot)))
    elif args.command == "validate-quant":
        result = validate_quant(
            args.scores,
            args.bars,
            args.output,
            persist=args.persist,
            model_version=args.model_version,
            deterministic_rebuild=args.deterministic_rebuild,
        )
        print(strict_json_dumps(result))
    elif args.command == "build-daily-scan":
        result = build_daily_scan(args.output, use_r2=args.r2)
        snapshot = result.get("snapshot") or {}
        summary = {key: value for key, value in result.items() if key != "snapshot"}
        summary.update(
            {
                "mode": snapshot.get("mode"),
                "session_date": snapshot.get("session_date"),
                "universe_coverage_pct": snapshot.get("universe_coverage_pct"),
                "warnings": snapshot.get("warnings", []),
                "excluded_count": len(snapshot.get("excluded", [])),
            }
        )
        print(strict_json_dumps(summary))
        if not result["published"]:
            return 2
    elif args.command == "refresh-market-history":
        result = refresh_market_history(args.output)
        print(strict_json_dumps(result))
        if not result["ready"]:
            return 2
    elif args.command == "run-daily-research":
        result = run_daily_research(
            args.output,
            release_path=args.release,
            use_r2=args.r2,
            final_attempt=args.final_attempt,
        )
        if not result.pop("_stdout_emitted", False):
            print(
                strict_json_dumps(
                    {key: value for key, value in result.items() if key != "stages"}
                )
            )
        return int(result.get("outcome", {}).get("exit_code", 2))
    elif args.command == "check-research-release":
        result = release_provenance(args.release)
        if args.base_ref and set(args.base_ref) != {"0"}:
            result["change_policy"] = check_release_change(args.base_ref, args.release)
        print(strict_json_dumps(result))
    elif args.command == "rebuild-monthly-panel":
        result = rebuild_monthly_panel(
            args.start, args.end, args.scores_output, args.bars_output
        )
        print(strict_json_dumps(result))
    elif args.command == "evaluate-signal-outcomes":
        print(strict_json_dumps(evaluate_signal_outcomes()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
