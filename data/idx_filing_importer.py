"""Filing-by-Filing import with durable skip and fenced completion."""

from datetime import datetime, timezone
import re
from uuid import uuid4

from data.filing_manifest import exact_identity, merge_manifests
from data.idx_xbrl import parse_idx_xbrl
from data.ingestion import acquire_artifact, upload_to_r2


def import_filings(
    manifest,
    repository,
    *,
    archive_directory=None,
    use_r2=False,
    acquire=acquire_artifact,
    parse=parse_idx_xbrl,
    upload=upload_to_r2,
):
    """Return only normalized identities, stable codes, and run-local counts."""
    report = {
        "run_id": str(uuid4()),
        "ok": False,
        "code": "MANIFEST_INVALID",
        "filings": [],
        "counts": dict.fromkeys(
            (
                "manifest",
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
        rows = merge_manifests({"filings": []}, manifest)["filings"]
        for row in rows:
            ticker, kind, period, version = exact_identity(row)
            if not re.fullmatch(r"[A-Z0-9]{1,12}", ticker):
                raise ValueError("invalid ticker")
            publication = datetime.fromisoformat(
                row["published_at"].replace("Z", "+00:00")
            )
            if publication.tzinfo is None or publication.date().isoformat() < period:
                raise ValueError("invalid publication time")
        rows = [
            {
                **row,
                "ticker": exact_identity(row)[0],
                "filing_type": exact_identity(row)[1],
            }
            for row in rows
        ]
    except (ValueError, TypeError, KeyError, AttributeError):
        return report
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
        if not repository.preflight_schema_migrations(
            ["007_filing_work_ledger", "008_filing_artifact_mismatch"]
        )["ok"]:
            report["code"] = "MIGRATION_PREFLIGHT_FAILED"
            block_all(report["code"])
            return report
        prepared = repository.prepare_filing_import(rows)
    except Exception:
        report["code"] = "MANIFEST_SYNC_FAILED"
        block_all(report["code"])
        return report

    for row in prepared:
        state = row["state"]
        if state in {"ACCEPTED", "QUARANTINED"}:
            counter = "skipped_accepted" if state == "ACCEPTED" else "quarantined"
            record(row, state, "SKIPPED", "ALREADY_TERMINAL", counter)
            continue
        expiry = row.get("lease_expires_at")
        if state == "RUNNING" and expiry and expiry > datetime.now(timezone.utc):
            record(row, "RUNNING", "DEFERRED", "LEASED_ELSEWHERE", "leased_elsewhere")
            continue
        try:
            fence = repository.filing_download_fence(row)
            owns_download = fence.__enter__()
        except Exception:
            record(row, state, "DEFERRED", "DATABASE_UNAVAILABLE", "retryable")
            continue
        try:
            if not owns_download:
                record(
                    row,
                    "RUNNING",
                    "DEFERRED",
                    "LEASED_ELSEWHERE",
                    "leased_elsewhere",
                )
                continue
            try:
                lease = repository.claim_filing_work(
                    row, report["run_id"], run_id=report["run_id"]
                )
            except Exception:
                record(row, state, "DEFERRED", "DATABASE_UNAVAILABLE", "retryable")
                continue
            if not lease:
                record(
                    row,
                    "RUNNING",
                    "DEFERRED",
                    "LEASED_ELSEWHERE",
                    "leased_elsewhere",
                )
                continue
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
                    continue
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
                    continue
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
                    continue
                record(
                    row,
                    outcome,
                    "IMPORTED" if outcome == "ACCEPTED" else "QUARANTINED",
                    "ACCEPTED" if outcome == "ACCEPTED" else code,
                    "accepted" if outcome == "ACCEPTED" else "quarantined",
                )
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
                record(
                    row,
                    "RETRYABLE" if durable else "RUNNING",
                    "RETRY" if durable else "DEFERRED",
                    code,
                    "retryable",
                )
        finally:
            fence.__exit__(None, None, None)
    report["ok"] = report["counts"]["accepted"] + report["counts"][
        "skipped_accepted"
    ] == len(rows)
    report["counts"]["remaining"] = len(rows) - (
        report["counts"]["accepted"] + report["counts"]["skipped_accepted"]
    )
    report["code"] = "COMPLETE" if report["ok"] else "INCOMPLETE"
    return report
