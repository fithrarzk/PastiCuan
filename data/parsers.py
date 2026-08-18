"""Strict parsers for reviewed canonical interchange files.

Official PDFs/XBRL whose layout is not explicitly supported remain quarantined;
the ingestion job never guesses columns or publication dates.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd


SCHEMAS = {
    "lq45_constituents_csv": {
        "ticker", "legal_name", "sector", "currency", "active_from",
        "effective_from", "effective_to", "source_url", "checksum",
    },
    "market_bars_csv": {
        "ticker", "session_date", "open", "high", "low", "close", "volume",
        "currency", "available_at", "source_url", "checksum",
    },
    "statement_facts_csv": {
        "ticker", "filing_type", "period_end", "available_at", "taxonomy",
        "concept", "normalized_concept", "value", "unit", "source_url",
        "document_checksum", "restatement_version", "consolidated", "audit_status",
        "object_key", "scale",
    },
    "shares_history_csv": {
        "ticker", "effective_from", "period_end_shares", "available_at",
        "source_url", "checksum",
    },
    "corporate_actions_csv": {
        "ticker", "action_type", "ex_date", "available_at", "source_url", "checksum",
    },
    "fx_rates_csv": {
        "rate_date", "base_currency", "quote_currency", "rate", "rate_type",
        "available_at", "source_url", "checksum",
    },
    "market_sessions_csv": {
        "exchange", "session_date", "status",
    },
    "issuer_profiles_csv": {
        "ticker", "legal_name", "sector", "issuer_type", "currency",
        "available_at", "source_url", "checksum",
    },
    "disclosure_events_csv": {
        "ticker", "event_type", "published_at", "available_at", "title",
        "source_url", "checksum",
    },
    "policy_rates_csv": {
        "observation_date", "rate_name", "annual_rate", "available_at",
        "source_url", "checksum",
    },
}


def parse_canonical_csv(artifact_type: str, body: bytes) -> list[dict]:
    required = SCHEMAS.get(artifact_type)
    if required is None:
        raise ValueError(f"No reviewed parser is registered for {artifact_type}.")
    frame = pd.read_csv(BytesIO(body))
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Canonical {artifact_type} is missing: {', '.join(sorted(missing))}.")
    if frame.empty:
        raise ValueError(f"Canonical {artifact_type} contains no records.")
    for column in [name for name in frame.columns if name.endswith("_at") or name.endswith("_date") or name.endswith("_from") or name.endswith("_to") or name == "period_end"]:
        if frame[column].isna().all() and column in {"active_to", "effective_to", "period_start", "published_at"}:
            continue
        converted = pd.to_datetime(frame[column], errors="coerce")
        if converted.isna().any() and not frame[column].isna().equals(converted.isna()):
            raise ValueError(f"Canonical {artifact_type} contains an invalid {column}.")
        frame[column] = converted.map(lambda value: value.isoformat() if pd.notna(value) else None)
    return frame.astype(object).where(pd.notna(frame), None).to_dict("records")
