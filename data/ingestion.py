"""Immutable source-artifact acquisition for scheduled research jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4


@dataclass(frozen=True)
class AcquiredArtifact:
    id: str
    provider: str
    source_class: str
    artifact_type: str
    source_url: str
    checksum: str
    retrieved_at: str
    published_at: str | None
    object_key: str | None
    content_type: str | None
    size_bytes: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def acquire_artifact(
    *, provider: str, source_class: str, artifact_type: str, source_url: str,
    published_at: str | None = None, archive_directory: str | Path | None = None,
) -> tuple[AcquiredArtifact, bytes]:
    if source_class not in {"official", "licensed", "yahoo_fallback"}:
        raise ValueError("Unsupported source class.")
    request = Request(source_url, headers={"User-Agent": "PastiCuan research ingestion/3.0"})
    with urlopen(request, timeout=30) as response:
        body = response.read()
        content_type = response.headers.get_content_type()
    checksum = hashlib.sha256(body).hexdigest()
    extension = mimetypes.guess_extension(content_type or "") or ".bin"
    object_key = f"sources/{provider.lower().replace(' ', '-')}/{checksum}{extension}"
    if archive_directory:
        destination = Path(archive_directory) / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(body)
    artifact = AcquiredArtifact(
        id=str(uuid4()), provider=provider, source_class=source_class,
        artifact_type=artifact_type, source_url=source_url, checksum=checksum,
        retrieved_at=datetime.now(timezone.utc).isoformat(), published_at=published_at,
        object_key=object_key, content_type=content_type, size_bytes=len(body),
    )
    return artifact, body


def upload_to_r2(object_key: str, body: bytes, *, content_type: str | None = None) -> None:
    required = ("R2_ENDPOINT_URL", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
    if not all(os.getenv(name) for name in required):
        raise RuntimeError("R2 credentials are incomplete.")
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("Install requirements-jobs.txt for R2 archival.") from exc
    client = boto3.client(
        "s3", endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto",
    )
    extra = {"ContentType": content_type} if content_type else {}
    client.put_object(Bucket=os.environ["R2_BUCKET"], Key=object_key, Body=body, **extra)


def read_manifest(path: str | Path) -> list[dict]:
    payload = json.loads(Path(path).read_text())
    records = payload.get("sources", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("Source manifest must be a list or contain a sources list.")
    return records
