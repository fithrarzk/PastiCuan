"""Validate reviewed IDX filing manifest identity and monotonicity."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

try:
    from data.filing_manifest import exact_identity, validate_filing_row
except ModuleNotFoundError:  # direct execution from scripts/ci in GitHub Actions
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from data.filing_manifest import exact_identity, validate_filing_row


FILING_REQUIRED = {
    "ticker",
    "source_url",
    "published_at",
    "filing_type",
    "period_end",
    "restatement_version",
    "audit_status",
}
SOURCE_REQUIRED = {"source_url"}


def records(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        result = payload.get("filings", payload.get("sources", payload))
    else:
        result = payload
    if not isinstance(result, list):
        raise ValueError("manifest must be a list or contain a filings list")
    return result


def validate_manifest(
    path: Path, baseline: Path | None = None, *, kind: str | None = None
) -> list[str]:
    errors: list[str] = []
    current = records(path)
    is_source_manifest = kind == "source" or (
        kind is None and bool(current) and "ticker" not in current[0]
    )
    identities: set[tuple[Any, ...]] = set()
    for index, entry in enumerate(current):
        required = SOURCE_REQUIRED if is_source_manifest else FILING_REQUIRED
        missing = required - set(entry)
        if missing:
            errors.append(f"entry {index} missing: {', '.join(sorted(missing))}")
            if not is_source_manifest:
                fallback = (
                    str(entry.get("ticker", "")).strip().upper().removesuffix(".JK"),
                    str(entry.get("filing_type", "")).strip().upper(),
                    str(entry.get("period_end", "")).strip(),
                    entry.get("restatement_version"),
                )
                if fallback in identities:
                    errors.append(f"duplicate filing identity: {fallback}")
                identities.add(fallback)
            continue
        if not is_source_manifest:
            errors.extend(
                f"entry {index} {error}" for error in validate_filing_row(entry)
            )
            try:
                normalized = exact_identity(entry)
            except ValueError:
                normalized = None
            if normalized is not None and normalized in identities:
                errors.append(f"duplicate filing identity: {normalized}")
            if normalized is not None:
                identities.add(normalized)
            continue
        ticker = str(entry.get("ticker", "")).strip().upper().replace(".JK", "")
        parsed = urlparse(str(entry["source_url"]))
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            errors.append(f"entry {index} source URL must use HTTPS")
        if not is_source_manifest and not (
            host == "idx.id"
            or host.endswith(".idx.id")
            or host == "idx.co.id"
            or host.endswith(".idx.co.id")
        ):
            errors.append(f"entry {index} is not an official IDX URL")
        if not is_source_manifest and not parsed.path.lower().endswith(".zip"):
            errors.append(f"entry {index} is not an IDX filing attachment")
        if not is_source_manifest and (
            not ticker
            or not str(entry["filing_type"]).strip()
            or not str(entry["period_end"]).strip()
        ):
            errors.append(f"entry {index} has an empty filing identity")
        if not is_source_manifest:
            version = entry.get("restatement_version")
            if (
                isinstance(version, bool)
                or not isinstance(version, int)
                or version <= 0
            ):
                errors.append(
                    f"entry {index} restatement_version must be a positive integer"
                )
        if is_source_manifest and (
            not str(entry.get("provider", "")).strip()
            or not str(entry.get("artifact_type", "")).strip()
        ):
            errors.append(
                f"entry {index} source identity requires provider and artifact_type"
            )
        identity: tuple[Any, ...]
        if is_source_manifest:
            identity = (
                entry.get("provider"),
                entry.get("artifact_type"),
                str(entry["source_url"]),
            )
        else:
            identity = (
                ticker,
                entry["filing_type"],
                entry["period_end"],
                entry.get("restatement_version"),
            )
        if identity in identities:
            errors.append(f"duplicate filing identity: {identity}")
        identities.add(identity)
    if baseline and baseline.exists():
        old = records(baseline)

        old_exact: dict[tuple[str, str, str, int], dict] = {}
        new_exact: dict[tuple[str, str, str, int], dict] = {}
        if not is_source_manifest:
            for label, rows, target in (
                ("baseline", old, old_exact),
                ("current", current, new_exact),
            ):
                for index, entry in enumerate(rows):
                    row_errors = validate_filing_row(entry)
                    errors.extend(
                        f"{label} entry {index} {error}" for error in row_errors
                    )
                    if not row_errors:
                        target[exact_identity(entry)] = entry

        def base_identity(entry: dict) -> tuple[Any, ...]:
            if is_source_manifest:
                return (
                    entry.get("provider"),
                    entry.get("artifact_type"),
                    str(entry.get("source_url")),
                )
            return (
                str(entry.get("ticker", "")).upper().replace(".JK", ""),
                entry.get("filing_type"),
                entry.get("period_end"),
            )

        old_ids: set[tuple[Any, ...]]
        new_ids: set[tuple[Any, ...]]
        if is_source_manifest:
            old_ids = {
                (
                    entry.get("provider"),
                    entry.get("artifact_type"),
                    str(entry.get("source_url")),
                )
                for entry in old
            }
            new_ids = {
                (
                    entry.get("provider"),
                    entry.get("artifact_type"),
                    str(entry.get("source_url")),
                )
                for entry in current
            }
        else:
            old_ids = set(old_exact)
            new_ids = set(new_exact)
            # Keep removal diagnostics useful for malformed legacy rows; valid
            # identity comparisons above always use the shared contract.
            old_ids.update(
                (
                    str(entry.get("ticker", "")).strip().upper().removesuffix(".JK"),
                    str(entry.get("filing_type", "")).strip().upper(),
                    str(entry.get("period_end", "")).strip(),
                    entry.get("restatement_version"),
                )
                for entry in old
                if validate_filing_row(entry)
            )
            new_ids.update(
                (
                    str(entry.get("ticker", "")).strip().upper().removesuffix(".JK"),
                    str(entry.get("filing_type", "")).strip().upper(),
                    str(entry.get("period_end", "")).strip(),
                    entry.get("restatement_version"),
                )
                for entry in current
                if validate_filing_row(entry)
            )
        removed = old_ids - new_ids
        if removed:
            errors.append(f"filing identities removed: {sorted(removed)[:5]}")
        if not is_source_manifest:
            old_versions = {
                identity[:3]: max(
                    exact[3] for exact in old_exact if exact[:3] == identity[:3]
                )
                for identity in old_exact
            }
            regressions = [
                identity[:3]
                for identity in new_exact
                if identity not in old_exact
                and identity[:3] in old_versions
                and identity[3] < old_versions[identity[:3]]
            ]
            if regressions:
                errors.append(
                    f"filing restatement version regressed: {sorted(regressions)[:5]}"
                )
            for identity in old_exact.keys() & new_exact.keys():
                if any(
                    old_exact[identity].get(field) != new_exact[identity].get(field)
                    for field in (
                        "source_url",
                        "published_at",
                        "audit_status",
                        "checksum",
                    )
                ):
                    errors.append(f"filing provenance conflict: {identity}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--kind", choices=("filing", "source"))
    args = parser.parse_args()
    errors = validate_manifest(args.manifest, args.baseline, kind=args.kind)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"manifest validation passed: {len(records(args.manifest))} filings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
