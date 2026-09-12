"""Filing-by-Filing import with durable skip and fenced completion."""

from datetime import datetime, timedelta, timezone
import hashlib
import re
import time
from uuid import uuid4

from data.filing_manifest import exact_identity, merge_manifests
from data.idx_xbrl import parse_idx_xbrl
from data.ingestion import acquire_artifact, upload_to_r2


_RETRYABLE_ERRORS = {
    ("TRANSIENT", "LEASE_EXPIRED"),
    ("PROVIDER", "PROVIDER_UNAVAILABLE"),
    ("DATABASE", "DATABASE_UNAVAILABLE"),
}
_REQUIRED_MIGRATIONS = [
    "007_filing_work_ledger",
    "008_filing_artifact_mismatch",
]


def _validated_filings(manifest):
    rows = merge_manifests({"filings": []}, manifest)["filings"]
    for row in rows:
        ticker, _kind, period, _version = exact_identity(row)
        if not re.fullmatch(r"[A-Z0-9]{1,12}", ticker):
            raise ValueError("invalid ticker")
        publication = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
        if publication.tzinfo is None or publication.date().isoformat() < period:
            raise ValueError("invalid publication time")
    return [
        {
            **row,
            "ticker": exact_identity(row)[0],
            "filing_type": exact_identity(row)[1],
        }
        for row in rows
    ]


def filing_shard(filing, shard_count: int) -> int:
    """Return a stable issuer/reporting-year shard without using process hash state."""
    if (
        isinstance(shard_count, bool)
        or not isinstance(shard_count, int)
        or shard_count <= 0
    ):
        raise ValueError("invalid Filing shard count")
    ticker, _kind, period_end, _version = exact_identity(filing)
    group = f"{ticker}:{period_end[:4]}".encode("ascii")
    return int.from_bytes(hashlib.sha256(group).digest()[:8], "big") % shard_count


def aggregate_filing_progress(manifest, repository, *, run_id: str) -> dict:
    """Validate and sync the complete manifest, then read durable batch progress."""
    report = {
        "run_id": str(run_id),
        "ok": False,
        "code": "MANIFEST_INVALID",
        "counts": {},
    }
    try:
        clean_run_id = str(run_id).strip()
        if not clean_run_id:
            raise ValueError("invalid Filing batch run")
        rows = _validated_filings(manifest)
    except (ValueError, TypeError, KeyError, AttributeError):
        return report
    try:
        if not repository.preflight_schema_migrations(_REQUIRED_MIGRATIONS)["ok"]:
            report["code"] = "MIGRATION_PREFLIGHT_FAILED"
            return report
        prepared = repository.prepare_filing_import(rows)
        counts = repository.aggregate_filing_progress(prepared, clean_run_id)
    except Exception:
        report["code"] = "PROGRESS_UNAVAILABLE"
        return report
    report["counts"] = counts
    report["ok"] = counts["accepted"] + counts["skipped_accepted"] == counts["manifest"]
    report["code"] = "COMPLETE" if report["ok"] else "INCOMPLETE"
    return report


def import_filings(
    manifest,
    repository,
    *,
    archive_directory=None,
    use_r2=False,
    acquire=acquire_artifact,
    parse=parse_idx_xbrl,
    upload=upload_to_r2,
    shard_count=1,
    shard_index=0,
    run_id=None,
    max_attempts=3,
    retry_backoff_seconds=0,
    time_budget_seconds=1200,
    per_item_reserve_seconds=120,
    monotonic=time.monotonic,
    sleep=time.sleep,
    now=None,
):
    """Return only normalized identities, stable codes, and run-local counts."""
    report = {
        "run_id": str(run_id or uuid4()),
        "ok": False,
        "code": "MANIFEST_INVALID",
        "filings": [],
        "counts": dict.fromkeys(
            (
                "manifest",
                "assigned",
                "attempted",
                "downloaded",
                "accepted",
                "skipped_accepted",
                "quarantined",
                "retryable",
                "leased_elsewhere",
                "remaining",
            ),
            0,
        ),
    }
    try:
        if (
            isinstance(shard_count, bool)
            or isinstance(shard_index, bool)
            or not isinstance(shard_count, int)
            or not isinstance(shard_index, int)
            or shard_count <= 0
            or shard_index < 0
            or shard_index >= shard_count
            or isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or max_attempts <= 0
            or retry_backoff_seconds < 0
            or time_budget_seconds <= 0
            or per_item_reserve_seconds < 0
            or per_item_reserve_seconds >= time_budget_seconds
            or not report["run_id"].strip()
        ):
            raise ValueError("invalid Filing import policy")
        rows = _validated_filings(manifest)
    except (ValueError, TypeError, KeyError, AttributeError):
        return report
    started_at = monotonic()
    deadline = started_at + time_budget_seconds
    current_time = now or (lambda: datetime.now(timezone.utc))
    report["counts"]["manifest"] = len(rows)
    report["counts"]["remaining"] = len(rows)

    def record(row, state, action, code, counter=None):
        report["filings"].append(
            {
                "identity": list(exact_identity(row)),
                "state": state,
                "action": action,
                "code": code,
            }
        )
        if counter:
            report["counts"][counter] += 1

    def block_all(code):
        for row in rows:
            record(row, "PENDING", "BLOCKED", code)

    try:
        if not repository.preflight_schema_migrations(_REQUIRED_MIGRATIONS)["ok"]:
            report["code"] = "MIGRATION_PREFLIGHT_FAILED"
            block_all(report["code"])
            return report
        prepared = repository.prepare_filing_import(rows)
    except Exception:
        report["code"] = "MANIFEST_SYNC_FAILED"
        block_all(report["code"])
        return report

    assigned = [
        row for row in prepared if filing_shard(row, shard_count) == shard_index
    ]
    report["counts"]["assigned"] = len(assigned)
    report["counts"]["remaining"] = len(assigned)

    for row in assigned:
        state = row["state"]
        if state in {"ACCEPTED", "QUARANTINED"}:
            counter = "skipped_accepted" if state == "ACCEPTED" else "quarantined"
            record(row, state, "SKIPPED", "ALREADY_TERMINAL", counter)
            continue
        attempt_count = int(row.get("attempt_count") or 0)
        if (
            state == "RETRYABLE"
            and (row.get("last_error_class"), row.get("last_error_summary"))
            not in _RETRYABLE_ERRORS
        ):
            record(row, state, "DEFERRED", "RETRY_NOT_ALLOWED", "retryable")
            continue
        if attempt_count >= max_attempts:
            record(row, "RETRYABLE", "EXHAUSTED", "RETRY_LIMIT_REACHED", "retryable")
            continue
        if state == "RETRYABLE" and retry_backoff_seconds:
            changed_at = row.get("state_changed_at")
            if isinstance(changed_at, str):
                changed_at = datetime.fromisoformat(changed_at.replace("Z", "+00:00"))
            delay = retry_backoff_seconds * (2 ** max(0, attempt_count - 1))
            if changed_at and current_time() < changed_at + timedelta(seconds=delay):
                record(row, state, "DEFERRED", "RETRY_BACKOFF", "retryable")
                continue
        expiry = row.get("lease_expires_at")
        if state == "RUNNING" and expiry and expiry > current_time():
            record(row, "RUNNING", "DEFERRED", "LEASED_ELSEWHERE", "leased_elsewhere")
            continue
        while True:
            if monotonic() + per_item_reserve_seconds > deadline:
                record(row, state, "DEFERRED", "BUDGET_EXHAUSTED")
                break
            try:
                fence = repository.filing_download_fence(row)
                owns_download = fence.__enter__()
            except Exception:
                record(row, state, "DEFERRED", "DATABASE_UNAVAILABLE", "retryable")
                break
            retry = False
            try:
                if not owns_download:
                    record(
                        row,
                        "RUNNING",
                        "DEFERRED",
                        "LEASED_ELSEWHERE",
                        "leased_elsewhere",
                    )
                    break
                try:
                    lease = repository.claim_filing_work(
                        row,
                        report["run_id"],
                        run_id=report["run_id"],
                        max_attempts=max_attempts,
                    )
                except Exception:
                    record(row, state, "DEFERRED", "DATABASE_UNAVAILABLE", "retryable")
                    break
                if not lease:
                    record(
                        row,
                        "RUNNING",
                        "DEFERRED",
                        "LEASED_ELSEWHERE",
                        "leased_elsewhere",
                    )
                    break
                attempt_count = int(lease.get("attempt_number") or attempt_count + 1)
                report["counts"]["attempted"] += 1
                token = lease["lease_token"]
                artifact = None
                parsed = None
                outcome = "ACCEPTED"
                error_class, code = "PROVIDER", "PROVIDER_UNAVAILABLE"
                try:
                    # The DB lease is a stale-writer fence. The session advisory lock
                    # remains the download fence across provider and parser work.
                    if not repository.renew_filing_work(row, token):
                        record(
                            row,
                            "RUNNING",
                            "DEFERRED",
                            "LEASE_EXPIRED",
                            "leased_elsewhere",
                        )
                        break
                    acquired, body = acquire(
                        provider="IDX",
                        source_class="official",
                        artifact_type="idx_xbrl_instance",
                        source_url=row["source_url"],
                        published_at=row["published_at"],
                        archive_directory=archive_directory,
                    )
                    artifact = acquired.to_dict()
                    report["counts"]["downloaded"] += 1
                    if use_r2:
                        upload(
                            artifact["object_key"] or artifact["checksum"],
                            body,
                            content_type=artifact["content_type"] or "application/zip",
                        )
                    if row.get("checksum") and artifact["checksum"] != row["checksum"]:
                        completed = repository.complete_filing_import(
                            row,
                            token,
                            artifact,
                            parsed=None,
                            state="QUARANTINED",
                            error_class="PROVENANCE",
                            error_summary="ARTIFACT_MISMATCH",
                        )
                        if not completed:
                            record(
                                row,
                                "RUNNING",
                                "DEFERRED",
                                "LEASE_EXPIRED",
                                "leased_elsewhere",
                            )
                        else:
                            record(
                                row,
                                "QUARANTINED",
                                "QUARANTINED",
                                "ARTIFACT_MISMATCH",
                                "quarantined",
                            )
                        break
                    try:
                        parsed = parse(
                            body,
                            ticker=row["ticker"],
                            source_url=row["source_url"],
                            published_at=row["published_at"],
                            filing_type=row["filing_type"],
                            filing_period_end=row["period_end"],
                            document_checksum=artifact["checksum"],
                            object_key=artifact["object_key"] or artifact["checksum"],
                            audit_status=row["audit_status"],
                            restatement_version=row["restatement_version"],
                        )
                    except (ValueError, KeyError, TypeError):
                        outcome, code = "QUARANTINED", "VALIDATION_FAILED"
                    error_class = "DATABASE"
                    if outcome == "ACCEPTED":
                        code = "DATABASE_UNAVAILABLE"
                    try:
                        completed = repository.complete_filing_import(
                            row, token, artifact, parsed=parsed, state=outcome
                        )
                    except (ValueError, KeyError, TypeError):
                        outcome, code = "QUARANTINED", "SCHEMA_INVALID"
                        completed = repository.complete_filing_import(
                            row,
                            token,
                            artifact,
                            state=outcome,
                            error_class="SCHEMA",
                            error_summary="SCHEMA_INVALID",
                        )
                    if not completed:
                        record(
                            row,
                            "RUNNING",
                            "DEFERRED",
                            "LEASE_EXPIRED",
                            "leased_elsewhere",
                        )
                        break
                    record(
                        row,
                        outcome,
                        "IMPORTED" if outcome == "ACCEPTED" else "QUARANTINED",
                        "ACCEPTED" if outcome == "ACCEPTED" else code,
                        "accepted" if outcome == "ACCEPTED" else "quarantined",
                    )
                    break
                except Exception:
                    # Failed completion rolled back. A separate fenced transaction records
                    # retryable work; if storage is down the durable RUNNING lease expires.
                    durable = None
                    try:
                        durable = repository.finalize_filing_work(
                            row,
                            token,
                            "RETRYABLE",
                            error_class=error_class,
                            error_summary=code,
                        )
                    except Exception:
                        code = "DATABASE_UNAVAILABLE"
                    if durable and attempt_count < max_attempts:
                        retry = True
                    else:
                        record(
                            row,
                            "RETRYABLE" if durable else "RUNNING",
                            "EXHAUSTED" if durable else "DEFERRED",
                            "RETRY_LIMIT_REACHED" if durable else code,
                            "retryable",
                        )
            finally:
                fence.__exit__(None, None, None)
            if not retry:
                break
            delay = retry_backoff_seconds * (2 ** max(0, attempt_count - 1))
            if monotonic() + delay + per_item_reserve_seconds > deadline:
                record(
                    row,
                    "RETRYABLE",
                    "DEFERRED",
                    "BUDGET_EXHAUSTED",
                    "retryable",
                )
                break
            if delay:
                sleep(delay)
    report["ok"] = report["counts"]["accepted"] + report["counts"][
        "skipped_accepted"
    ] == len(assigned)
    report["counts"]["remaining"] = len(assigned) - (
        report["counts"]["accepted"] + report["counts"]["skipped_accepted"]
    )
    report["code"] = "COMPLETE" if report["ok"] else "INCOMPLETE"
    return report
