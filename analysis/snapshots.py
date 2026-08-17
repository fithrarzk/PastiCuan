"""Approved research snapshots used by the low-latency Railway bot.

Only immutable SHADOW or VALIDATED_RESEARCH snapshots are loadable. Candidate
artifacts are deliberately rejected so a scheduled ingestion job cannot alter
Telegram output before review.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any


SNAPSHOT_SCHEMA_VERSION = "2.0"
SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS = {"1.0", "2.0"}
APPROVED_STATUSES = {"SHADOW", "VALIDATED_RESEARCH"}


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


@dataclass(frozen=True)
class ResearchSnapshot:
    snapshot_id: str
    effective_at: str
    created_at: str
    model_version: str
    model_status: str
    universe: str = "LQ45"
    formula_version: str = "lq45-cross-section-v4+business-quality-v1"
    schema_version: str = SNAPSHOT_SCHEMA_VERSION
    validation_run_id: str | None = None
    constituents: list[str] = field(default_factory=list)
    rankings: dict[str, dict[str, Any]] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    signature: str | None = None
    signing_key_id: str | None = None
    checksum: str = ""

    def unsigned_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("checksum", None)
        payload.pop("signature", None)
        payload.pop("signing_key_id", None)
        return payload

    def calculated_checksum(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = self.unsigned_dict()
        payload["signature"] = self.signature
        payload["signing_key_id"] = self.signing_key_id
        payload["checksum"] = self.checksum or self.calculated_checksum()
        return payload

    def ticker(self, ticker: str) -> dict[str, Any] | None:
        return self.rankings.get(ticker.upper().replace(".JK", ""))

    def validate(self, *, approved_only: bool = True) -> None:
        if self.schema_version not in SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported snapshot schema {self.schema_version}.")
        if approved_only and self.model_status not in APPROVED_STATUSES:
            raise ValueError("Only reviewed SHADOW or VALIDATED_RESEARCH snapshots may be loaded.")
        if not approved_only and self.model_status not in APPROVED_STATUSES | {"CANDIDATE"}:
            raise ValueError("Unknown snapshot model status.")
        if not self.snapshot_id or not self.effective_at or not self.model_version:
            raise ValueError("Snapshot identity, effective time and model version are required.")
        datetime.fromisoformat(self.effective_at.replace("Z", "+00:00"))
        if not self.checksum or self.checksum != self.calculated_checksum():
            raise ValueError("Snapshot checksum is missing or invalid.")
        from analysis.signing import verify_checksum
        if not verify_checksum(self.checksum, self.signature):
            raise ValueError("Snapshot Ed25519 signature is missing or invalid.")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResearchSnapshot":
        if isinstance(payload, str):
            payload = json.loads(payload)
        allowed = set(cls.__dataclass_fields__)
        snapshot = cls(**{key: value for key, value in payload.items() if key in allowed})
        snapshot.validate()
        return snapshot


def write_snapshot(snapshot: ResearchSnapshot, path: str | Path, *, allow_candidate: bool = False) -> None:
    """Write deterministically; callers must explicitly approve the status."""
    resolved = snapshot
    if not snapshot.checksum or not snapshot.signature:
        checksum = snapshot.checksum or snapshot.calculated_checksum()
        from analysis.signing import sign_checksum
        signature, key_id = sign_checksum(checksum)
        resolved = ResearchSnapshot(**{
            **snapshot.unsigned_dict(), "checksum": checksum,
            "signature": signature or snapshot.signature,
            "signing_key_id": key_id or snapshot.signing_key_id,
        })
    resolved.validate(approved_only=not allow_candidate)
    payload = resolved.to_dict()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = _canonical(payload)
    if destination.suffix == ".gz":
        with destination.open("wb") as stream:
            with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as handle:
                handle.write(raw)
    else:
        destination.write_bytes(raw)


def load_snapshot(path: str | Path) -> ResearchSnapshot:
    source = Path(path)
    raw = gzip.open(source, "rb").read() if source.suffix == ".gz" else source.read_bytes()
    return ResearchSnapshot.from_dict(json.loads(raw))


def empty_shadow_snapshot(reason: str | None = None) -> ResearchSnapshot:
    now = datetime.now(timezone.utc).isoformat()
    base = ResearchSnapshot(
        snapshot_id="bundled-empty-shadow",
        effective_at="1970-01-01T00:00:00+00:00",
        created_at=now,
        model_version="lq45-factor-v1-shadow",
        model_status="SHADOW",
        warnings=[reason or "No approved historical LQ45 snapshot is bundled."],
    )
    return ResearchSnapshot(**{**base.unsigned_dict(), "checksum": base.calculated_checksum()})


class SnapshotManager:
    """Process-local snapshot cache with a safe bundled fallback."""

    def __init__(self, path: str | None = None):
        self.path = path or os.getenv("RESEARCH_SNAPSHOT_PATH", "data/snapshots/latest.json.gz")
        self._snapshot: ResearchSnapshot | None = None
        self._loaded_at = 0.0
        self._lock = Lock()

    def get(self, *, refresh: bool = False) -> ResearchSnapshot:
        with self._lock:
            ttl = max(30.0, min(900.0, float(os.getenv("SNAPSHOT_CACHE_TTL_SECONDS", "300"))))
            if self._snapshot is not None and not refresh and monotonic() - self._loaded_at < ttl:
                return self._snapshot
            # Supabase is optional and never sits in the per-command hot path.
            # A bundled approved snapshot keeps Railway available when a Free
            # project is paused or the network is unavailable.
            if os.getenv("SUPABASE_DATABASE_URL"):
                try:
                    from storage.database import connect_from_env
                    from storage.repository import SnapshotRepository
                    remote = SnapshotRepository(connect_from_env).latest_approved_quant_snapshot()
                    if remote is not None:
                        self._snapshot = remote
                        self._loaded_at = monotonic()
                        return remote
                except Exception as exc:
                    database_warning = f"Supabase snapshot unavailable ({type(exc).__name__}); using bundled fallback."
                else:
                    database_warning = None
            else:
                database_warning = None
            try:
                self._snapshot = load_snapshot(self.path)
            except (OSError, ValueError, json.JSONDecodeError, TypeError):
                self._snapshot = empty_shadow_snapshot(database_warning)
            self._loaded_at = monotonic()
            return self._snapshot


_manager = SnapshotManager()


def get_research_snapshot(*, refresh: bool = False) -> ResearchSnapshot:
    return _manager.get(refresh=refresh)
