import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from data.idx_filing_importer import import_filings
from data.ingestion import AcquiredArtifact


def filing(ticker="TEST"):
    return dict(
        ticker=ticker,
        filing_type="Q1",
        period_end="2025-03-31",
        restatement_version=1,
        published_at="2025-04-01T00:00:00Z",
        audit_status="UNAUDITED",
        source_url=f"https://idx.co.id/{ticker}.zip",
    )


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.preflight_schema_migrations.return_value = {"ok": True}
        self.repo.prepare_filing_import.side_effect = lambda rows: [
            {**row, "issuer_id": i + 1, "state": "ACCEPTED"}
            for i, row in enumerate(rows)
        ]
        self.acquire = Mock()
        self.parse = Mock(return_value={"facts": [], "diagnostics": {}})
        self.upload = Mock()

    def run_import(self, rows=None):
        return import_filings(
            {"filings": rows if rows is not None else [filing()]},
            self.repo,
            acquire=self.acquire,
            parse=self.parse,
            upload=self.upload,
            use_r2=True,
        )

    def pending(self, states):
        self.repo.prepare_filing_import.side_effect = lambda rows: [
            {**row, "issuer_id": i + 1, "state": state}
            for i, (row, state) in enumerate(zip(rows, states))
        ]
        self.repo.claim_filing_work.return_value = {"lease_token": "token"}
        self.repo.renew_filing_work.return_value = True
        self.repo.complete_filing_import.return_value = {"state": "ACCEPTED"}
        self.repo.finalize_filing_work.return_value = {"state": "RETRYABLE"}

        def acquire(**kwargs):
            return AcquiredArtifact(
                "id",
                "IDX",
                "official",
                "idx_xbrl_instance",
                kwargs["source_url"],
                "a" * 64,
                "2026-01-01T00:00:00Z",
                kwargs["published_at"],
                "key",
                "application/zip",
                3,
            ), b"zip"

        self.acquire.side_effect = acquire

    def test_accepted_rerun_skips_every_external_and_write_boundary(self):
        result = self.run_import()
        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["skipped_accepted"], 1)
        self.assertEqual(result["counts"]["remaining"], 0)
        self.acquire.assert_not_called()
        self.upload.assert_not_called()
        self.parse.assert_not_called()
        self.repo.claim_filing_work.assert_not_called()
        self.repo.complete_filing_import.assert_not_called()

    def test_invalid_manifest_and_missing_migration_stop_before_sync_or_network(self):
        for rows in (
            [filing(), filing()],
            [{**filing(), "source_url": "https://evil.test/a.zip"}],
        ):
            self.assertFalse(self.run_import(rows)["ok"])
        self.repo.prepare_filing_import.assert_not_called()
        self.acquire.assert_not_called()
        self.repo.preflight_schema_migrations.return_value = {"ok": False}
        migration_failure = self.run_import()
        self.assertFalse(migration_failure["ok"])
        self.assertEqual(migration_failure["counts"]["remaining"], 1)
        self.repo.preflight_schema_migrations.assert_called_with(
            ["007_filing_work_ledger"]
        )
        self.repo.prepare_filing_import.assert_not_called()

    def test_mixed_manifest_skips_terminal_states_and_claims_only_unfinished(self):
        self.pending(["ACCEPTED", "QUARANTINED", "PENDING"])
        result = self.run_import([filing("AAAA"), filing("BBBB"), filing("CCCC")])
        self.assertFalse(result["ok"])
        self.assertEqual(result["counts"]["downloaded"], 1)
        self.assertEqual(result["counts"]["quarantined"], 1)
        self.assertEqual(result["counts"]["remaining"], 1)
        self.assertEqual(self.repo.claim_filing_work.call_count, 1)

    def test_provider_failure_is_retryable_and_redacted(self):
        self.pending(["PENDING"])
        self.acquire.side_effect = RuntimeError("private-provider-body")
        result = self.run_import()
        self.assertEqual(result["counts"]["retryable"], 1)
        self.assertNotIn("private-provider-body", str(result))
        self.assertEqual(
            self.repo.finalize_filing_work.call_args.kwargs["error_summary"],
            "PROVIDER_UNAVAILABLE",
        )

    def test_parser_failure_quarantines_and_next_filing_still_completes(self):
        self.pending(["PENDING", "PENDING"])
        self.parse.side_effect = [
            ValueError("private-body"),
            {"facts": [], "diagnostics": {}},
        ]
        self.repo.complete_filing_import.side_effect = [
            {"state": "QUARANTINED"},
            {"state": "ACCEPTED"},
        ]
        result = self.run_import([filing("AAAA"), filing("BBBB")])
        self.assertEqual(result["counts"]["accepted"], 1)
        self.assertEqual(result["counts"]["quarantined"], 1)
        self.assertNotIn("private-body", str(result))

    def test_live_lease_or_lost_claim_never_downloads(self):
        self.pending(["RUNNING"])
        self.repo.prepare_filing_import.side_effect = lambda rows: [
            {
                **rows[0],
                "issuer_id": 1,
                "state": "RUNNING",
                "lease_expires_at": datetime(2100, 1, 1, tzinfo=timezone.utc),
            }
        ]
        self.assertEqual(self.run_import()["counts"]["leased_elsewhere"], 1)
        self.repo.claim_filing_work.assert_not_called()
        self.pending(["PENDING"])
        self.repo.claim_filing_work.return_value = None
        self.assertEqual(self.run_import()["counts"]["leased_elsewhere"], 1)
        self.acquire.assert_not_called()

    def test_sync_conflicts_and_unknown_issuer_stop_before_network(self):
        for error in (ValueError("provenance-private"), ValueError("unknown-private")):
            self.repo.prepare_filing_import.side_effect = error
            result = self.run_import()
            self.assertEqual(result["code"], "MANIFEST_SYNC_FAILED")
            self.assertNotIn("private", str(result))
        self.acquire.assert_not_called()

    def test_r2_failure_and_lost_renewal_cannot_accept(self):
        self.pending(["PENDING"])
        self.upload.side_effect = RuntimeError("private-r2")
        result = self.run_import()
        self.assertEqual(result["counts"]["retryable"], 1)
        self.repo.complete_filing_import.assert_not_called()
        self.repo.renew_filing_work.return_value = False
        self.acquire.reset_mock()
        self.assertEqual(self.run_import()["counts"]["leased_elsewhere"], 1)
        self.acquire.assert_not_called()

    def test_expired_work_is_reclaimed_and_checksum_conflict_never_parses(self):
        self.pending(["RUNNING"])
        result = self.run_import([{**filing(), "checksum": "b" * 64}])
        self.assertEqual(result["counts"]["retryable"], 1)
        self.assertEqual(result["filings"][0]["code"], "ARTIFACT_MISMATCH")
        self.parse.assert_not_called()

    def test_cli_report_and_exit_require_every_filing_accepted(self):
        from operations.research_cli import main

        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            for ok in (False, True):
                with patch(
                    "operations.research_cli.ingest_idx_xbrl_manifest",
                    return_value={"ok": ok},
                ):
                    code = main(
                        [
                            "ingest-idx-xbrl",
                            "--manifest",
                            "unused",
                            "--report",
                            str(path),
                        ]
                    )
                self.assertEqual(code, 0 if ok else 2)
                self.assertEqual(json.loads(path.read_text()), {"ok": ok})
