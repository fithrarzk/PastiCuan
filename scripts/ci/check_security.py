"""Fail-closed secret and dependency-input scanner for CI."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

PATTERNS = (
    (
        "database URL",
        re.compile(r"(?:postgres(?:ql)?|mysql|mongodb)://[^\s'\"]+", re.I),
    ),
    ("Telegram token", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
    (
        "cloud access key",
        re.compile(
            r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|(?:R2|AWS)_(?:SECRET_)?ACCESS_KEY(?:_ID)?\s*[:=]\s*['\"]?[A-Za-z0-9/+_=.-]{12,}",
            re.I,
        ),
    ),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "GitHub token",
        re.compile(r"\b(?:gh[ps]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
)


_ALLOWED_LOCAL_DATABASE_URLS = {
    "postgresql://test",
    "postgresql://pasticuan_ci:pasticuan_ci@localhost:5432/pasticuan_ci",
    "postgresql://pasticuan_ci:pasticuan_ci@localhost:5432/pasticuan_ascii",
}


def _safe_database_url(value: str, path: Path) -> bool:
    if value in _ALLOWED_LOCAL_DATABASE_URLS:
        return True
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        path.name == ".env.example"
        and parsed.hostname == "pooler.example"
        and parsed.password == "password"
    )


def scan_paths(paths: list[Path]) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for category, pattern in PATTERNS:
            for match in pattern.finditer(text):
                if category == "database URL" and _safe_database_url(
                    match.group(0), path
                ):
                    continue
                findings.append((str(path), category))
                break
    return findings


def tracked_paths() -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True)
    return [Path(raw) for raw in result.stdout.decode("utf-8").split("\0") if raw]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    findings = scan_paths(args.paths or tracked_paths())
    if findings:
        for path, category in findings:
            print(f"secret-like {category} found in {path}")
        return 1
    print("tracked-source secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
