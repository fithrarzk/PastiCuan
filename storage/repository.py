"""PostgreSQL repository using DB-API connections supplied by the deployment."""

from __future__ import annotations

import hashlib
import math
from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Callable
from uuid import uuid4

from analysis.contracts import AnalysisBundle, strict_json_dumps
from analysis.snapshots import ResearchSnapshot
from analysis.scan_snapshots import ScanResearchSnapshot


def _migration_preflight_error(exc: Exception, *, scope: str = "ledger") -> dict:
    """Translate DB-API SQLSTATE without exposing provider/connection text."""
    code = getattr(exc, "pgcode", None) or getattr(exc, "sqlstate", None)
    if code in {"42501", "42502"}:
        stable = f"LEDGER_{scope.upper()}_PRIVILEGE_DENIED"
    elif code in {"42P01", "3F000"}:
        stable = "LEDGER_ABSENT"
    elif code in {"57014", "55P03"}:
        stable = "LEDGER_TIMEOUT"
    else:
        stable = "LEDGER_DATABASE_ERROR"
    return {"ok": False, "code": stable, "missing_versions": []}


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
                     bundle.analysis_version, strict_json_dumps(payload),
                     bundle.data_quality.grade, bundle.action),
                )
        return snapshot_id

    def verify_issuer_profile(self, ticker: str, *, sector: str, source_url: str,
                              checksum: str, available_at: str) -> str:
        """Promote official XBRL issuer metadata without guessing missing sectors."""
        clean_sector = str(sector or "").strip()
        if not clean_sector or clean_sector.upper() in {"N/A", "UNKNOWN", "UNCLASSIFIED"}:
            raise ValueError("Official XBRL does not contain usable issuer-sector metadata.")
        lowered = clean_sector.lower()
        issuer_type = "bank" if any(token in lowered for token in ("bank", "banking")) else "general"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT issuer_type,profile_checksum FROM issuers WHERE ticker=%s FOR UPDATE""",
                    (ticker.upper().replace(".JK", ""),),
                )
                existing = cursor.fetchone()
                if not existing:
                    raise ValueError(f"Issuer {ticker} must exist before profile verification.")
                if existing[1] and existing[0] != issuer_type:
                    raise ValueError(f"Official issuer profile conflicts with the reviewed {existing[0]} profile.")
                cursor.execute(
                    """UPDATE issuers SET sector=%s,issuer_type=%s,profile_verified_at=%s,
                              profile_source_url=%s,profile_checksum=%s WHERE ticker=%s""",
                    (clean_sector, issuer_type, available_at, source_url, checksum,
                     ticker.upper().replace(".JK", "")),
                )
        return issuer_type

    def applied_schema_migrations(self) -> list[str]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
                return [
                    row[0].decode("utf-8") if isinstance(row[0], bytes) else row[0]
                    for row in cursor.fetchall()
                ]

    def preflight_schema_migrations(self, required_versions: list[str] | tuple[str, ...]) -> dict:
        """Read the migration ledger and return a redacted stable result."""
        required = sorted({str(version) for version in required_versions})
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    try:
                        cursor.execute("SELECT has_schema_privilege(current_user, 'public', 'USAGE')")
                        schema_privilege = cursor.fetchone()
                    except Exception as exc:
                        return _migration_preflight_error(exc, scope="schema")
                    if not schema_privilege or not bool(schema_privilege[0]):
                        return {"ok": False, "code": "LEDGER_SCHEMA_PRIVILEGE_DENIED", "missing_versions": required}
                    try:
                        cursor.execute("SELECT to_regclass('public.schema_migrations')")
                        row = cursor.fetchone()
                    except Exception as exc:
                        return _migration_preflight_error(exc, scope="ledger")
                    if not row or row[0] is None:
                        return {"ok": False, "code": "LEDGER_ABSENT", "missing_versions": required}
                    try:
                        cursor.execute("SELECT has_table_privilege(current_user, 'public.schema_migrations', 'SELECT')")
                        privilege = cursor.fetchone()
                    except Exception as exc:
                        return _migration_preflight_error(exc, scope="table")
                    if not privilege or not bool(privilege[0]):
                        return {"ok": False, "code": "LEDGER_TABLE_PRIVILEGE_DENIED", "missing_versions": required}
                    try:
                        cursor.execute("SELECT version FROM public.schema_migrations ORDER BY version")
                        rows = cursor.fetchall()
                    except Exception as exc:
                        return _migration_preflight_error(exc)
        except Exception as exc:
            return _migration_preflight_error(exc)
        applied = {
            row[0].decode("utf-8") if isinstance(row[0], bytes) else str(row[0])
            for row in rows
        }
        missing = [version for version in required if version not in applied]
        if missing:
            return {"ok": False, "code": "REQUIRED_MIGRATION_MISSING", "missing_versions": missing}
        return {"ok": True, "code": "LEDGER_READY", "missing_versions": []}

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

    def ticker_market_history(self, ticker: str, as_of: str, *, sessions: int = 756):
        """Return verified stored OHLCV for bot charts; this never calls a provider."""
        import pandas as pd
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id,sector FROM issuers WHERE ticker=%s", (ticker.upper().replace(".JK", ""),))
                issuer = cursor.fetchone()
        if not issuer:
            return pd.DataFrame(), None
        rows = self.market_bars_as_of(issuer[0], as_of)[-max(1, min(int(sessions), 1000)):]
        if not rows:
            return pd.DataFrame(), issuer[1]
        frame = pd.DataFrame(rows).rename(columns={
            "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
        })
        frame.index = pd.to_datetime(frame.pop("session_date"))
        return frame[["Open", "High", "Low", "Close", "Volume"]].sort_index(), issuer[1]

    def valuation_bands_for_ticker(self, ticker: str, history, as_of: str) -> dict:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM issuers WHERE ticker=%s", (ticker.upper().replace(".JK", ""),))
                row = cursor.fetchone()
                if not row:
                    return {"status": "INSUFFICIENT_POINT_IN_TIME_DATA", "pe": None, "pbv": None}
                issuer_id = row[0]
                cursor.execute(
                    """SELECT effective_from AS period_end,period_end_shares,weighted_average_shares,
                              available_at,checksum FROM shares_history
                       WHERE issuer_id=%s AND available_at<=%s ORDER BY effective_from,available_at""",
                    (issuer_id, as_of),
                )
                names = [column.name for column in cursor.description]
                shares = [dict(zip(names, value)) for value in cursor.fetchall()]
        from analysis.valuation_bands import compute_valuation_bands_from_facts
        return compute_valuation_bands_from_facts(history, self.facts_as_of(issuer_id, as_of), shares)

    def completed_session_age(self, session_date: str, on_date: str) -> int | None:
        """Count known completed IDX sessions after ``session_date``."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT count(*) FROM market_sessions
                       WHERE exchange='IDX' AND status='COMPLETED'
                         AND session_date>%s AND session_date<=%s""",
                    (session_date, on_date),
                )
                count = int(cursor.fetchone()[0])
                cursor.execute(
                    """SELECT 1 FROM market_sessions
                       WHERE exchange='IDX' AND status='COMPLETED' LIMIT 1"""
                )
                return count if cursor.fetchone() else None

    def expected_session_age(self, session_date: str, on_date: str) -> int | None:
        """Count official trading sessions after a date, excluding holidays."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT 1 FROM market_sessions
                       WHERE exchange='IDX' AND status IN ('SCHEDULED','HOLIDAY','HALTED')
                       LIMIT 1"""
                )
                if cursor.fetchone() is None:
                    return None
                cursor.execute(
                    """SELECT count(*) FROM market_sessions
                       WHERE exchange='IDX' AND status IN ('SCHEDULED','COMPLETED')
                         AND session_date>%s AND session_date<=%s""",
                    (session_date, on_date),
                )
                return int(cursor.fetchone()[0])

    def import_yahoo_market_histories(self, histories: dict[str, Any], *, available_at: str) -> int:
        """Store fetched OHLCV with retrieval-time availability; never backdate knowledge."""
        rows = []
        for ticker, history in histories.items():
            if history is None or history.empty:
                continue
            clean = history.dropna(subset=["Open", "High", "Low", "Close"])
            for index, values in clean.iterrows():
                raw_volume = values.get("Volume", 0)
                volume = float(raw_volume) if raw_volume is not None else 0.0
                if not math.isfinite(volume):
                    volume = 0.0
                payload = {
                    "ticker": ticker, "session_date": str(index.date()),
                    "open": float(values["Open"]), "high": float(values["High"]),
                    "low": float(values["Low"]), "close": float(values["Close"]),
                    "volume": volume,
                }
                checksum = hashlib.sha256(
                    strict_json_dumps(payload, separators=(",", ":")).encode()
                ).hexdigest()
                rows.append((
                    payload["ticker"], payload["session_date"], payload["open"],
                    payload["high"], payload["low"], payload["close"],
                    payload["volume"], available_at, checksum,
                ))
        if not rows:
            return 0
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT ticker,id FROM issuers WHERE ticker=ANY(%s)", (list(histories),))
                issuer_ids = {str(ticker): issuer_id for ticker, issuer_id in cursor.fetchall()}
                cursor.execute(
                    """SELECT DISTINCT ON (issuer_id,session_date)
                         issuer_id,session_date,version,checksum
                       FROM market_bars WHERE issuer_id=ANY(%s)
                       ORDER BY issuer_id,session_date,version DESC""",
                    (list(issuer_ids.values()),),
                )
                latest = {
                    (issuer_id, str(session_date)): (int(version), checksum)
                    for issuer_id, session_date, version, checksum in cursor.fetchall()
                }
                values = []
                for ticker, session_date, open_, high, low, close, volume, available_at, checksum in rows:
                    if ticker not in issuer_ids:
                        continue
                    issuer_id = issuer_ids[ticker]
                    version, previous_checksum = latest.get((issuer_id, session_date), (0, None))
                    if checksum == previous_checksum:
                        continue
                    values.append(
                        (issuer_id, session_date, version + 1, open_, high, low, close,
                         volume, available_at, checksum)
                    )
                cursor.executemany(
                    """INSERT INTO market_bars
                         (issuer_id,session_date,version,open,high,low,close,volume,currency,
                          available_at,source_class,source_url,checksum)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'IDR',%s,'yahoo_fallback',
                               'https://finance.yahoo.com',%s)
                       ON CONFLICT (issuer_id,session_date,version) DO NOTHING""",
                    values,
                )
                return len(values)

    def record_completed_market_session(self, session_date: str, *, observed_at: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO market_sessions(exchange,session_date,closes_at,status)
                       VALUES ('IDX',%s,%s,'COMPLETED')
                       ON CONFLICT (exchange,session_date) DO UPDATE SET
                         closes_at=EXCLUDED.closes_at,status='COMPLETED'""",
                    (session_date, f"{session_date}T16:00:00+07:00"),
                )

    def facts_as_of(self, issuer_id: int, as_of: str) -> list[dict]:
        """Only facts whose filing was actually available by simulation time."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT ON (sf.normalized_concept, sf.period_start, sf.period_end)
                      sf.normalized_concept, sf.period_start, sf.period_end, sf.value,
                      sf.currency, sf.scale, sf.unit, sf.available_at,
                      sf.period_type, sf.duration_class, sf.fiscal_year, sf.fiscal_quarter,
                      sf.restatement_version, sf.source_url, sf.document_checksum
                    FROM statement_facts sf
                    JOIN filings f ON f.id = sf.filing_id
                    WHERE f.issuer_id = %s AND sf.available_at <= %s
                      AND f.available_at <= %s AND f.quarantined_at IS NULL
                    ORDER BY sf.normalized_concept, sf.period_start, sf.period_end,
                             sf.restatement_version DESC, sf.available_at DESC, sf.id DESC
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

    def constituent_issuers_as_of(self, index_code: str, on_date: str) -> list[dict]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT i.id, i.ticker, i.legal_name, i.sector, i.issuer_type, i.currency,
                              i.profile_verified_at,i.profile_source_url,i.profile_checksum
                       FROM index_constituents c JOIN issuers i ON i.id=c.issuer_id
                       WHERE c.index_code=%s AND c.effective_from<=%s AND c.effective_to>=%s
                       ORDER BY i.ticker""", (index_code, on_date, on_date),
                )
                names = [column.name for column in cursor.description]
                return [dict(zip(names, row)) for row in cursor.fetchall()]

    def latest_scan_snapshot(self) -> ScanResearchSnapshot | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT payload FROM scan_research_snapshots
                       ORDER BY session_date DESC, published_at DESC LIMIT 1"""
                )
                row = cursor.fetchone()
        if not row:
            return None
        snapshot = ScanResearchSnapshot.from_dict(row[0])
        today = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Jakarta")).date().isoformat()
        age = self.expected_session_age(snapshot.session_date, today)
        return replace(snapshot, verified_session_age=age)

    def ticker_snapshot_history(self, ticker: str, *, limit: int = 8) -> list[dict]:
        ticker = ticker.upper().replace(".JK", "")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT session_date,payload->'candidates',payload->'excluded',formula_version,checksum
                       FROM scan_research_snapshots
                       ORDER BY session_date DESC,published_at DESC LIMIT %s""",
                    (int(max(1, min(limit * 4, 80))),),
                )
                result = []
                for session_date, candidates, excluded, formula_version, checksum in cursor.fetchall():
                    candidate = next((item for item in candidates or [] if item.get("ticker") == ticker), None)
                    exclusion = next((item for item in excluded or [] if item.get("ticker") == ticker), None)
                    if candidate or exclusion:
                        result.append({"session_date": str(session_date), "formula_version": formula_version,
                                       "checksum": checksum, "candidate": candidate,
                                       "reason": (exclusion or {}).get("reason")})
                    if len(result) >= limit:
                        break
                return result

    def disclosure_events_for_ticker(self, ticker: str, *, limit: int = 10) -> list[dict]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT de.event_type,de.published_at,de.title,de.source_url,de.metadata
                       FROM disclosure_events de JOIN issuers i ON i.id=de.issuer_id
                       WHERE i.ticker=%s ORDER BY de.published_at DESC LIMIT %s""",
                    (ticker.upper().replace(".JK", ""), int(max(1, min(limit, 20)))),
                )
                names = [column.name for column in cursor.description]
                return [dict(zip(names, row)) for row in cursor.fetchall()]

    def operational_status(self) -> dict:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT max(session_date) FROM market_sessions WHERE exchange='IDX' AND status='COMPLETED'")
                session = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM ingestion_issues WHERE status='OPEN'")
                issues = int(cursor.fetchone()[0])
                cursor.execute("SELECT max(started_at) FROM research_job_runs WHERE status='SUCCEEDED'")
                job = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM provider_runs WHERE status='FAILED' AND started_at>now()-interval '24 hours'")
                failures = int(cursor.fetchone()[0])
                cursor.execute("SELECT pg_database_size(current_database())")
                database_size = int(cursor.fetchone()[0])
                return {"latest_session": str(session) if session else None, "open_issues": issues,
                        "last_successful_job": job.isoformat() if job else None,
                        "provider_failures_24h": failures,
                        "database_size_bytes": database_size,
                        "database_size_state": "CRITICAL" if database_size >= 425 * 1024 * 1024
                        else ("WARNING" if database_size >= 350 * 1024 * 1024 else "OK")}

    def record_provider_run(self, run: dict) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO provider_runs
                         (id,provider,capability,source_class,started_at,completed_at,status,attempts,
                          latency_ms,coverage_pct,fallback_from,error_type,metadata)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                    (run["id"], run["provider"], run["capability"], run["source_class"],
                     run["started_at"], run.get("completed_at"), run["status"], run.get("attempts", 1),
                     run.get("latency_ms"), run.get("coverage_pct"), run.get("fallback_from"),
                     run.get("error_type"), strict_json_dumps(run.get("metadata") or {})),
                )

    def record_research_job(self, run: dict) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO research_job_runs
                         (id,job_type,workflow_run_id,started_at,completed_at,status,
                          input_checksum,output_checksum,metrics,error_type)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                       ON CONFLICT (id) DO UPDATE SET completed_at=EXCLUDED.completed_at,
                         status=EXCLUDED.status,output_checksum=EXCLUDED.output_checksum,
                         metrics=EXCLUDED.metrics,error_type=EXCLUDED.error_type""",
                    (run["id"], run["job_type"], run.get("workflow_run_id"), run["started_at"],
                     run.get("completed_at"), run["status"], run.get("input_checksum"),
                     run.get("output_checksum"), strict_json_dumps(run.get("metrics") or {}),
                     run.get("error_type")),
                )

    def reserve_alert(self, *, ticker: str, signal_date: str, horizon: str,
                      model_version: str, channel: str = "telegram") -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO alert_deliveries
                         (ticker,signal_date,horizon,model_version,channel,status)
                       VALUES (%s,%s,%s,%s,%s,'RESERVED')
                       ON CONFLICT DO NOTHING RETURNING ticker""",
                    (ticker.upper().replace(".JK", ""), signal_date, horizon, model_version, channel),
                )
                return cursor.fetchone() is not None

    def complete_alert(self, *, ticker: str, signal_date: str, horizon: str,
                       model_version: str, status: str, error: str | None = None,
                       channel: str = "telegram") -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE alert_deliveries SET status=%s,sent_at=CASE WHEN %s='SENT' THEN now() END,error=%s
                       WHERE ticker=%s AND signal_date=%s AND horizon=%s AND model_version=%s AND channel=%s""",
                    (status, status, error, ticker.upper().replace(".JK", ""), signal_date,
                     horizon, model_version, channel),
                )

    def completed_month_ends(self, start: str, end: str) -> list[str]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT max(session_date) FROM market_sessions
                       WHERE exchange='IDX' AND status='COMPLETED' AND session_date BETWEEN %s AND %s
                       GROUP BY date_trunc('month',session_date) ORDER BY max(session_date)""",
                    (start, end),
                )
                return [str(row[0]) for row in cursor.fetchall()]

    def validation_bars(self, start: str, end: str) -> list[dict]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT DISTINCT ON (i.ticker,mb.session_date)
                              mb.session_date AS date,i.ticker,mb.open,mb.high,mb.low,mb.close,mb.volume
                       FROM market_bars mb JOIN issuers i ON i.id=mb.issuer_id
                       WHERE mb.session_date BETWEEN %s AND %s AND mb.quarantined_at IS NULL
                       ORDER BY i.ticker,mb.session_date,mb.version DESC""",
                    (start, end),
                )
                names = [column.name for column in cursor.description]
                return [dict(zip(names, row)) for row in cursor.fetchall()]

    def portfolio_price_history(self, tickers: list[str], as_of: str, *, sessions: int = 756):
        import pandas as pd
        from analysis.factor_dataset import _adjusted_close
        series = {}
        for ticker in dict.fromkeys(value.upper().replace(".JK", "") for value in tickers):
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id FROM issuers WHERE ticker=%s", (ticker,))
                    found = cursor.fetchone()
            if not found:
                continue
            issuer_id = found[0]
            bars = self.market_bars_as_of(issuer_id, as_of)[-sessions:]
            actions = self.corporate_actions_as_of(issuer_id, as_of)
            adjusted = _adjusted_close(bars, actions)
            if not adjusted.empty:
                series[f"{ticker}.JK"] = adjusted
        return pd.DataFrame(series).sort_index()

    def publish_scan_snapshot(self, snapshot: ScanResearchSnapshot) -> str:
        snapshot.validate()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO scan_research_snapshots
                         (id,session_date,universe,mode,model_status,quant_snapshot_id,
                          universe_coverage_pct,schema_version,formula_version,checksum,
                          payload,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                       ON CONFLICT (checksum) DO NOTHING RETURNING id""",
                    (snapshot.snapshot_id, snapshot.session_date, snapshot.universe,
                     snapshot.mode, snapshot.model_status, snapshot.quant_snapshot_id,
                     snapshot.universe_coverage_pct, snapshot.schema_version,
                     snapshot.formula_version, snapshot.checksum,
                     strict_json_dumps(snapshot.to_dict()), snapshot.created_at),
                )
                row = cursor.fetchone()
                if row:
                    published_id = str(row[0])
                else:
                    cursor.execute("SELECT id FROM scan_research_snapshots WHERE checksum=%s", (snapshot.checksum,))
                    published_id = str(cursor.fetchone()[0])
                for candidate in snapshot.candidates:
                    ticker = str(candidate.get("ticker") or "").upper().replace(".JK", "")
                    cursor.execute("SELECT id FROM issuers WHERE ticker=%s", (ticker,))
                    issuer = cursor.fetchone()
                    if not issuer:
                        continue
                    evidence = {
                        "formula_version": snapshot.formula_version,
                        "ranking_score": candidate.get("ranking_score"),
                        "technical_score": candidate.get("technical_score"),
                        "risk_reward": candidate.get("risk_reward"),
                        "coverage_pct": candidate.get("coverage_pct"),
                    }
                    cursor.execute(
                        """INSERT INTO scan_signals
                             (snapshot_id,issuer_id,signal_session,business_state,entry_state,
                              business_score,entry_reference,stop_loss,target,evidence)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                           ON CONFLICT (snapshot_id,issuer_id) DO NOTHING""",
                        (published_id, issuer[0], snapshot.session_date,
                         candidate.get("business_state") or "LIMITED_HISTORY",
                         candidate.get("entry_state") or "NO_RELIABLE_SETUP",
                         candidate.get("business_score"), candidate.get("entry_reference"),
                         candidate.get("stop_loss"), candidate.get("target"),
                         strict_json_dumps(evidence)),
                    )
                return published_id

    def pending_signal_windows(self, *, horizons: tuple[int, ...] = (5, 20, 60, 252)) -> list[dict]:
        """Return immutable signals and subsequent prices for missing outcomes."""
        rows = []
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT ss.snapshot_id,ss.issuer_id,ss.signal_session,i.ticker,
                              ss.business_state,ss.entry_state,ss.business_score
                       FROM scan_signals ss JOIN issuers i ON i.id=ss.issuer_id
                       ORDER BY ss.signal_session,ss.issuer_id"""
                )
                names = [column.name for column in cursor.description]
                signals = [dict(zip(names, row)) for row in cursor.fetchall()]
                for signal in signals:
                    cursor.execute(
                        """SELECT DISTINCT ON (session_date) session_date,close
                           FROM market_bars WHERE issuer_id=%s AND session_date>%s
                             AND quarantined_at IS NULL
                           ORDER BY session_date,version DESC""",
                        (signal["issuer_id"], signal["signal_session"]),
                    )
                    raw_prices = [{"session_date": row[0], "close": row[1]} for row in cursor.fetchall()]
                    cursor.execute(
                        """SELECT action_type,ex_date,ratio FROM corporate_actions
                           WHERE issuer_id=%s AND ex_date>%s AND available_at<=now()
                             AND quarantined_at IS NULL AND validation_status='ACCEPTED'
                           ORDER BY ex_date,version""",
                        (signal["issuer_id"], signal["signal_session"]),
                    )
                    actions = [{"action_type": row[0], "ex_date": row[1], "ratio": row[2]}
                               for row in cursor.fetchall()]
                    from analysis.factor_dataset import _adjusted_close
                    adjusted = _adjusted_close(raw_prices, actions)
                    prices = [{"session_date": index.date(), "close": value}
                              for index, value in adjusted.items()]
                    cursor.execute(
                        """SELECT horizon_sessions FROM signal_outcomes
                           WHERE snapshot_id=%s AND issuer_id=%s""",
                        (signal["snapshot_id"], signal["issuer_id"]),
                    )
                    completed = {int(row[0]) for row in cursor.fetchall()}
                    rows.append({**signal, "prices": prices,
                                 "horizons": [value for value in horizons if value not in completed]})
        return rows

    def save_signal_outcome(self, outcome: dict) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO signal_outcomes
                         (snapshot_id,issuer_id,horizon_sessions,evaluated_session,absolute_return,
                          benchmark_return,excess_return,maximum_favorable_excursion,
                          maximum_adverse_excursion,status,adjustment_version,evidence)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                       ON CONFLICT (snapshot_id,issuer_id,horizon_sessions) DO NOTHING""",
                    (outcome["snapshot_id"], outcome["issuer_id"], outcome["horizon_sessions"],
                     outcome["evaluated_session"], outcome.get("absolute_return"),
                     outcome.get("benchmark_return"), outcome.get("excess_return"),
                     outcome.get("maximum_favorable_excursion"),
                     outcome.get("maximum_adverse_excursion"), outcome["status"],
                     outcome["adjustment_version"], strict_json_dumps(outcome.get("evidence") or {})),
                )

    def shares_as_of(self, issuer_id: int, as_of: str) -> dict | None:
        on_date = str(as_of).split("T", 1)[0].split(" ", 1)[0]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT effective_from,period_end_shares,weighted_average_shares,
                              available_at,checksum
                       FROM shares_history WHERE issuer_id=%s AND effective_from<=%s
                         AND (effective_to IS NULL OR effective_to>=%s)
                         AND available_at<=%s
                       ORDER BY effective_from DESC, available_at DESC LIMIT 1""",
                    (issuer_id, on_date, on_date, as_of),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                names = [column.name for column in cursor.description]
                return dict(zip(names, row))

    def corporate_actions_as_of(self, issuer_id: int, as_of: str) -> list[dict]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT action_type,ex_date,ratio,cash_amount,currency,available_at,
                              subscription_price,source_class,validation_status
                       FROM corporate_actions WHERE issuer_id=%s AND available_at<=%s
                         AND quarantined_at IS NULL
                       ORDER BY ex_date,version""", (issuer_id, as_of),
                )
                names = [column.name for column in cursor.description]
                return [dict(zip(names, row)) for row in cursor.fetchall()]

    def latest_approved_quant_snapshot(self) -> ResearchSnapshot | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT payload FROM quant_research_snapshots
                       WHERE status IN ('SHADOW','VALIDATED_RESEARCH')
                       ORDER BY effective_at DESC, approved_at DESC LIMIT 1"""
                )
                row = cursor.fetchone()
                return ResearchSnapshot.from_dict(row[0]) if row else None

    def model_evidence(self, model_version_id: str) -> dict:
        """Return validation authority only when a persisted run passed."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT mv.id, mv.status, vr.id, vr.metrics
                       FROM model_versions mv
                       LEFT JOIN LATERAL (
                         SELECT id, metrics FROM validation_runs
                         WHERE model_version_id = mv.id AND status = 'PASSED'
                         ORDER BY completed_at DESC LIMIT 1
                       ) vr ON true
                       WHERE mv.id = %s""",
                    (model_version_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return {"model_version": model_version_id, "model_status": "SHADOW"}
                return {
                    "model_version": row[0], "model_status": row[1],
                    "validation_run_id": str(row[2]) if row[2] else None,
                    "validation_metrics": row[3] or {},
                }

    def register_source_artifact(self, artifact: dict, *, parse_status: str = "PENDING") -> str:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO source_artifacts
                         (id, provider, source_class, artifact_type, source_url, object_key,
                          checksum, published_at, retrieved_at, parse_status, metadata)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                       ON CONFLICT (checksum) DO UPDATE SET retrieved_at = EXCLUDED.retrieved_at
                       RETURNING id""",
                    (artifact["id"], artifact["provider"], artifact["source_class"],
                     artifact["artifact_type"], artifact["source_url"], artifact.get("object_key"),
                     artifact["checksum"], artifact.get("published_at"), artifact["retrieved_at"],
                     parse_status, strict_json_dumps({"content_type": artifact.get("content_type"),
                                               "size_bytes": artifact.get("size_bytes")})),
                )
                return str(cursor.fetchone()[0])

    def record_ingestion_issue(self, artifact_id: str | None, code: str, detail: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO ingestion_issues(artifact_id, issue_code, severity, detail)
                       VALUES (%s,%s,'ERROR',%s)""", (artifact_id, code, detail),
                )

    def set_artifact_status(self, artifact_id: str, status: str) -> None:
        if status not in {"PENDING", "ACCEPTED", "QUARANTINED"}:
            raise ValueError("Invalid artifact status.")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE source_artifacts SET parse_status=%s WHERE id=%s", (status, artifact_id))

    def import_canonical_records(self, artifact_type: str, records: list[dict], *, source_class: str) -> int:
        """Import a reviewed canonical interchange file in one transaction."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                imported = 0
                for row in records:
                    if artifact_type == "fx_rates_csv":
                        cursor.execute(
                            """INSERT INTO fx_rates(rate_date,base_currency,quote_currency,rate,rate_type,
                                      available_at,source_url,checksum)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (rate_date,base_currency,quote_currency,rate_type)
                               DO UPDATE SET rate=EXCLUDED.rate,available_at=EXCLUDED.available_at,
                                             source_url=EXCLUDED.source_url,checksum=EXCLUDED.checksum""",
                            (row["rate_date"], row["base_currency"], row["quote_currency"], row["rate"],
                             row["rate_type"], row["available_at"], row["source_url"], row["checksum"]),
                        )
                        imported += 1
                        continue
                    if artifact_type == "market_sessions_csv":
                        cursor.execute(
                            """INSERT INTO market_sessions(exchange,session_date,opens_at,closes_at,status)
                               VALUES (%s,%s,%s,%s,%s)
                               ON CONFLICT (exchange,session_date) DO UPDATE SET
                                 opens_at=EXCLUDED.opens_at,closes_at=EXCLUDED.closes_at,status=EXCLUDED.status""",
                            (row.get("exchange") or "IDX", row["session_date"], row.get("opens_at"),
                             row.get("closes_at"), row["status"]),
                        )
                        imported += 1
                        continue
                    if artifact_type == "policy_rates_csv":
                        cursor.execute(
                            """INSERT INTO policy_rates(observation_date,rate_name,annual_rate,
                                      available_at,source_url,checksum)
                               VALUES (%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (observation_date,rate_name) DO UPDATE SET
                                 annual_rate=EXCLUDED.annual_rate,available_at=EXCLUDED.available_at,
                                 source_url=EXCLUDED.source_url,checksum=EXCLUDED.checksum""",
                            (row["observation_date"], row["rate_name"], row["annual_rate"],
                             row["available_at"], row["source_url"], row["checksum"]),
                        )
                        imported += 1
                        continue
                    ticker = str(row["ticker"]).upper().replace(".JK", "")
                    if artifact_type == "issuer_profiles_csv":
                        issuer_type = str(row["issuer_type"]).lower()
                        if issuer_type not in {"general", "bank"}:
                            raise ValueError(f"Unsupported issuer profile {issuer_type} for {ticker}.")
                        cursor.execute(
                            """UPDATE issuers SET legal_name=%s,sector=%s,issuer_type=%s,currency=%s,
                                      profile_verified_at=%s,profile_source_url=%s,profile_checksum=%s
                               WHERE ticker=%s""",
                            (row["legal_name"], row["sector"], issuer_type, row["currency"],
                             row["available_at"], row["source_url"], row["checksum"], ticker),
                        )
                        if cursor.rowcount != 1:
                            raise ValueError(f"Issuer {ticker} must exist before its profile is imported.")
                    elif artifact_type == "lq45_constituents_csv":
                        cursor.execute(
                            """INSERT INTO issuers(ticker,legal_name,sector,currency,active_from,active_to)
                               VALUES (%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (ticker) DO UPDATE SET legal_name=EXCLUDED.legal_name,
                                 sector=EXCLUDED.sector, active_to=EXCLUDED.active_to RETURNING id""",
                            (ticker, row["legal_name"], row["sector"], row["currency"],
                             row["active_from"], row.get("active_to")),
                        )
                        issuer_id = cursor.fetchone()[0]
                        cursor.execute(
                            """INSERT INTO index_constituents
                                 (index_code,issuer_id,effective_from,effective_to,source_url,checksum)
                               VALUES ('LQ45',%s,%s,%s,%s,%s)
                               ON CONFLICT (index_code,issuer_id,effective_from) DO UPDATE SET
                                 effective_to=EXCLUDED.effective_to, source_url=EXCLUDED.source_url,
                                 checksum=EXCLUDED.checksum""",
                            (issuer_id, row["effective_from"], row["effective_to"], row["source_url"], row["checksum"]),
                        )
                    else:
                        cursor.execute("SELECT id FROM issuers WHERE ticker=%s", (ticker,))
                        found = cursor.fetchone()
                        if not found:
                            raise ValueError(f"Issuer {ticker} must be imported before {artifact_type}.")
                        issuer_id = found[0]
                        if artifact_type == "market_bars_csv":
                            cursor.execute(
                                """INSERT INTO market_bars
                                     (issuer_id,session_date,version,open,high,low,close,volume,currency,
                                      available_at,source_class,source_url,checksum)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                   ON CONFLICT (issuer_id,session_date,version) DO NOTHING""",
                                (issuer_id, row["session_date"], int(row.get("version") or 1), row["open"],
                                 row["high"], row["low"], row["close"], row["volume"], row["currency"],
                                 row["available_at"], source_class, row["source_url"], row["checksum"]),
                            )
                        elif artifact_type == "shares_history_csv":
                            cursor.execute(
                                """INSERT INTO shares_history
                                     (issuer_id,effective_from,effective_to,period_end_shares,
                                      weighted_average_shares,available_at,source_url,checksum)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                                   ON CONFLICT (issuer_id,effective_from) DO UPDATE SET
                                     period_end_shares=EXCLUDED.period_end_shares,
                                     weighted_average_shares=EXCLUDED.weighted_average_shares,
                                     available_at=EXCLUDED.available_at, checksum=EXCLUDED.checksum""",
                                (issuer_id, row["effective_from"], row.get("effective_to"),
                                 row["period_end_shares"], row.get("weighted_average_shares"),
                                 row["available_at"], row["source_url"], row["checksum"]),
                            )
                        elif artifact_type == "statement_facts_csv":
                            consolidated = str(row["consolidated"]).lower() in {"true", "1", "yes"}
                            cursor.execute(
                                """INSERT INTO filings
                                     (issuer_id,filing_type,period_end,published_at,available_at,consolidated,
                                      audit_status,restatement_version,source_url,object_key,document_checksum)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                   ON CONFLICT (issuer_id,filing_type,period_end,restatement_version)
                                   DO UPDATE SET available_at=EXCLUDED.available_at,
                                     source_url=EXCLUDED.source_url, object_key=EXCLUDED.object_key
                                   RETURNING id""",
                                (issuer_id, row["filing_type"], row["period_end"], row.get("published_at"),
                                 row["available_at"], consolidated, row["audit_status"],
                                 int(row["restatement_version"]), row["source_url"], row["object_key"],
                                 row["document_checksum"]),
                            )
                            filing_id = cursor.fetchone()[0]
                            cursor.execute(
                                """INSERT INTO statement_facts
                                     (filing_id,taxonomy,concept,normalized_concept,period_start,period_end,
                                      published_at,available_at,value,currency,scale,unit,consolidated,
                                      audit_status,source_url,document_checksum,restatement_version,
                                      period_type,duration_class,fiscal_year,fiscal_quarter)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                   ON CONFLICT (filing_id,concept,period_start,period_end,unit) DO UPDATE SET
                                     period_type=COALESCE(statement_facts.period_type,EXCLUDED.period_type),
                                     duration_class=COALESCE(statement_facts.duration_class,EXCLUDED.duration_class),
                                     fiscal_year=COALESCE(statement_facts.fiscal_year,EXCLUDED.fiscal_year),
                                     fiscal_quarter=COALESCE(statement_facts.fiscal_quarter,EXCLUDED.fiscal_quarter)""",
                                (filing_id, row["taxonomy"], row["concept"], row["normalized_concept"],
                                 row.get("period_start"), row["period_end"], row.get("published_at"),
                                 row["available_at"], row["value"], row.get("currency"), int(row["scale"]),
                                 row["unit"], consolidated, row["audit_status"], row["source_url"],
                                 row["document_checksum"], int(row["restatement_version"]),
                                 row.get("period_type"), row.get("duration_class"),
                                 row.get("fiscal_year"), row.get("fiscal_quarter")),
                            )
                        elif artifact_type == "corporate_actions_csv":
                            action = str(row["action_type"]).upper()
                            validation = "QUARANTINED" if (
                                action == "RIGHTS" and (not row.get("ratio") or not row.get("subscription_price"))
                            ) else "ACCEPTED"
                            cursor.execute(
                                """INSERT INTO corporate_actions
                                     (issuer_id,action_type,ex_date,payable_date,ratio,cash_amount,currency,
                                      published_at,available_at,source_class,subscription_price,
                                      validation_status,source_url,checksum,quarantined_at,quarantine_reason)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                      CASE WHEN %s='QUARANTINED' THEN now() END,
                                      CASE WHEN %s='QUARANTINED' THEN 'Rights terms are incomplete.' END)
                                   ON CONFLICT (issuer_id,action_type,ex_date,version) DO NOTHING""",
                                (issuer_id, action, row["ex_date"], row.get("payable_date"), row.get("ratio"),
                                 row.get("cash_amount"), row.get("currency"), row.get("published_at"),
                                 row["available_at"], source_class, row.get("subscription_price"), validation,
                                 row["source_url"], row["checksum"], validation, validation),
                            )
                        elif artifact_type == "disclosure_events_csv":
                            cursor.execute(
                                """INSERT INTO disclosure_events
                                     (id,issuer_id,event_type,published_at,available_at,title,
                                      source_url,object_key,checksum,metadata)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                                   ON CONFLICT (checksum) DO NOTHING""",
                                (str(uuid4()), issuer_id, row["event_type"], row["published_at"],
                                 row["available_at"], row["title"], row["source_url"],
                                 row.get("object_key"), row["checksum"],
                                 strict_json_dumps(row.get("metadata") or {})),
                            )
                        else:
                            raise ValueError(f"Unsupported canonical artifact type {artifact_type}.")
                    imported += 1
                return imported

    def fx_rate_as_of(self, base: str, quote: str, rate_date: str, as_of: str,
                      *, rate_type: str = "SPOT") -> dict | None:
        if base == quote:
            return {"rate": 1.0, "rate_date": rate_date, "rate_type": "IDENTITY", "available_at": as_of}
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT rate,rate_date,rate_type,available_at,source_url,checksum
                       FROM fx_rates WHERE base_currency=%s AND quote_currency=%s
                         AND rate_date<=%s AND available_at<=%s AND rate_type=%s
                       ORDER BY rate_date DESC,available_at DESC LIMIT 1""",
                    (base, quote, rate_date, as_of, rate_type),
                )
                row = cursor.fetchone()
                if not row:
                    cursor.execute(
                        """SELECT rate,rate_date,rate_type,available_at,source_url,checksum
                           FROM fx_rates WHERE base_currency=%s AND quote_currency=%s
                             AND rate_date<=%s AND available_at<=%s AND rate_type=%s
                           ORDER BY rate_date DESC,available_at DESC LIMIT 1""",
                        (quote, base, rate_date, as_of, rate_type),
                    )
                    row = cursor.fetchone()
                    if not row or float(row[0]) == 0:
                        return None
                    names = [column.name for column in cursor.description]
                    result = dict(zip(names, row))
                    result["rate"] = 1 / float(result["rate"])
                    result["inverted"] = True
                    return result
                names = [column.name for column in cursor.description]
                return dict(zip(names, row))

    def publish_quant_snapshot(self, snapshot: ResearchSnapshot) -> str:
        snapshot.validate()
        release = next(
            (item for item in snapshot.sources if item.get("type") == "research_release"), {}
        )
        code_checksum = release.get("calculation_digest") or snapshot.checksum
        parameters = {"release": release} if release else {}
        with self._connect() as connection:
            with connection.cursor() as cursor:
                if snapshot.model_status == "VALIDATED_RESEARCH":
                    if not snapshot.validation_run_id:
                        raise ValueError("Validated snapshots require a validation run.")
                    cursor.execute(
                        """SELECT 1 FROM validation_runs
                           WHERE id=%s AND model_version_id=%s AND status='PASSED'""",
                        (snapshot.validation_run_id, snapshot.model_version),
                    )
                    if cursor.fetchone() is None:
                        raise ValueError("Validation run is missing, failed, or belongs to another model.")
                cursor.execute(
                    """INSERT INTO model_versions
                         (id, model_type, formula_version, parameters, code_checksum, status)
                       VALUES (%s,'CROSS_SECTIONAL_QUANT',%s,%s::jsonb,%s,%s)
                       ON CONFLICT (id) DO UPDATE SET
                         formula_version=EXCLUDED.formula_version,
                         parameters=EXCLUDED.parameters,
                         code_checksum=EXCLUDED.code_checksum,
                         status=EXCLUDED.status""",
                    (snapshot.model_version, snapshot.formula_version, strict_json_dumps(parameters),
                     code_checksum, snapshot.model_status),
                )
                cursor.execute(
                    """INSERT INTO quant_research_snapshots
                         (id, model_version_id, validation_run_id, effective_at, status,
                          schema_version, checksum, payload, approved_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
                       ON CONFLICT (checksum) DO NOTHING RETURNING id""",
                    (snapshot.snapshot_id, snapshot.model_version, snapshot.validation_run_id,
                     snapshot.effective_at, snapshot.model_status, snapshot.schema_version,
                     snapshot.checksum, strict_json_dumps(snapshot.to_dict())),
                )
                row = cursor.fetchone()
                return str(row[0]) if row else snapshot.snapshot_id

    def save_validation_run(self, *, run_id: str, model_version: str, input_checksum: str,
                            metrics: dict, acceptance: dict, holdout_start: str | None,
                            holdout_end: str | None, output_checksum: str) -> str:
        status = "PASSED" if acceptance.get("passed") else "FAILED"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO model_versions
                         (id, model_type, formula_version, parameters, code_checksum, status)
                       VALUES (%s,'CROSS_SECTIONAL_QUANT','monthly-lq45-next-open-v1',
                               '{}'::jsonb,%s,'SHADOW')
                       ON CONFLICT (id) DO NOTHING""", (model_version, input_checksum),
                )
                cursor.execute(
                    """INSERT INTO validation_runs
                         (id, model_version_id, input_checksum, started_at, completed_at,
                          status, holdout_start, holdout_end, metrics, acceptance, output_checksum)
                       VALUES (%s,%s,%s,now(),now(),%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                       ON CONFLICT (model_version_id,input_checksum) DO UPDATE SET
                         completed_at=EXCLUDED.completed_at, status=EXCLUDED.status,
                         metrics=EXCLUDED.metrics, acceptance=EXCLUDED.acceptance,
                         output_checksum=EXCLUDED.output_checksum
                       RETURNING id""",
                    (run_id, model_version, input_checksum, status, holdout_start, holdout_end,
                    strict_json_dumps(metrics), strict_json_dumps(acceptance), output_checksum),
                )
                return str(cursor.fetchone()[0])
