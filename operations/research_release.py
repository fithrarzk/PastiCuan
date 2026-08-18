"""Reviewed SHADOW release metadata and deterministic calculation provenance."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any


DEFAULT_RELEASE_PATH = "data/research_release.json"
REQUIRED_FIELDS = {
    "release_id", "model_version", "formula_version", "calculation_revision",
    "status", "calculation_paths",
}


def _root_for(path: str | Path) -> Path:
    source = Path(path).resolve()
    return source.parent.parent if source.parent.name == "data" else Path.cwd().resolve()


def load_release(path: str | Path = DEFAULT_RELEASE_PATH) -> dict[str, Any]:
    source = Path(path)
    payload = json.loads(source.read_text())
    if not isinstance(payload, dict):
        raise ValueError("Research release must be a JSON object.")
    missing = REQUIRED_FIELDS - set(payload)
    if missing:
        raise ValueError(f"Research release is missing: {', '.join(sorted(missing))}.")
    if payload["status"] != "SHADOW":
        raise ValueError("Automatic research publication is restricted to SHADOW releases.")
    if not isinstance(payload["calculation_paths"], list) or not payload["calculation_paths"]:
        raise ValueError("Research release calculation_paths must be a non-empty list.")
    if not isinstance(payload["calculation_revision"], int) or payload["calculation_revision"] < 1:
        raise ValueError("Research release calculation_revision must be a positive integer.")
    return payload


def calculation_digest(
    release: dict[str, Any], *, repository_root: str | Path | None = None,
) -> str:
    root = Path(repository_root).resolve() if repository_root else Path.cwd().resolve()
    digest = hashlib.sha256()
    identity = {
        key: release[key]
        for key in ("release_id", "model_version", "formula_version", "calculation_revision", "status")
    }
    digest.update(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    for relative in sorted(set(release["calculation_paths"])):
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Calculation path escapes the repository: {relative}") from exc
        if not candidate.is_file():
            raise ValueError(f"Calculation path does not exist: {relative}")
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(candidate.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def release_provenance(
    path: str | Path = DEFAULT_RELEASE_PATH, *, repository_root: str | Path | None = None,
    market_session: str | None = None,
) -> dict[str, Any]:
    release = load_release(path)
    root = Path(repository_root).resolve() if repository_root else _root_for(path)
    result = {
        "type": "research_release",
        "release_id": release["release_id"],
        "model_version": release["model_version"],
        "formula_version": release["formula_version"],
        "calculation_revision": release["calculation_revision"],
        "calculation_digest": calculation_digest(release, repository_root=root),
        "git_commit": os.getenv("GITHUB_SHA") or "local",
    }
    if market_session:
        result["market_session"] = market_session
    return result


def release_from_sources(sources: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    return next((item for item in sources or [] if item.get("type") == "research_release"), None)


def check_release_change(base_ref: str, path: str = DEFAULT_RELEASE_PATH) -> dict[str, Any]:
    """Require an explicit release revision when calculation code changes."""
    current = load_release(path)
    changed = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    relevant = sorted(set(changed) & set(current["calculation_paths"]))
    if not relevant:
        return {"calculation_changed": False, "changed_paths": []}
    try:
        previous_raw = subprocess.run(
            ["git", "show", f"{base_ref}:{path}"], check=True,
            capture_output=True, text=True,
        ).stdout
        previous = json.loads(previous_raw)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return {"calculation_changed": True, "changed_paths": relevant, "new_release": True}
    identity = ("release_id", "model_version", "formula_version", "calculation_revision")
    if all(previous.get(key) == current.get(key) for key in identity):
        raise ValueError(
            "Calculation code changed without a research release revision: " + ", ".join(relevant)
        )
    return {"calculation_changed": True, "changed_paths": relevant, "new_release": False}
