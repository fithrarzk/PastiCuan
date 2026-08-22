"""Cumulative, fail-closed merge for reviewed IDX filing manifests."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


class ManifestError(ValueError):
    """A manifest cannot safely be used as a merge input."""


FILING_REQUIRED = frozenset(
    {
        "ticker",
        "source_url",
        "published_at",
        "filing_type",
        "period_end",
        "restatement_version",
        "audit_status",
    }
)
_PROVENANCE_FIELDS = ("source_url", "published_at", "audit_status", "checksum")


def validate_filing_row(row: Mapping[str, Any]) -> list[str]:
    """Return deterministic schema/provenance errors for one filing row."""
    errors = (
        [f"missing: {', '.join(sorted(FILING_REQUIRED - set(row)))}"]
        if FILING_REQUIRED - set(row)
        else []
    )
    if errors:
        return errors
    try:
        exact_identity(row)
    except ManifestError as exc:
        errors.append(str(exc))
    url = str(row["source_url"])
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host == "idx.id"
        or host.endswith(".idx.id")
        or host == "idx.co.id"
        or host.endswith(".idx.co.id")
    ):
        errors.append("source URL must be HTTPS on an official IDX host")
    if not parsed.path.lower().endswith(".zip"):
        errors.append("source URL must be an IDX filing attachment")
    try:
        date.fromisoformat(str(row["period_end"]))
    except ValueError:
        errors.append("period_end must be an ISO date")
    try:
        datetime.fromisoformat(str(row["published_at"]))
    except ValueError:
        errors.append("published_at must be an ISO timestamp")
    if not str(row["audit_status"]).strip():
        errors.append("audit_status must not be empty")
    if "checksum" in row and not isinstance(row["checksum"], str):
        errors.append("checksum must be a string when present")
    return errors


def _filings(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("filings")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ManifestError("manifest must contain a filings list of objects")
    return rows


def exact_identity(row: Mapping[str, Any]) -> tuple[str, str, str, int]:
    try:
        version = row["restatement_version"]
        if type(version) is not int:
            raise TypeError
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(
            "restatement_version is required and must be positive"
        ) from exc
    if version <= 0:
        raise ManifestError("restatement_version is required and must be positive")
    ticker = str(row.get("ticker", "")).strip().upper().removesuffix(".JK")
    filing_type = str(row.get("filing_type", "")).strip().upper()
    period_end = str(row.get("period_end", "")).strip()
    if not ticker or not filing_type or not period_end:
        raise ManifestError("filing identity fields must not be empty")
    return ticker, filing_type, period_end, version


def base_identity(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return exact_identity(row)[:3]


def _validate(
    rows: list[dict[str, Any]], label: str
) -> dict[tuple[str, str, str, int], dict[str, Any]]:
    indexed: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for row in rows:
        errors = validate_filing_row(row)
        if errors:
            raise ManifestError(f"invalid {label} filing: {'; '.join(errors)}")
        identity = exact_identity(row)
        if identity in indexed:
            raise ManifestError(f"duplicate exact identity in {label}: {identity}")
        indexed[identity] = row
    return indexed


def _provenance_conflict(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return any(left.get(field) != right.get(field) for field in _PROVENANCE_FIELDS)


def merge_manifests(
    baseline: Mapping[str, Any], discovered: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge a discovery draft into reviewed history without mutating either input."""
    old = _validate(_filings(baseline), "baseline")
    new = _validate(_filings(discovered), "discovered")
    old_versions: dict[tuple[str, str, str], int] = {}
    for identity in old:
        old_versions[identity[:3]] = max(old_versions.get(identity[:3], 0), identity[3])
    for identity, row in new.items():
        if identity in old and _provenance_conflict(old[identity], row):
            raise ManifestError(f"provenance conflict at exact identity: {identity}")
        if identity not in old and identity[3] < old_versions.get(
            identity[:3], identity[3]
        ):
            raise ManifestError(f"restatement version regression: {identity}")
    merged = dict(baseline)
    rows = {
        **old,
        **{identity: row for identity, row in new.items() if identity not in old},
    }
    merged["filings"] = [rows[identity] for identity in sorted(rows)]
    if "discovery" in discovered:
        merged["discovery"] = discovered["discovery"]
    return merged


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestError("manifest root must be an object")
    return value


def merge_files(baseline: Path, discovered: Path, output: Path) -> None:
    result = merge_manifests(_read(baseline), _read(discovered))
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(
                result,
                handle,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ": "),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--discovered", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        merge_files(args.baseline, args.discovered, args.output)
    except ManifestError as exc:
        print(f"manifest merge failed: {exc}")
        return 1
    print(f"manifest merge passed: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
