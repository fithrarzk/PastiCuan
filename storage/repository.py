"""PostgreSQL repository using DB-API connections supplied by the deployment."""

from __future__ import annotations

import json
from typing import Any, Callable
from uuid import uuid4

from analysis.contracts import AnalysisBundle


class SnapshotRepository:
    def __init__(self, connect: Callable[[], Any]):
        self._connect = connect

    def save_bundle(self, issuer_id: int, bundle: AnalysisBundle) -> str:
        snapshot_id = str(uuid4())
        payload = bundle.to_dict()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO analysis_snapshots
                      (id, issuer_id, as_of, horizon, analysis_version, bundle,
                       data_quality_grade, action_label)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    """,
                    (snapshot_id, issuer_id, bundle.as_of, bundle.horizon,
                     bundle.analysis_version, json.dumps(payload),
                     bundle.data_quality.grade, bundle.action),
                )
        return snapshot_id

    def market_bars_as_of(self, issuer_id: int, as_of: str) -> list[dict]:
        """Latest non-quarantined version known by ``as_of`` for each session."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT ON (session_date)
                      session_date, open, high, low, close, volume, currency,
                      available_at, source_class, source_url, checksum
                    FROM market_bars
                    WHERE issuer_id = %s AND available_at <= %s
                      AND quarantined_at IS NULL
                    ORDER BY session_date, version DESC
                    """,
                    (issuer_id, as_of),
                )
                names = [column.name for column in cursor.description]
                return [dict(zip(names, row)) for row in cursor.fetchall()]

    def facts_as_of(self, issuer_id: int, as_of: str) -> list[dict]:
        """Only facts whose filing was actually available by simulation time."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT ON (sf.normalized_concept, sf.period_start, sf.period_end)
                      sf.normalized_concept, sf.period_start, sf.period_end, sf.value,
                      sf.currency, sf.scale, sf.unit, sf.available_at,
                      sf.restatement_version, sf.source_url, sf.document_checksum
                    FROM statement_facts sf
                    JOIN filings f ON f.id = sf.filing_id
                    WHERE f.issuer_id = %s AND sf.available_at <= %s
                      AND f.available_at <= %s AND f.quarantined_at IS NULL
                    ORDER BY sf.normalized_concept, sf.period_start, sf.period_end,
                             sf.restatement_version DESC
                    """,
                    (issuer_id, as_of, as_of),
                )
                names = [column.name for column in cursor.description]
                return [dict(zip(names, row)) for row in cursor.fetchall()]

    def constituents_as_of(self, index_code: str, on_date: str) -> list[int]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT issuer_id FROM index_constituents
                       WHERE index_code = %s AND effective_from <= %s AND effective_to >= %s
                       ORDER BY issuer_id""",
                    (index_code, on_date, on_date),
                )
                return [row[0] for row in cursor.fetchall()]

