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
from uuid import uuid4

import pandas as pd

from analysis.quant import compute_cross_sectional_factors
from analysis.business import compute_business_scores
from analysis.backtest import BrokerCostProfile
from analysis.quant_backtest import assess_holdout, backtest_monthly_quant
from analysis.factor_dataset import build_factor_inputs
from analysis.scan_v2 import build_full_lq45_scan
from analysis.snapshots import ResearchSnapshot, load_snapshot, write_snapshot
from data.ingestion import acquire_artifact, read_manifest, upload_to_r2
from data.parsers import parse_canonical_csv
from data.idx_xbrl import parse_idx_xbrl, validate_official_idx_url
from data.idx_reports import discover_idx_xbrl_manifest


def _signed_snapshot(**values) -> ResearchSnapshot:
    base = ResearchSnapshot(**values)
    return ResearchSnapshot(**{**base.unsigned_dict(), "checksum": base.calculated_checksum()})


def build_snapshot(input_path: str, output_path: str, effective_at: str, model_version: str) -> ResearchSnapshot:
    frame = pd.read_csv(input_path)
    result = compute_cross_sectional_factors(
        frame, as_of=effective_at, min_universe=10, allow_global_fallback=True,
    )
    if result["status"] != "AVAILABLE":
        raise ValueError(result["reason"])
    business = compute_business_scores(frame)
    business_map = {}
    if business["status"] == "AVAILABLE":
        business_map = {
            str(row["ticker"]).upper().replace(".JK", ""): row
            for row in business["scores"].where(pd.notna(business["scores"]), None).to_dict("records")
        }
    rankings = {}
    for row in result["scores"].where(pd.notna(result["scores"]), None).to_dict("records"):
        ticker = str(row.pop("ticker")).upper().replace(".JK", "")
        rankings[ticker] = {**row, **{key: value for key, value in business_map.get(ticker, {}).items()
                                     if key != "ticker"}}
    warnings = list(result.get("warnings", []))
    if "share_count_source" in frame and (frame["share_count_source"] == "idx_xbrl_implied_weighted_average").any():
        warnings.append(
            "Where official period-end shares were unavailable, market cap uses the weighted-average "
            "share count implied by official IDX XBRL profit and basic EPS."
        )
    snapshot = _signed_snapshot(
        snapshot_id=str(uuid4()), effective_at=effective_at,
        created_at=datetime.now(timezone.utc).isoformat(), model_version=model_version,
        model_status="CANDIDATE", constituents=sorted(rankings), rankings=rankings,
        warnings=warnings, formula_version="lq45-cross-section-v4+business-quality-v1",
    )
    write_snapshot(snapshot, output_path, allow_candidate=True)
    return snapshot


def approve_snapshot(candidate_path: str, output_path: str, status: str, validation_run_id: str | None) -> ResearchSnapshot:
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
    approved = _signed_snapshot(**{
        **candidate.unsigned_dict(), "model_status": status,
        "validation_run_id": validation_run_id,
    })
    write_snapshot(approved, output_path)
    return approved


def ingest_manifest(path: str, *, archive_directory: str | None, use_r2: bool) -> list[dict]:
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
                provider=source["provider"], source_class=source.get("source_class", "official"),
                artifact_type=source["artifact_type"], source_url=source["source_url"],
                published_at=source.get("published_at"), archive_directory=archive_directory,
            )
            if repository:
                artifact_id = repository.register_source_artifact(artifact.to_dict(), parse_status="PENDING")
            if use_r2:
                upload_to_r2(artifact.object_key or artifact.checksum, body, content_type=artifact.content_type)
            records = parse_canonical_csv(artifact.artifact_type, body)
            if repository:
                repository.import_canonical_records(
                    artifact.artifact_type, records, source_class=artifact.source_class,
                )
                repository.set_artifact_status(artifact_id, "ACCEPTED")
            report.append({**artifact.to_dict(), "status": "ACCEPTED", "record_count": len(records)})
        except Exception as exc:
            if repository and artifact_id:
                repository.set_artifact_status(artifact_id, "QUARANTINED")
                repository.record_ingestion_issue(artifact_id, "PARSE_OR_ARCHIVE_FAILURE", str(exc))
            report.append({"source_url": source.get("source_url"), "status": "QUARANTINED", "detail": str(exc)})
    return report


def ingest_idx_xbrl_manifest(path: str, *, archive_directory: str | None, use_r2: bool) -> list[dict]:
    """Acquire official IDX instances, archive originals, and import reviewed facts."""
    payload = json.loads(Path(path).read_text())
    filings = payload.get("filings", payload) if isinstance(payload, dict) else payload
    if not isinstance(filings, list):
        raise ValueError("IDX filing manifest must be a list or contain a filings list.")
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
                raise ValueError(f"IDX filing manifest entry is missing: {', '.join(sorted(missing))}.")
            validate_official_idx_url(source["source_url"])
            artifact, body = acquire_artifact(
                provider="IDX", source_class="official", artifact_type="idx_xbrl_instance",
                source_url=source["source_url"], published_at=source["published_at"],
                archive_directory=archive_directory,
            )
            artifact_id = repository.register_source_artifact(artifact.to_dict(), parse_status="PENDING")
            if use_r2:
                upload_to_r2(artifact.object_key or artifact.checksum, body,
                             content_type=artifact.content_type or "application/zip")
            parsed = parse_idx_xbrl(
                body, ticker=source["ticker"], source_url=source["source_url"],
                published_at=source["published_at"], filing_type=source["filing_type"],
                filing_period_end=source["period_end"], document_checksum=artifact.checksum,
                object_key=artifact.object_key or artifact.checksum,
                audit_status=source.get("audit_status", "UNAUDITED"),
                restatement_version=int(source.get("restatement_version", 1)),
            )
            imported = repository.import_canonical_records(
                "statement_facts_csv", parsed["facts"], source_class="official",
            )
            repository.set_artifact_status(artifact_id, "ACCEPTED")
            report.append({
                **artifact.to_dict(), "ticker": source["ticker"], "status": "ACCEPTED",
                "record_count": imported, "diagnostics": parsed["diagnostics"],
            })
        except Exception as exc:
            if artifact_id:
                repository.set_artifact_status(artifact_id, "QUARANTINED")
                repository.record_ingestion_issue(artifact_id, "IDX_XBRL_FAILURE", str(exc))
            report.append({"ticker": source.get("ticker"), "source_url": source.get("source_url"),
                           "status": "QUARANTINED", "detail": str(exc)})
    return report


def discover_idx_manifest(output_path: str, *, as_of: str, year: int, period: str) -> dict:
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository
    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    issuers = repository.constituent_issuers_as_of("LQ45", as_of.split("T", 1)[0])
    if len(issuers) != 45:
        raise ValueError(f"Official discovery requires exactly 45 effective LQ45 issuers; found {len(issuers)}.")
    manifest = discover_idx_xbrl_manifest(
        [issuer["ticker"] for issuer in issuers], year=year, period=period,
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def candidate_readiness(snapshot: ResearchSnapshot) -> dict:
    """Enforce the scan's quant gate before a reviewed candidate can publish."""
    snapshot.validate(approved_only=False)
    expected = 45

    def row_eligible(row: dict) -> bool:
        factor_coverage = float(row.get("factor_coverage_pct", row.get("coverage_pct")) or 0)
        raw_coverage = float(row.get("raw_component_coverage_pct", row.get("coverage_pct")) or 0)
        return (row.get("composite_percentile") is not None
                and factor_coverage >= 75.0 and raw_coverage >= 70.0)

    eligible = [
        ticker for ticker, row in snapshot.rankings.items()
        if row_eligible(row)
    ]
    scored = [ticker for ticker, row in snapshot.rankings.items()
              if row.get("composite_percentile") is not None]
    factor_covered = [ticker for ticker, row in snapshot.rankings.items()
                      if float(row.get("factor_coverage_pct", row.get("coverage_pct")) or 0) >= 75.0]
    raw_covered = [ticker for ticker, row in snapshot.rankings.items()
                   if float(row.get("raw_component_coverage_pct", row.get("coverage_pct")) or 0) >= 70.0]
    required_eligible = math.ceil(expected * 0.90)
    checks = {
        "candidate_status": snapshot.model_status == "CANDIDATE",
        "exact_lq45_universe": len(snapshot.constituents) == expected,
        "rankings_match_constituents": set(snapshot.rankings) == set(snapshot.constituents),
        "eligible_quant_rows": len(eligible) >= required_eligible,
    }
    return {
        "ready": all(checks.values()), "checks": checks,
        "constituent_count": len(snapshot.constituents), "eligible_count": len(eligible),
        "scored_count": len(scored), "factor_coverage_75_count": len(factor_covered),
        "raw_coverage_70_count": len(raw_covered),
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
        failed = ", ".join(key for key, passed in readiness["checks"].items() if not passed)
        raise ValueError(f"Candidate readiness failed: {failed}. Details: {json.dumps(readiness, sort_keys=True)}")
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
        failed = ", ".join(key for key, passed in readiness["checks"].items() if not passed)
        raise ValueError(f"Candidate is not publishable: {failed}. Details: {json.dumps(readiness, sort_keys=True)}")
    approved = approve_snapshot(candidate_path, output_path, "SHADOW", None)
    snapshot_id = publish_snapshot(output_path)
    return {"published": True, "snapshot_id": snapshot_id, "readiness": readiness,
            "checksum": approved.checksum}


def backup_database(output_path: str, upload: bool) -> None:
    database_url = os.getenv("SUPABASE_WRITER_DATABASE_URL")
    if not database_url:
        raise RuntimeError("SUPABASE_WRITER_DATABASE_URL is required.")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--file", str(destination), database_url], check=True)
    if upload:
        key = os.getenv("BACKUP_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("BACKUP_ENCRYPTION_KEY is required before a database backup may leave the runner.")
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise RuntimeError("Install requirements-jobs.txt for encrypted backups.") from exc
        encrypted = Fernet(key.encode()).encrypt(destination.read_bytes())
        upload_to_r2(f"backups/{destination.name}.fernet", encrypted, content_type="application/octet-stream")


def publish_snapshot(path: str) -> str:
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository
    return SnapshotRepository(lambda: connect_from_env(writer=True)).publish_quant_snapshot(load_snapshot(path))


def build_daily_scan(output_path: str, *, use_r2: bool = False) -> dict:
    """Build and atomically publish the full-LQ45 EOD scan outside Railway."""
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository
    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    run = {"id": run_id, "job_type": "DAILY_SCAN",
           "workflow_run_id": os.getenv("GITHUB_RUN_ID"), "started_at": started_at,
           "status": "RUNNING", "metrics": {}}
    repository.record_research_job(run)

    archive = None
    if use_r2:
        archive = lambda key, body: upload_to_r2(key, body, content_type="application/gzip")
    try:
        snapshot = build_full_lq45_scan(repository, archive_callback=archive)
        payload = snapshot.to_dict()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(payload, indent=2, sort_keys=True))
        if snapshot.mode == "UNAVAILABLE":
            repository.record_research_job({**run, "completed_at": datetime.now(timezone.utc).isoformat(),
                                              "status": "DEGRADED", "output_checksum": snapshot.checksum,
                                              "metrics": {"mode": snapshot.mode,
                                                          "coverage_pct": snapshot.universe_coverage_pct}})
            return {"published": False, "snapshot": payload}
        snapshot_id = repository.publish_scan_snapshot(snapshot)
        repository.record_research_job({**run, "completed_at": datetime.now(timezone.utc).isoformat(),
                                          "status": "SUCCEEDED", "output_checksum": snapshot.checksum,
                                          "metrics": {"mode": snapshot.mode,
                                                      "coverage_pct": snapshot.universe_coverage_pct,
                                                      "candidate_count": len(snapshot.candidates)}})
        return {"published": True, "snapshot_id": snapshot_id, "snapshot": payload}
    except Exception as exc:
        repository.record_research_job({**run, "completed_at": datetime.now(timezone.utc).isoformat(),
                                          "status": "FAILED", "error_type": type(exc).__name__})
        raise


def build_snapshot_from_database(output_path: str, effective_at: str, model_version: str) -> ResearchSnapshot:
    from storage.database import connect_from_env
    from storage.repository import SnapshotRepository
    repository = SnapshotRepository(lambda: connect_from_env(writer=True))
    frame = build_factor_inputs(repository, effective_at)
    if frame.empty:
        raise ValueError("No eligible point-in-time LQ45 factor inputs were produced.")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".factor-inputs.csv")
    frame.to_csv(temporary, index=False)
    try:
        return build_snapshot(str(temporary), output_path, effective_at, model_version)
    finally:
        temporary.unlink(missing_ok=True)


def rebuild_monthly_panel(start: str, end: str, scores_output: str, bars_output: str) -> dict:
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
        for row in business["scores"].where(pd.notna(business["scores"]), None).to_dict("records"):
            if row.get("business_score") is not None:
                score_rows.append({"rebalance_date": session_date, "ticker": row["ticker"],
                                   "composite_percentile": row["business_score"],
                                   "coverage_pct": row["raw_fundamental_coverage_pct"]})
    scores = pd.DataFrame(score_rows)
    bars = pd.DataFrame(repository.validation_bars(start, end))
    if scores.empty or bars.empty:
        raise ValueError("Historical point-in-time scores or bars are unavailable.")
    Path(scores_output).parent.mkdir(parents=True, exist_ok=True)
    Path(bars_output).parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(scores_output, index=False)
    bars.to_csv(bars_output, index=False)
    return {"months": len(month_ends), "score_rows": len(scores), "bar_rows": len(bars),
            "scores_checksum": hashlib.sha256(Path(scores_output).read_bytes()).hexdigest(),
            "bars_checksum": hashlib.sha256(Path(bars_output).read_bytes()).hexdigest()}


def validate_quant(scores_path: str, bars_path: str, output_path: str,
                   *, persist: bool = False, model_version: str = "lq45-factor-v1",
                   deterministic_rebuild: bool = False) -> dict:
    scores, bars = pd.read_csv(scores_path), pd.read_csv(bars_path)
    costs = BrokerCostProfile(
        os.getenv("BROKER_COST_PROFILE", "validation"),
        float(os.getenv("BROKER_BUY_COMMISSION", ".0015")),
        float(os.getenv("BROKER_SELL_COMMISSION", ".0025")),
        float(os.getenv("BROKER_SELL_LEVY", ".001")),
        float(os.getenv("BROKER_HALF_SPREAD", ".0005")),
        float(os.getenv("BROKER_SLIPPAGE_BPS", "5")),
    )
    dates = sorted(pd.to_datetime(scores["rebalance_date"]).dt.tz_localize(None).unique())
    holdout_dates = dates[-25:] if len(dates) >= 25 else dates
    holdout = scores[pd.to_datetime(scores["rebalance_date"]).dt.tz_localize(None).isin(holdout_dates)]
    result = backtest_monthly_quant(holdout, bars, broker_costs=costs)
    if result.get("status") != "AVAILABLE":
        raise ValueError(result.get("reason", "Quant validation unavailable."))
    high_cost = BrokerCostProfile(
        f"{costs.name}-2x", costs.buy_commission * 2, costs.sell_commission * 2,
        costs.sell_tax_levy * 2, costs.half_spread * 2, costs.slippage_bps * 2,
    )
    stressed = backtest_monthly_quant(holdout, bars, broker_costs=high_cost)
    delayed = backtest_monthly_quant(holdout, bars, broker_costs=costs, execution_delay_sessions=1)
    usable_years = ((max(dates) - min(dates)).days / 365.25) if len(dates) > 1 else 0
    acceptance = assess_holdout(
        result, usable_years=usable_years, holdout_months=max(0, len(holdout_dates) - 1),
        higher_cost_positive=(stressed.get("net_excess_cagr") or 0) > 0,
        delayed_entry_positive=(delayed.get("net_excess_cagr") or 0) > 0,
        deterministic_rebuild=deterministic_rebuild,
    )
    summary = {key: value for key, value in result.items() if key not in {"monthly", "observations"}}
    payload = {"metrics": summary, "acceptance": acceptance}
    encoded = json.dumps(payload, indent=2, sort_keys=True).encode()
    Path(output_path).write_bytes(encoded)
    if persist:
        from storage.database import connect_from_env
        from storage.repository import SnapshotRepository
        input_checksum = hashlib.sha256(Path(scores_path).read_bytes() + Path(bars_path).read_bytes()).hexdigest()
        run_id = str(uuid4())
        persisted = SnapshotRepository(lambda: connect_from_env(writer=True)).save_validation_run(
            run_id=run_id, model_version=model_version, input_checksum=input_checksum,
            metrics=summary, acceptance=acceptance,
            holdout_start=str(pd.Timestamp(holdout_dates[0]).date()) if holdout_dates else None,
            holdout_end=str(pd.Timestamp(holdout_dates[-1]).date()) if holdout_dates else None,
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
    build.add_argument("--input", required=True); build.add_argument("--output", required=True)
    build.add_argument("--effective-at", required=True); build.add_argument("--model-version", default="lq45-factor-v1")
    approve = sub.add_parser("approve-snapshot")
    approve.add_argument("--candidate", required=True); approve.add_argument("--output", required=True)
    approve.add_argument("--status", choices=["SHADOW", "VALIDATED_RESEARCH"], default="SHADOW")
    approve.add_argument("--validation-run-id")
    build_db = sub.add_parser("build-snapshot-from-database")
    build_db.add_argument("--output", required=True); build_db.add_argument("--effective-at", required=True)
    build_db.add_argument("--model-version", default="lq45-factor-v1")
    ingest = sub.add_parser("ingest-manifest")
    ingest.add_argument("--manifest", required=True); ingest.add_argument("--report", required=True)
    ingest.add_argument("--archive-directory"); ingest.add_argument("--r2", action="store_true")
    ingest_idx = sub.add_parser("ingest-idx-xbrl")
    ingest_idx.add_argument("--manifest", required=True); ingest_idx.add_argument("--report", required=True)
    ingest_idx.add_argument("--archive-directory"); ingest_idx.add_argument("--r2", action="store_true")
    discover_idx = sub.add_parser("discover-idx-xbrl")
    discover_idx.add_argument("--output", required=True); discover_idx.add_argument("--as-of", required=True)
    discover_idx.add_argument("--year", required=True, type=int)
    discover_idx.add_argument("--period", required=True, choices=["tw1", "tw2", "tw3"])
    backup = sub.add_parser("backup")
    backup.add_argument("--output", required=True); backup.add_argument("--r2", action="store_true")
    publish = sub.add_parser("publish-snapshot")
    publish.add_argument("--snapshot", required=True)
    publish_shadow = sub.add_parser("publish-reviewed-shadow")
    publish_shadow.add_argument("--candidate", required=True); publish_shadow.add_argument("--output", required=True)
    check = sub.add_parser("check-candidate")
    check.add_argument("--snapshot", required=True)
    validate = sub.add_parser("validate-quant")
    validate.add_argument("--scores", required=True); validate.add_argument("--bars", required=True)
    validate.add_argument("--output", required=True)
    validate.add_argument("--persist", action="store_true")
    validate.add_argument("--model-version", default="lq45-factor-v1")
    validate.add_argument("--deterministic-rebuild", action="store_true")
    daily_scan = sub.add_parser("build-daily-scan")
    daily_scan.add_argument("--output", required=True)
    daily_scan.add_argument("--r2", action="store_true")
    rebuild = sub.add_parser("rebuild-monthly-panel")
    rebuild.add_argument("--start", required=True); rebuild.add_argument("--end", required=True)
    rebuild.add_argument("--scores-output", required=True); rebuild.add_argument("--bars-output", required=True)
    sub.add_parser("evaluate-signal-outcomes")
    args = parser.parse_args(argv)
    if args.command == "build-snapshot":
        build_snapshot(args.input, args.output, args.effective_at, args.model_version)
    elif args.command == "approve-snapshot":
        approve_snapshot(args.candidate, args.output, args.status, args.validation_run_id)
    elif args.command == "build-snapshot-from-database":
        build_snapshot_from_database(args.output, args.effective_at, args.model_version)
    elif args.command == "ingest-manifest":
        report = ingest_manifest(args.manifest, archive_directory=args.archive_directory, use_r2=args.r2)
        Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True))
        if any(item["status"] == "QUARANTINED" for item in report):
            return 2
    elif args.command == "ingest-idx-xbrl":
        report = ingest_idx_xbrl_manifest(
            args.manifest, archive_directory=args.archive_directory, use_r2=args.r2,
        )
        Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True))
        if any(item["status"] == "QUARANTINED" for item in report):
            return 2
    elif args.command == "discover-idx-xbrl":
        manifest = discover_idx_manifest(
            args.output, as_of=args.as_of, year=args.year, period=args.period,
        )
        missing = manifest["discovery"]["current_period_missing"] + manifest["discovery"]["prior_annual_missing"]
        print(json.dumps(manifest["discovery"], sort_keys=True))
        if missing:
            return 2
    elif args.command == "backup":
        backup_database(args.output, args.r2)
    elif args.command == "publish-snapshot":
        print(publish_snapshot(args.snapshot))
    elif args.command == "publish-reviewed-shadow":
        print(json.dumps(publish_reviewed_shadow(args.candidate, args.output), sort_keys=True))
    elif args.command == "check-candidate":
        print(json.dumps(check_candidate(args.snapshot), sort_keys=True))
    elif args.command == "validate-quant":
        result = validate_quant(args.scores, args.bars, args.output, persist=args.persist,
                                model_version=args.model_version,
                                deterministic_rebuild=args.deterministic_rebuild)
        print(json.dumps(result, sort_keys=True))
    elif args.command == "build-daily-scan":
        result = build_daily_scan(args.output, use_r2=args.r2)
        snapshot = result.get("snapshot") or {}
        summary = {key: value for key, value in result.items() if key != "snapshot"}
        summary.update({
            "mode": snapshot.get("mode"),
            "session_date": snapshot.get("session_date"),
            "universe_coverage_pct": snapshot.get("universe_coverage_pct"),
            "warnings": snapshot.get("warnings", []),
            "excluded_count": len(snapshot.get("excluded", [])),
        })
        print(json.dumps(summary, sort_keys=True))
        if not result["published"]:
            return 2
    elif args.command == "rebuild-monthly-panel":
        result = rebuild_monthly_panel(args.start, args.end, args.scores_output, args.bars_output)
        print(json.dumps(result, sort_keys=True))
    elif args.command == "evaluate-signal-outcomes":
        print(json.dumps(evaluate_signal_outcomes(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
