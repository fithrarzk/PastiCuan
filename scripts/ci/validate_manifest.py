"""Validate reviewed IDX filing manifest identity and monotonicity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
from typing import Any


REQUIRED = {"ticker", "source_url", "published_at", "filing_type", "period_end"}


def records(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        result = payload.get("filings", payload.get("sources", payload))
    else:
        result = payload
    if not isinstance(result, list):
        raise ValueError("manifest must be a list or contain a filings list")
    return result


def validate_manifest(path: Path, baseline: Path | None = None) -> list[str]:
    errors: list[str] = []
    current = records(path)
    is_source_manifest = bool(current) and "ticker" not in current[0]
    identities: set[tuple[Any, ...]] = set()
    for index, entry in enumerate(current):
        required = {"source_url"} if is_source_manifest else REQUIRED
        missing = required - set(entry)
        if missing:
            errors.append(f"entry {index} missing: {', '.join(sorted(missing))}")
            continue
        ticker = str(entry.get("ticker", "")).strip().upper().replace(".JK", "")
        parsed = urlparse(str(entry["source_url"]))
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (host == "idx.id" or host.endswith(".idx.id") or host == "idx.co.id" or host.endswith(".idx.co.id")):
            errors.append(f"entry {index} is not an official IDX URL")
        identity: tuple[Any, ...]
        if is_source_manifest:
            identity = (entry.get("provider"), entry.get("artifact_type"), str(entry["source_url"]))
        else:
            identity = (ticker, entry["filing_type"], entry["period_end"], entry.get("restatement_version", 1))
        if identity in identities:
            errors.append(f"duplicate filing identity: {identity}")
        identities.add(identity)
    if baseline and baseline.exists():
        old = records(baseline)
        def base_identity(entry: dict) -> tuple[Any, ...]:
            if is_source_manifest:
                return (entry.get("provider"), entry.get("artifact_type"), str(entry.get("source_url")))
            return (str(entry.get("ticker", "")).upper().replace(".JK", ""), entry.get("filing_type"), entry.get("period_end"))

        old_ids = {base_identity(entry) for entry in old}
        new_ids = {base_identity(entry) for entry in current}
        removed = old_ids - new_ids
        if removed:
            errors.append(f"filing identities removed: {sorted(removed)[:5]}")
        if not is_source_manifest:
            old_versions = {base_identity(entry): int(entry.get("restatement_version", 1)) for entry in old}
            new_versions = {base_identity(entry): int(entry.get("restatement_version", 1)) for entry in current}
            regressions = [identity for identity in old_versions.keys() & new_versions.keys() if new_versions[identity] < old_versions[identity]]
            if regressions:
                errors.append(f"filing restatement version regressed: {sorted(regressions)[:5]}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    errors = validate_manifest(args.manifest, args.baseline)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"manifest validation passed: {len(records(args.manifest))} filings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
