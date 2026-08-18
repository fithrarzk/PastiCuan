"""Immutable full-universe scan snapshots consumed by the Railway bot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
import os
from threading import Lock
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from analysis.contracts import ScanBundle


SCAN_SCHEMA_VERSION = "4.0"
SUPPORTED_SCAN_SCHEMA_VERSIONS = {"2.0", "3.0", "4.0"}
SCAN_MODES = {"PRIMARY", "DEGRADED", "UNAVAILABLE"}
JAKARTA = ZoneInfo("Asia/Jakarta")


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _ticker(value: str) -> str:
    return str(value).strip().upper().replace(".JK", "")


def _business_session_age(session_date: str, today: date | None = None) -> int:
    session = pd.Timestamp(session_date).date()
    current = today or datetime.now(timezone.utc).astimezone(JAKARTA).date()
    if session >= current:
        return 0
    return len(pd.bdate_range(session + pd.offsets.Day(1), current))


@dataclass(frozen=True)
class ScanResearchSnapshot:
    snapshot_id: str
    session_date: str
    created_at: str
    mode: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    universe: str = "LQ45"
    universe_size: int = 45
    universe_coverage_pct: float = 0.0
    quant_snapshot_id: str | None = None
    model_status: str = "SHADOW"
    source_summary: dict[str, Any] = field(default_factory=dict)
    formula_version: str = "quality-first-scan-v5"
    schema_version: str = SCAN_SCHEMA_VERSION
    signature: str | None = None
    signing_key_id: str | None = None
    checksum: str = ""
    verified_session_age: int | None = field(default=None, repr=False, compare=False)

    def unsigned_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("checksum", None)
        payload.pop("signature", None)
        payload.pop("signing_key_id", None)
        payload.pop("verified_session_age", None)
        return payload

    def calculated_checksum(self) -> str:
        return hashlib.sha256(_canonical(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "signature": self.signature, "signing_key_id": self.signing_key_id,
                "checksum": self.checksum or self.calculated_checksum()}

    def validate(self) -> None:
        if self.schema_version not in SUPPORTED_SCAN_SCHEMA_VERSIONS:
            raise ValueError(f"Unsupported scan snapshot schema {self.schema_version}.")
        if self.mode not in SCAN_MODES:
            raise ValueError(f"Unsupported scan mode {self.mode}.")
        datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        date.fromisoformat(self.session_date)
        if not self.snapshot_id or self.universe != "LQ45":
            raise ValueError("A scan snapshot ID and the LQ45 universe are required.")
        if self.mode == "PRIMARY" and not self.quant_snapshot_id:
            raise ValueError("PRIMARY scans require an approved quant snapshot.")
        if not self.checksum or self.checksum != self.calculated_checksum():
            raise ValueError("Scan snapshot checksum is missing or invalid.")
        from analysis.signing import verify_checksum
        if not verify_checksum(self.checksum, self.signature):
            raise ValueError("Scan snapshot Ed25519 signature is missing or invalid.")

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | str) -> "ScanResearchSnapshot":
        value = json.loads(payload) if isinstance(payload, str) else payload
        allowed = set(cls.__dataclass_fields__)
        snapshot = cls(**{key: item for key, item in value.items() if key in allowed})
        snapshot.validate()
        return snapshot

    def to_bundle(self, requested: list[str] | None = None, *, today: date | None = None) -> ScanBundle:
        normalized = []
        for value in requested or []:
            ticker = _ticker(value)
            if ticker and ticker not in normalized:
                normalized.append(ticker)
        membership = {
            _ticker(row.get("ticker", "")) for row in [*self.candidates, *self.excluded]
            if row.get("ticker")
        }
        candidates = list(self.candidates)
        excluded = list(self.excluded)
        if normalized:
            candidates = [row for row in candidates if _ticker(row.get("ticker", "")) in normalized]
            excluded = [row for row in excluded if _ticker(row.get("ticker", "")) in normalized]
            excluded.extend(
                {"ticker": ticker, "reason": "Outside the effective LQ45 snapshot universe."}
                for ticker in normalized if ticker not in membership
            )

        mode = self.mode
        warnings = list(self.warnings)
        session_age = (self.verified_session_age if self.verified_session_age is not None
                       else _business_session_age(self.session_date, today))
        if session_age > 2:
            mode = "UNAVAILABLE"
            candidates = []
            warnings.insert(0, "The latest scan is more than two completed business sessions old.")
        return ScanBundle(
            as_of=self.created_at,
            requested_tickers=normalized or sorted(membership),
            candidates=candidates,
            excluded=excluded,
            warnings=list(dict.fromkeys(warnings)),
            mode=mode,
            snapshot_id=self.snapshot_id,
            session_date=self.session_date,
            universe=self.universe,
            universe_coverage_pct=self.universe_coverage_pct,
            quant_snapshot_id=self.quant_snapshot_id,
            source_summary=self.source_summary,
        )


def signed_scan_snapshot(**values) -> ScanResearchSnapshot:
    base = ScanResearchSnapshot(**values)
    checksum = base.calculated_checksum()
    from analysis.signing import sign_checksum
    signature, key_id = sign_checksum(checksum)
    return ScanResearchSnapshot(**{**base.unsigned_dict(), "checksum": checksum,
                                   "signature": signature, "signing_key_id": key_id})


def unavailable_scan_snapshot(reason: str) -> ScanResearchSnapshot:
    now = datetime.now(timezone.utc)
    return signed_scan_snapshot(
        snapshot_id="unavailable-scan",
        session_date=now.astimezone(JAKARTA).date().isoformat(),
        created_at=now.isoformat(),
        mode="UNAVAILABLE",
        universe_size=45,
        warnings=[reason],
    )


class ScanSnapshotManager:
    """Lazy 15-minute Supabase cache with a last-good in-process fallback."""

    def __init__(self, ttl_seconds: int | None = None):
        configured = ttl_seconds or int(os.getenv("SCAN_SNAPSHOT_TTL_SECONDS", "300"))
        self.ttl_seconds = max(30, min(900, configured))
        self._snapshot: ScanResearchSnapshot | None = None
        self._loaded_at = 0.0
        self._lock = Lock()

    def get(self, *, refresh: bool = False) -> ScanResearchSnapshot:
        with self._lock:
            if self._snapshot and not refresh and monotonic() - self._loaded_at < self.ttl_seconds:
                return self._snapshot
            try:
                from storage.database import connect_from_env
                from storage.repository import SnapshotRepository
                remote = SnapshotRepository(connect_from_env).latest_scan_snapshot()
                if remote is not None:
                    self._snapshot = remote
                    self._loaded_at = monotonic()
                    return remote
                reason = "No full-LQ45 scan snapshot has been published."
            except Exception as exc:
                if self._snapshot is not None:
                    self._loaded_at = monotonic()
                    return self._snapshot
                reason = f"Scan snapshot unavailable ({type(exc).__name__})."
            self._snapshot = unavailable_scan_snapshot(reason)
            self._loaded_at = monotonic()
            return self._snapshot


_manager = ScanSnapshotManager()


def get_scan_snapshot(*, refresh: bool = False) -> ScanResearchSnapshot:
    return _manager.get(refresh=refresh)
