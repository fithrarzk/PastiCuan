import unittest
import os
from uuid import uuid4
from pathlib import Path

from scripts.ci.check_migrations import migration_checksums, read_sql
from storage.database import validate_writer_connection_mode
from storage.repository import SnapshotRepository


ROOT = Path(__file__).resolve().parents[1]


class FilingWorkLedgerContractTests(unittest.TestCase):
    def test_writer_connection_rejects_transaction_pooling(self):
        with self.assertRaisesRegex(RuntimeError, "session-compatible"):
            validate_writer_connection_mode(
                "postgres" + "ql://user@pooler.example:6543/postgres"
            )
        validate_writer_connection_mode(
            "postgres" + "ql://user@pooler.example:5432/postgres"
        )

    def test_migration_007_is_a_utf8_reversible_pair(self):
        migrations = ROOT / "storage/migrations"
        checksums = migration_checksums(migrations)
        self.assertEqual(len(checksums), 8)
        self.assertIn("007_filing_work_ledger", checksums)
        self.assertIn("008_filing_artifact_mismatch", checksums)
        self.assertIn(
            "CREATE TABLE filing_work_items",
            read_sql(migrations / "007_filing_work_ledger.up.sql"),
        )
        self.assertIn(
            "CREATE TABLE filing_work_attempts",
            read_sql(migrations / "007_filing_work_ledger.up.sql"),
        )

    def test_repository_exposes_durable_ledger_seams(self):
        expected = {
            "sync_reviewed_filings",
            "get_filing_work_statuses",
            "claim_filing_work",
            "renew_filing_work",
            "finalize_filing_work",
            "expire_filing_work_leases",
            "get_filing_attempt_history",
            "get_filing_work_counts",
            "filing_download_fence",
        }
        self.assertTrue(expected.issubset(set(dir(SnapshotRepository))))
        self.assertNotIn("sync_filing_work_items", dir(SnapshotRepository))

    def test_stable_error_surface_rejects_raw_or_unknown_summaries(self):
        self.assertEqual(
            SnapshotRepository._error_fields("provider", "provider_unavailable"),
            ("PROVIDER", "PROVIDER_UNAVAILABLE"),
        )
        with self.assertRaises(ValueError):
            SnapshotRepository._error_fields("provider", "raw provider response body")
        with self.assertRaises(ValueError):
            SnapshotRepository._error_fields("provider", RuntimeError("provider body"))

    def test_attempt_contract_has_run_and_source_snapshots(self):
        sql = read_sql(ROOT / "storage/migrations/007_filing_work_ledger.up.sql")
        for field in (
            "run_id",
            "lease_expires_at",
            "source_url",
            "expected_checksum",
            "artifact_status",
        ):
            self.assertIn(field, sql)
        self.assertIn("DEFERRABLE INITIALLY DEFERRED", sql)

    def test_roles_do_not_grant_delete_or_bot_ledger_access(self):
        roles = (ROOT / "storage/supabase_roles.sql").read_text()
        self.assertNotIn("DELETE ON filing_work_", roles)
        bot_grants = [line for line in roles.splitlines() if "TO pasticuan_bot" in line]
        self.assertFalse(any("filing_work_" in grant for grant in bot_grants))


@unittest.skipUnless(
    os.getenv("PASTICUAN_TEST_DATABASE_URL"), "disposable PostgreSQL required"
)
class FilingImportTransactionTests(unittest.TestCase):
    def test_atomic_completion_rollback_stale_fence_and_point_in_time(self):
        import psycopg
        from data.idx_xbrl import parse_idx_xbrl
        from tests.test_idx_xbrl import _instance
        from tests.test_idx_filing_importer import filing

        url = os.environ["PASTICUAN_TEST_DATABASE_URL"]
        repo = SnapshotRepository(lambda: psycopg.connect(url))
        ticker = "T" + uuid4().hex[:7].upper()
        with psycopg.connect(url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO issuers(ticker,legal_name,sector,currency,active_from) VALUES (%s,%s,'Industrials','IDR','2025-01-01') RETURNING id",
                    (ticker, ticker),
                )
                issuer_id = cursor.fetchone()[0]
        source = filing(ticker)
        row = repo.prepare_filing_import([source])[0]
        self.assertEqual(row["state"], "PENDING")
        with repo.filing_download_fence(row) as first_fence:
            self.assertTrue(first_fence)
            with repo.filing_download_fence(row) as second_fence:
                self.assertFalse(second_fence)
        with repo.filing_download_fence(row) as released_fence:
            self.assertTrue(released_fence)
        lease = repo.claim_filing_work(row, "ci", run_id=str(uuid4()))
        artifact = dict(
            id=str(uuid4()),
            provider="IDX",
            source_class="official",
            artifact_type="idx_xbrl_instance",
            source_url=source["source_url"],
            checksum=uuid4().hex * 2,
            retrieved_at="2026-01-01T00:00:00Z",
            published_at=source["published_at"],
            object_key="ci",
            size_bytes=100,
        )
        parsed = parse_idx_xbrl(
            _instance().replace(b"TEST", ticker.encode()),
            ticker=ticker,
            source_url=source["source_url"],
            published_at=source["published_at"],
            filing_type="Q1",
            filing_period_end="2025-03-31",
            document_checksum=artifact["checksum"],
            object_key="ci",
        )
        self.assertIsNone(
            repo.complete_filing_import(row, str(uuid4()), artifact, parsed=parsed)
        )
        # Inject a malformed later fact: earlier fact and artifact must roll back.
        with self.assertRaises(Exception):
            repo.complete_filing_import(
                row,
                lease["lease_token"],
                artifact,
                parsed={**parsed, "facts": [parsed["facts"][0], {}]},
            )
        self.assertEqual(repo.prepare_filing_import([source])[0]["state"], "RUNNING")
        with psycopg.connect(url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM source_artifacts WHERE id=%s",
                    (artifact["id"],),
                )
                self.assertEqual(cursor.fetchone()[0], 0)
        result = repo.complete_filing_import(
            row, lease["lease_token"], artifact, parsed=parsed
        )
        self.assertEqual(result["state"], "ACCEPTED")
        self.assertEqual(repo.prepare_filing_import([source])[0]["state"], "ACCEPTED")
        self.assertEqual(
            repo.get_filing_attempt_history(row)[0]["outcome_state"], "ACCEPTED"
        )
        self.assertEqual(repo.facts_as_of(issuer_id, "2025-03-31T23:59:59Z"), [])
        self.assertTrue(repo.facts_as_of(issuer_id, "2025-04-02T00:00:00Z"))
        self.assertIsNone(
            repo.complete_filing_import(
                row, lease["lease_token"], artifact, parsed=parsed
            )
        )
        from data.idx_filing_importer import import_filings
        from unittest.mock import Mock

        never_download = Mock(side_effect=AssertionError("accepted work redownloaded"))
        rerun = import_filings({"filings": [source]}, repo, acquire=never_download)
        self.assertTrue(rerun["ok"])
        self.assertEqual(rerun["counts"]["skipped_accepted"], 1)
        never_download.assert_not_called()
        # The next independent filing can be quarantined without undoing acceptance.
        other = {
            **source,
            "period_end": "2025-06-30",
            "filing_type": "Q2",
            "published_at": "2025-07-01T00:00:00Z",
            "source_url": source["source_url"].replace(".zip", "-q2.zip"),
        }
        second = repo.prepare_filing_import([source, other])[1]
        second_lease = repo.claim_filing_work(second, "ci")
        second_artifact = {
            **artifact,
            "id": str(uuid4()),
            "checksum": uuid4().hex * 2,
            "source_url": other["source_url"],
            "published_at": other["published_at"],
        }
        repo.complete_filing_import(
            second, second_lease["lease_token"], second_artifact, state="QUARANTINED"
        )
        self.assertEqual(
            [item["state"] for item in repo.prepare_filing_import([source, other])],
            ["ACCEPTED", "QUARANTINED"],
        )
        mismatch = {
            **source,
            "period_end": "2025-09-30",
            "filing_type": "Q3",
            "published_at": "2025-10-01T00:00:00Z",
            "source_url": source["source_url"].replace(".zip", "-q3.zip"),
            "checksum": "f" * 64,
        }
        mismatch_row = repo.prepare_filing_import([mismatch])[0]
        mismatch_lease = repo.claim_filing_work(mismatch_row, "ci")
        mismatch_artifact = {
            **artifact,
            "id": str(uuid4()),
            "checksum": "e" * 64,
            "source_url": mismatch["source_url"],
            "published_at": mismatch["published_at"],
        }
        repo.complete_filing_import(
            mismatch_row,
            mismatch_lease["lease_token"],
            mismatch_artifact,
            state="QUARANTINED",
            error_class="PROVENANCE",
            error_summary="ARTIFACT_MISMATCH",
        )
        mismatch_status = repo.prepare_filing_import([mismatch])[0]
        self.assertEqual(mismatch_status["state"], "QUARANTINED")
        with psycopg.connect(url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT expected_checksum,artifact_checksum,last_error_summary
                       FROM filing_work_items
                       WHERE issuer_id=%s AND filing_type='Q3'""",
                    (issuer_id,),
                )
                observed = tuple(repo._db_text(value) for value in cursor.fetchone())
                self.assertEqual(observed, ("f" * 64, "e" * 64, "ARTIFACT_MISMATCH"))


if __name__ == "__main__":
    unittest.main()
