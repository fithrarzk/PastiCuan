"""Apply and verify the repository's PostgreSQL migrations in CI.

This helper intentionally uses a database URL supplied by the ephemeral CI
service. It never creates a production connection and never runs down
migrations.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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
    repo.sync_reviewed_filings([base])
    repo.sync_reviewed_filings([base])
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM filing_work_items WHERE issuer_id=%s", (issuer,)
        )
        assert cursor.fetchone()[0] == 1
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

    # Terminal artifacts and completed attempts cannot be rewritten by the ingest role.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT artifact_id FROM filing_work_items WHERE issuer_id=%s", (issuer,)
        )
        accepted_row = cursor.fetchone()
        if not accepted_row:
            raise RuntimeError("accepted filing artifact was not persisted")
        accepted_artifact = accepted_row[0]
        for statement, params in (
            (
                "UPDATE source_artifacts SET checksum=%s WHERE id=%s",
                ("d" * 64, accepted_artifact),
            ),
            (
                "UPDATE filing_work_attempts SET outcome_state='RETRYABLE' WHERE issuer_id=%s AND attempt_number=2",
                (issuer,),
            ),
        ):
            try:
                cursor.execute(statement, params)
            except Exception:
                connection.rollback()
            else:
                raise RuntimeError("terminal filing ledger mutation was allowed")

    connection.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--migrations", type=Path, default=Path("storage/migrations"))
    parser.add_argument(
        "--base-ref", help="git ref whose existing migrations must remain immutable"
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
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT has_table_privilege('pasticuan_ingest','public.filing_work_items','UPDATE')"
                )
                privilege = cursor.fetchone()
                if not privilege or not privilege[0]:
                    raise RuntimeError(
                        "ingest role lacks filing ledger write privilege"
                    )
                cursor.execute(
                    "SELECT has_table_privilege('pasticuan_bot','public.filing_work_items','SELECT')"
                )
                privilege = cursor.fetchone()
                if privilege and privilege[0]:
                    raise RuntimeError("bot role has filing ledger access")
                cursor.execute(
                    "SELECT has_table_privilege('pasticuan_ingest','public.filing_work_items','DELETE'), has_table_privilege('pasticuan_validator','public.filing_work_items','DELETE')"
                )
                delete_privileges = cursor.fetchone()
                if delete_privileges and any(delete_privileges):
                    raise RuntimeError("ledger role has destructive delete privilege")
            connection.commit()
        filing_work_behavior(connection, args.database_url)
        down = args.migrations / "007_filing_work_ledger.down.sql"
        up = args.migrations / "007_filing_work_ledger.up.sql"
        with connection.cursor() as cursor:
            cursor.execute(read_sql(down))
            cursor.execute(read_sql(up))
        connection.commit()
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
