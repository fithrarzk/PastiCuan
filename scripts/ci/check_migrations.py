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
import subprocess
import sys


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


def repository_compatibility(connection: Any) -> None:
    """Exercise the repository's read-only migration seam without providers."""
    project_root = str(Path.cwd())
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from storage.repository import SnapshotRepository

    migrations = SnapshotRepository(lambda: connection).applied_schema_migrations()
    if not migrations:
        raise RuntimeError("repository cannot observe applied migrations")


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
        repository_compatibility(connection)
    print(f"verified {len(migration_checksums(args.migrations))} migrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
