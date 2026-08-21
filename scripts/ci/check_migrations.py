"""Apply and verify the repository's PostgreSQL migrations in CI.

This helper intentionally uses a database URL supplied by the ephemeral CI
service. It never creates a production connection and never runs down
migrations.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any


def migration_files(directory: Path) -> list[Path]:
    """Return ordered up migrations, rejecting duplicate version names."""
    files = sorted(directory.glob("*.up.sql"))
    versions = [path.name.removesuffix(".up.sql") for path in files]
    if len(versions) != len(set(versions)):
        raise ValueError("migration versions are duplicated")
    return files


def migration_checksums(directory: Path) -> dict[str, str]:
    return {
        path.name.removesuffix(".up.sql"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in migration_files(directory)
    }


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
            cursor.execute("SELECT checksum FROM ci_migration_checksums WHERE version=%s", (version,))
            recorded = cursor.fetchone()
            if recorded and recorded[0] != checksums[version]:
                raise RuntimeError(f"migration checksum changed after application: {version}")
            if not recorded:
                cursor.execute(path.read_text())
                cursor.execute(
                    "INSERT INTO ci_migration_checksums(version, checksum) VALUES (%s, %s)",
                    (version, checksums[version]),
                )
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        applied = {str(row[0]) for row in cursor.fetchall()}
    expected = set(checksums)
    if applied != expected:
        raise RuntimeError(f"migration ledger mismatch: expected {sorted(expected)}, got {sorted(applied)}")
    connection.commit()
    return checksums


def repository_compatibility(connection: Any) -> None:
    """Exercise the repository's read-only migration seam without providers."""
    from storage.repository import SnapshotRepository

    migrations = SnapshotRepository(lambda: connection).applied_schema_migrations()
    if not migrations:
        raise RuntimeError("repository cannot observe applied migrations")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--migrations", type=Path, default=Path("storage/migrations"))
    args = parser.parse_args()
    import psycopg

    with psycopg.connect(args.database_url, autocommit=False) as connection:
        apply_migrations(connection, args.migrations)
        repository_compatibility(connection)
    print(f"verified {len(migration_checksums(args.migrations))} migrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
