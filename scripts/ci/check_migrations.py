"""Apply and verify the repository's PostgreSQL migrations in CI.

This helper intentionally uses a database URL supplied by the ephemeral CI
service. It never creates a production connection. Migration down/re-up runs
only with the explicit guarded disposable flag and a named CI database/user on
a loopback PostgreSQL server.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import hashlib
from pathlib import Path
import time
from typing import Any
import subprocess
import sys
from uuid import uuid4


def migration_files(directory: Path) -> list[Path]:
    """Return ordered up migrations, rejecting duplicate version names."""
    files = sorted(directory.glob("*.up.sql"))
    versions = [path.name.removesuffix(".up.sql") for path in files]
    if len(versions) != len(set(versions)):
        raise ValueError("migration versions are duplicated")
    return files


def migration_pairs(directory: Path) -> dict[str, tuple[Path, Path]]:
    """Require a reversible pair for every migration version."""
    ups = {p.name.removesuffix(".up.sql"): p for p in directory.glob("*.up.sql")}
    downs = {p.name.removesuffix(".down.sql"): p for p in directory.glob("*.down.sql")}
    if set(ups) != set(downs):
        raise ValueError(
            "migration up/down pairs do not match: "
            f"missing up={sorted(set(downs) - set(ups))}, "
            f"missing down={sorted(set(ups) - set(downs))}"
        )
    return {version: (ups[version], downs[version]) for version in sorted(ups)}


def migration_checksums(directory: Path) -> dict[str, str]:
    migration_pairs(directory)
    return {
        path.name.removesuffix(".up.sql"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in migration_files(directory)
    }


def read_sql(path: Path) -> str:
    """Decode migration bytes explicitly so locale/SQL_ASCII cannot leak in."""
    return path.read_bytes().decode("utf-8", errors="strict")


def normalize_version(value: object) -> str:
    """Normalize PostgreSQL text values from UTF-8 and SQL_ASCII adapters."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict")
    return str(value)


def immutable_against(directory: Path, base_ref: str) -> None:
    """Reject edits to an already published migration in the requested base."""
    changed = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD", "--", str(directory)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for filename in changed:
        path = Path(filename)
        if path.suffixes[-2:] not in ([".up", ".sql"], [".down", ".sql"]):
            continue
        try:
            subprocess.run(
                ["git", "cat-file", "-e", f"{base_ref}:{filename}"],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            continue  # An additive migration is allowed; its pair is checked above.
        raise RuntimeError(
            f"immutable migration changed relative to {base_ref}: {filename}"
        )


def apply_migrations(connection: Any, directory: Path) -> dict[str, str]:
    """Apply every migration to a clean database and verify the ledger."""
    checksums = migration_checksums(directory)
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS ci_migration_checksums "
            "(version text PRIMARY KEY, checksum text NOT NULL)"
        )
        for path in migration_files(directory):
            version = path.name.removesuffix(".up.sql")
            cursor.execute(
                "SELECT checksum FROM ci_migration_checksums WHERE version=%s",
                (version,),
            )
            recorded = cursor.fetchone()
            if recorded and normalize_version(recorded[0]) != checksums[version]:
                raise RuntimeError(
                    f"migration checksum changed after application: {version}"
                )
            if not recorded:
                cursor.execute(read_sql(path))
                cursor.execute(
                    "INSERT INTO ci_migration_checksums(version, checksum) VALUES (%s, %s)",
                    (version, checksums[version]),
                )
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        applied = {normalize_version(row[0]) for row in cursor.fetchall()}
    expected = set(checksums)
    if applied != expected:
        raise RuntimeError(
            f"migration ledger mismatch: expected {sorted(expected)}, got {sorted(applied)}"
        )
    connection.commit()
    return checksums


def repository_compatibility(connection: Any, expected_versions: set[str]) -> None:
    """Exercise the repository's read-only migration seam without providers."""
    project_root = str(Path.cwd())
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from storage.repository import SnapshotRepository

    class ReusedConnection:
        def __init__(self, wrapped: Any):
            self.wrapped = wrapped

        def __enter__(self):
            return self.wrapped

        def __exit__(self, *_args):
            return False

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    migrations = SnapshotRepository(
        lambda: ReusedConnection(connection)
    ).applied_schema_migrations()
    observed = set(migrations)
    if observed != expected_versions:
        raise RuntimeError(
            f"repository migration mismatch: expected {sorted(expected_versions)}, "
            f"got {sorted(observed)}"
        )


def filing_work_behavior(connection: Any, database_url: str) -> None:
    """Exercise migration-007 behavior against the disposable CI PostgreSQL service."""
    from storage.repository import SnapshotRepository

    def connect():
        import psycopg

        return psycopg.connect(database_url)

    def artifact(source_url: str, checksum: str, status: str) -> str:
        artifact_id = str(uuid4())
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO source_artifacts
                   (id,provider,source_class,artifact_type,source_url,checksum,retrieved_at,parse_status)
                   VALUES (%s,'ci','official','filing',%s,%s,clock_timestamp(),%s)""",
                (artifact_id, source_url, checksum, status),
            )
        connection.commit()
        return artifact_id

    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO issuers(ticker,legal_name,sector,currency,active_from) VALUES ('CIW','CI ledger','Test','IDR','2020-01-01') RETURNING id"
        )
        issuer = cursor.fetchone()[0]
    connection.commit()

    repo = SnapshotRepository(connect)
    future_filing_checksum = "9" * 64
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO filings
               (issuer_id,filing_type,period_end,published_at,available_at,consolidated,audit_status,
                restatement_version,source_url,object_key,document_checksum)
               VALUES (%s,'FUTURE','2099-12-31','2099-12-31T00:00:00Z','2099-12-31T00:00:00Z',true,
                       'AUDITED',1,'https://ci.example/future.zip','ci/future.zip',%s)
               RETURNING id""",
            (issuer, future_filing_checksum),
        )
        future_filing_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO statement_facts
               (filing_id,taxonomy,concept,normalized_concept,period_start,period_end,published_at,available_at,
                value,currency,scale,unit,consolidated,audit_status,source_url,document_checksum,restatement_version)
               VALUES (%s,'CI','FutureConcept','future_concept','2099-01-01','2099-12-31','2099-12-31T00:00:00Z',
                       '2099-12-31T00:00:00Z',123.45,'IDR',0,'IDR',true,'AUDITED','https://ci.example/future.zip',%s,1)""",
            (future_filing_id, future_filing_checksum),
        )
    connection.commit()
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM filings")
        filings_before = cursor.fetchone()[0]
    if repo.facts_as_of(issuer, "2090-01-01T00:00:00Z"):
        raise RuntimeError("future filing leaked before its available_at cutoff")
    if len(repo.facts_as_of(issuer, "2100-01-01T00:00:00Z")) != 1:
        raise RuntimeError(
            "future filing was not visible after its available_at cutoff"
        )

    ingest_connection = connect()
    try:
        with ingest_connection.cursor() as cursor:
            cursor.execute("SET ROLE pasticuan_ingest")
            cursor.execute(
                """INSERT INTO filing_work_items
                   (issuer_id,filing_type,period_end,restatement_version,source_url,published_at,audit_status,
                    state,attempt_count,lease_token,lease_owner,lease_expires_at)
                   VALUES (%s,'FORGED','2025-01-01',1,'https://ci.example/forged.zip','2025-01-02T00:00:00Z',
                           'UNAUDITED','RUNNING',1,'00000000-0000-0000-0000-000000000002','forged',clock_timestamp()+interval '1 minute')""",
                (issuer,),
            )
        ingest_connection.commit()
    except Exception:
        ingest_connection.rollback()
    else:
        raise RuntimeError("ingest role inserted non-pending filing work")
    finally:
        ingest_connection.close()

    base = {
        "issuer_id": issuer,
        "filing_type": "Q1",
        "period_end": "2025-03-31",
        "restatement_version": 1,
        "source_url": "https://ci.example/q1.zip",
        "published_at": "2025-04-01T00:00:00Z",
        "audit_status": "UNAUDITED",
        "expected_checksum": "a" * 64,
    }
    independent = {
        **base,
        "filing_type": "Q4",
        "period_end": "2025-12-31",
        "source_url": "https://ci.example/q4.zip",
        "expected_checksum": "f" * 64,
    }
    repo.sync_reviewed_filings([base, independent])
    repo.sync_reviewed_filings([base])
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM filing_work_items WHERE issuer_id=%s", (issuer,)
        )
        assert cursor.fetchone()[0] == 2
        try:
            cursor.execute(
                """UPDATE filing_work_items SET state='RUNNING',attempt_count=1,lease_token='00000000-0000-0000-0000-000000000001',
                          lease_owner='forged',lease_expires_at=clock_timestamp()+interval '1 minute'
                   WHERE issuer_id=%s AND filing_type='Q1'""",
                (issuer,),
            )
            connection.commit()
        except Exception:
            connection.rollback()
        else:
            raise RuntimeError("pending filing work ran without a matching attempt")
    conflict = {**base, "source_url": "https://ci.example/changed.zip"}
    try:
        repo.sync_reviewed_filings([conflict])
    except ValueError:
        pass
    else:
        raise RuntimeError("filing provenance conflict was accepted")

    # Two separate database sessions contend for one lease; exactly one wins.
    def claim():
        return SnapshotRepository(connect).claim_filing_work(
            base, "ci-worker", lease_seconds=2, run_id=str(uuid4())
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim(), range(2)))
    winners = [value for value in claims if value]
    if len(winners) != 1:
        raise RuntimeError("concurrent filing lease fencing failed")
    winner = winners[0]
    if not repo.renew_filing_work(base, winner["lease_token"], lease_seconds=2):
        raise RuntimeError("live lease renewal failed")
    if (
        repo.finalize_filing_work(
            base,
            str(uuid4()),
            "RETRYABLE",
            error_class="PROVIDER",
            error_summary="PROVIDER_UNAVAILABLE",
        )
        is not None
    ):
        raise RuntimeError("stale filing lease finalized work")

    # Expiry is durable and reclaim creates a new attempt/run without changing identity.
    time.sleep(2.1)
    if not repo.expire_filing_work_leases(limit=10):
        raise RuntimeError("expired filing lease was not persisted")
    reclaimed = repo.claim_filing_work(
        base, "ci-worker-2", lease_seconds=10, run_id="ci-reclaim"
    )
    if not reclaimed or reclaimed["attempt_number"] != 2:
        raise RuntimeError("expired filing lease was not reclaimed")

    accepted_id = artifact(base["source_url"], base["expected_checksum"], "ACCEPTED")
    try:
        repo.finalize_filing_work(
            base,
            reclaimed["lease_token"],
            "ACCEPTED",
            artifact_id=accepted_id,
            checksum="b" * 64,
        )
    except ValueError:
        pass
    else:
        raise RuntimeError("caller checksum mismatch was accepted")
    if (
        repo.finalize_filing_work(
            base,
            reclaimed["lease_token"],
            "ACCEPTED",
            artifact_id=accepted_id,
            checksum=base["expected_checksum"],
        )
        is None
    ):
        raise RuntimeError("matching accepted artifact was rejected")
    independent_status = repo.get_filing_work_statuses([independent])
    if not independent_status or independent_status[0]["state"] != "PENDING":
        raise RuntimeError("independent filing work was changed by another item")
    independent_claim = repo.claim_filing_work(
        independent, "ci-independent", run_id="ci-independent"
    )
    if not independent_claim:
        raise RuntimeError("independent filing lease was not acquired")
    repo.finalize_filing_work(
        independent,
        independent_claim["lease_token"],
        "RETRYABLE",
        error_class="PROVIDER",
        error_summary="PROVIDER_UNAVAILABLE",
    )
    if len(repo.get_filing_attempt_history(base)) != 2:
        raise RuntimeError("filing attempt history was not retained")

    direct_reclaim = {
        **base,
        "filing_type": "Q3",
        "period_end": "2025-09-30",
        "source_url": "https://ci.example/q3.zip",
        "expected_checksum": "e" * 64,
    }
    repo.sync_reviewed_filings([direct_reclaim])
    first_claim = repo.claim_filing_work(
        direct_reclaim, "ci-reclaim-1", lease_seconds=1, run_id="ci-expiring"
    )
    if not first_claim:
        raise RuntimeError("initial short filing lease was not acquired")
    time.sleep(1.1)
    second_claim = repo.claim_filing_work(
        direct_reclaim, "ci-reclaim-2", lease_seconds=10, run_id="ci-reclaimed"
    )
    if not second_claim or second_claim["attempt_number"] != 2:
        raise RuntimeError("claim did not reclaim an expired lease")
    repo.finalize_filing_work(
        direct_reclaim,
        second_claim["lease_token"],
        "RETRYABLE",
        error_class="PROVIDER",
        error_summary="PROVIDER_UNAVAILABLE",
    )
    if (
        repo.get_filing_attempt_history(direct_reclaim)[0]["outcome_state"]
        != "RETRYABLE"
    ):
        raise RuntimeError("expired attempt was not durably finalized")

    quarantine = {
        **base,
        "filing_type": "Q2",
        "period_end": "2025-06-30",
        "source_url": "https://ci.example/q2.zip",
        "expected_checksum": "c" * 64,
    }
    repo.sync_reviewed_filings([quarantine])
    quarantined_id = artifact(
        quarantine["source_url"], quarantine["expected_checksum"], "QUARANTINED"
    )
    qclaim = repo.claim_filing_work(quarantine, "ci-quarantine", run_id="ci-q")
    if not qclaim:
        raise RuntimeError("quarantine filing lease was not acquired")
    repo.finalize_filing_work(
        quarantine,
        qclaim["lease_token"],
        "QUARANTINED",
        artifact_id=quarantined_id,
        checksum=quarantine["expected_checksum"],
        error_class="VALIDATION",
        error_summary="VALIDATION_FAILED",
    )
    statuses = repo.get_filing_work_statuses([base, quarantine])
    if {row["state"] for row in statuses} != {"ACCEPTED", "QUARANTINED"}:
        raise RuntimeError("terminal filing statuses are not deterministic")
    if repo.get_filing_work_counts()["PENDING"] != 0:
        raise RuntimeError("filing work aggregate counts are incorrect")

    # Exercise the repository finalize seam while a contender holds an artifact update lock.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT artifact_id FROM filing_work_items WHERE issuer_id=%s AND filing_type='Q1' AND state='ACCEPTED'",
            (issuer,),
        )
        accepted_row = cursor.fetchone()
        if not accepted_row:
            raise RuntimeError("accepted filing artifact was not persisted")
        accepted_artifact = accepted_row[0]
    race_item = {
        **base,
        "filing_type": "RACE",
        "period_end": "2025-11-30",
        "source_url": "https://ci.example/race.zip",
        "expected_checksum": "8" * 64,
    }
    repo.sync_reviewed_filings([race_item])
    race_artifact = artifact(
        race_item["source_url"], race_item["expected_checksum"], "ACCEPTED"
    )
    race_claim = repo.claim_filing_work(race_item, "ci-race", run_id="ci-race")
    if not race_claim:
        raise RuntimeError("artifact race filing lease was not acquired")
    contender = connect()
    try:
        with contender.cursor() as cursor:
            cursor.execute(
                "UPDATE source_artifacts SET checksum=%s WHERE id=%s",
                ("e" * 64, race_artifact),
            )
        finalize_pool = ThreadPoolExecutor(max_workers=1)
        finalize_future = finalize_pool.submit(
            repo.finalize_filing_work,
            race_item,
            race_claim["lease_token"],
            "ACCEPTED",
            artifact_id=race_artifact,
            checksum=race_item["expected_checksum"],
        )
        try:
            finalize_future.result(timeout=0.3)
        except FuturesTimeoutError:
            pass
        else:
            raise RuntimeError(
                "repository finalize did not lock the contested artifact"
            )
        contender.rollback()
        contender.close()
        if finalize_future.result(timeout=3) is None:
            raise RuntimeError("repository finalize lost the artifact race")
        finalize_pool.shutdown(wait=True)
    finally:
        if not contender.closed:
            contender.rollback()
            contender.close()

    def racing_artifact_update():
        contender = connect()
        try:
            with contender.cursor() as cursor:
                cursor.execute(
                    "UPDATE source_artifacts SET checksum=%s WHERE id=%s",
                    ("e" * 64, race_artifact),
                )
            contender.commit()
            return False
        except Exception:
            contender.rollback()
            return True
        finally:
            contender.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        blocked_or_rejected = pool.submit(racing_artifact_update).result()
    if not blocked_or_rejected:
        raise RuntimeError("terminal artifact race was not rejected")
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT fwi.artifact_checksum, sa.checksum
               FROM filing_work_items fwi JOIN source_artifacts sa ON sa.id=fwi.artifact_id
               WHERE fwi.issuer_id=%s AND fwi.filing_type='Q1' AND fwi.state='ACCEPTED'""",
            (issuer,),
        )
        agreement = cursor.fetchone()
        if not agreement or agreement[0] != agreement[1]:
            raise RuntimeError("terminal filing artifact rows disagree")
        cursor.execute(
            """SELECT fwi.artifact_checksum, sa.checksum
               FROM filing_work_items fwi JOIN source_artifacts sa ON sa.id=fwi.artifact_id
               WHERE fwi.issuer_id=%s AND fwi.filing_type='RACE' AND fwi.state='ACCEPTED'""",
            (issuer,),
        )
        race_agreement = cursor.fetchone()
        if not race_agreement or race_agreement[0] != race_agreement[1]:
            raise RuntimeError("artifact race final rows disagree")
        for statement, params in (
            (
                "UPDATE source_artifacts SET checksum=%s WHERE id=%s",
                ("d" * 64, accepted_artifact),
            ),
            (
                "UPDATE filing_work_attempts SET outcome_state='RETRYABLE' WHERE issuer_id=%s AND attempt_number=2",
                (issuer,),
            ),
            (
                "DELETE FROM filing_work_attempts WHERE issuer_id=%s AND attempt_number=2",
                (issuer,),
            ),
        ):
            try:
                cursor.execute(statement, params)
            except Exception:
                connection.rollback()
            else:
                raise RuntimeError("terminal filing ledger mutation was allowed")
        cursor.execute("SELECT count(*) FROM filings")
        if cursor.fetchone()[0] != filings_before:
            raise RuntimeError(
                "filing ledger operations interfered with point-in-time filings"
            )

    connection.commit()


def verify_disposable_database_identity(connection: Any) -> None:
    """Allow down/re-up only through a loopback client endpoint to named CI databases."""
    database = str(connection.info.dbname)
    user = str(connection.info.user)
    host = str(getattr(connection.info, "host", "") or "")
    if (
        user != "pasticuan_ci"
        or database not in {"pasticuan_ci", "pasticuan_ascii"}
        or host not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise RuntimeError(
            "disposable down/re-up requires a named CI database on loopback"
        )


def verify_filing_work_catalog(connection: Any) -> None:
    """Check migration-007's required relations, constraints, indexes, and triggers."""
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT conname,contype,pg_get_constraintdef(oid)
               FROM pg_constraint
               WHERE conrelid IN ('public.filing_work_items'::regclass,'public.filing_work_attempts'::regclass)"""
        )
        constraints = {
            normalize_version(row[0]): (
                normalize_version(row[1]),
                normalize_version(row[2]),
            )
            for row in cursor.fetchall()
        }
        required_constraints = {
            "filing_work_identity_pkey": (
                "p",
                "PRIMARY KEY (issuer_id, filing_type, period_end, restatement_version)",
            ),
            "filing_work_state_check": (
                "c",
                "state = ANY",
                "PENDING",
                "RUNNING",
                "ACCEPTED",
                "QUARANTINED",
                "RETRYABLE",
            ),
            "filing_work_lease_fields_check": (
                "c",
                "state = 'RUNNING'",
                "lease_token IS NOT NULL",
                "lease_owner IS NOT NULL",
                "lease_expires_at IS NOT NULL",
            ),
            "filing_work_quarantine_reason_check": (
                "c",
                "state <> 'QUARANTINED'",
                "artifact_status = 'QUARANTINED'",
                "last_error_summary IS NOT NULL",
                "btrim(last_error_summary)",
            ),
            "filing_work_accepted_artifact_check": (
                "c",
                "state <> 'ACCEPTED'",
                "accepted_artifact_id = artifact_id",
            ),
            "filing_work_accepted_checksum_check": (
                "c",
                "state <> 'ACCEPTED'",
                "accepted_checksum = artifact_checksum",
            ),
            "filing_work_accepted_status_check": (
                "c",
                "state <> 'ACCEPTED'",
                "artifact_status = 'ACCEPTED'",
            ),
            "filing_work_attempt_lease_unique": (
                "u",
                "UNIQUE (issuer_id, filing_type, period_end, restatement_version, lease_token)",
            ),
            "filing_work_attempt_number_unique": (
                "u",
                "UNIQUE (issuer_id, filing_type, period_end, restatement_version, attempt_number)",
            ),
            "filing_work_attempt_identity_fkey": (
                "f",
                "FOREIGN KEY (issuer_id, filing_type, period_end, restatement_version)",
            ),
            "filing_work_attempt_completion_check": (
                "c",
                "finished_at IS NULL",
                "outcome_state IS NULL",
            ),
            "filing_work_attempt_error_class_check": ("c", "error_class = ANY"),
            "filing_work_attempt_error_summary_check": (
                "c",
                "error_summary = ANY",
                "PROVIDER_UNAVAILABLE",
                "UNKNOWN_FAILURE",
            ),
            "filing_work_error_class_length_check": (
                "c",
                "length(last_error_class) <= 32",
            ),
            "filing_work_error_summary_length_check": (
                "c",
                "length(last_error_summary) <= 64",
            ),
            "filing_work_attempt_error_class_length_check": (
                "c",
                "length(error_class) <= 32",
            ),
            "filing_work_attempt_error_summary_length_check": (
                "c",
                "length(error_summary) <= 64",
            ),
        }
        for name, expected in required_constraints.items():
            kind, *fragments = expected
            observed = constraints.get(name)
            if (
                not observed
                or observed[0] != kind
                or any(
                    fragment.lower() not in observed[1].lower()
                    for fragment in fragments
                )
            ):
                raise RuntimeError(
                    f"filing ledger constraint identity is incomplete: {name}"
                )
        cursor.execute(
            """SELECT i.indexrelid::regclass::text,i.indisunique,
                      array_agg(a.attname ORDER BY columns.ordinality)
               FROM pg_index i
               CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS columns(attnum,ordinality)
               JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=columns.attnum
               WHERE i.indrelid IN ('public.filing_work_items'::regclass,'public.filing_work_attempts'::regclass)
               GROUP BY i.indexrelid,i.indisunique"""
        )
        indexes = {
            normalize_version(row[0]): (
                bool(row[1]),
                tuple(normalize_version(column) for column in row[2]),
            )
            for row in cursor.fetchall()
        }
        required_indexes = {
            "filing_work_items_state_idx": (
                False,
                ("state", "lease_expires_at", "period_end", "issuer_id", "filing_type"),
            ),
            "filing_work_attempts_identity_idx": (
                False,
                (
                    "issuer_id",
                    "filing_type",
                    "period_end",
                    "restatement_version",
                    "attempt_number",
                ),
            ),
        }
        if any(
            name not in indexes
            or indexes[name][0] != unique
            or indexes[name][1] != columns
            for name, (unique, columns) in required_indexes.items()
        ):
            raise RuntimeError("filing ledger indexes are incomplete")
        cursor.execute(
            """SELECT tgname,pg_get_triggerdef(oid) FROM pg_trigger
               WHERE tgrelid IN ('public.filing_work_items'::regclass,'public.filing_work_attempts'::regclass,'public.source_artifacts'::regclass)
                 AND NOT tgisinternal"""
        )
        triggers = {
            normalize_version(row[0]): normalize_version(row[1]).lower()
            for row in cursor.fetchall()
        }
        required_triggers = {
            "filing_work_acceptance_guard": "before insert or update",
            "filing_work_initial_state_guard": "before insert",
            "filing_work_item_clock_guard": "before insert",
            "filing_work_item_transition_guard": "before update",
            "filing_work_attempt_insert_guard": "before insert",
            "filing_work_attempt_update_guard": "before update",
            "filing_work_attempt_delete_guard": "before delete",
            "filing_work_artifact_drift_guard": "before update of parse_status, checksum, source_url",
            "filing_work_attempt_completion_guard": "deferrable initially deferred",
        }
        if any(
            name not in triggers or fragment not in triggers[name]
            for name, fragment in required_triggers.items()
        ):
            raise RuntimeError("filing ledger trigger identity is incomplete")


def verify_filing_work_privileges(connection: Any) -> None:
    """Verify exact direct privileges for each ledger role after role re-apply."""
    expected = {
        "pasticuan_ingest": (True, True, True, False),
        "pasticuan_validator": (True, False, False, False),
        "pasticuan_bot": (False, False, False, False),
    }
    with connection.cursor() as cursor:
        for table in ("filing_work_items", "filing_work_attempts"):
            for role, privileges in expected.items():
                cursor.execute(
                    """SELECT has_table_privilege(%s,%s,'SELECT'),
                              has_table_privilege(%s,%s,'INSERT'),
                              has_table_privilege(%s,%s,'UPDATE'),
                              has_table_privilege(%s,%s,'DELETE')""",
                    (
                        role,
                        f"public.{table}",
                        role,
                        f"public.{table}",
                        role,
                        f"public.{table}",
                        role,
                        f"public.{table}",
                    ),
                )
                observed = cursor.fetchone()
                if observed != privileges:
                    raise RuntimeError(
                        f"unexpected filing ledger privileges for {role} on {table}"
                    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--migrations", type=Path, default=Path("storage/migrations"))
    parser.add_argument(
        "--base-ref", help="git ref whose existing migrations must remain immutable"
    )
    parser.add_argument(
        "--verify-disposable-down-reup",
        action="store_true",
        help="run migration-007 down/re-up only on a named disposable CI database",
    )
    args = parser.parse_args()
    import psycopg

    migration_pairs(args.migrations)
    if args.base_ref:
        immutable_against(args.migrations, args.base_ref)
    with psycopg.connect(args.database_url, autocommit=False) as connection:
        apply_migrations(connection, args.migrations)
        apply_migrations(connection, args.migrations)
        repository_compatibility(connection, set(migration_checksums(args.migrations)))
        roles = Path("storage/supabase_roles.sql")
        if roles.exists():
            with connection.cursor() as cursor:
                cursor.execute(read_sql(roles))
            connection.commit()
            verify_filing_work_privileges(connection)
            verify_filing_work_catalog(connection)
        filing_work_behavior(connection, args.database_url)
        if args.verify_disposable_down_reup:
            verify_disposable_database_identity(connection)
            down = args.migrations / "007_filing_work_ledger.down.sql"
            up = args.migrations / "007_filing_work_ledger.up.sql"
            with connection.cursor() as cursor:
                cursor.execute(read_sql(down))
                cursor.execute(read_sql(up))
            connection.commit()
            if roles.exists():
                with connection.cursor() as cursor:
                    cursor.execute(read_sql(roles))
                connection.commit()
                verify_filing_work_privileges(connection)
            verify_filing_work_catalog(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regclass('public.filing_work_items'), to_regclass('public.filing_work_attempts')"
                )
                relation_names = cursor.fetchone()
                if not relation_names or tuple(
                    normalize_version(value) for value in relation_names
                ) != (
                    "filing_work_items",
                    "filing_work_attempts",
                ):
                    raise RuntimeError("migration-007 disposable down/re-up failed")
    print(f"verified {len(migration_checksums(args.migrations))} migrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
