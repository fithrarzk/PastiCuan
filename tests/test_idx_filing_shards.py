import json
import unittest
from contextlib import nullcontext
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from data.idx_filing_importer import (
    aggregate_filing_progress,
    filing_shard,
    import_filings,
)
from data.filing_work_policy import FilingImportPolicy, is_retryable_filing_error
from data.ingestion import AcquiredArtifact
from tests.test_idx_filing_importer import filing


def accepted_artifact(**kwargs):
    return AcquiredArtifact(
        "artifact-id",
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


class DeterministicShardTests(unittest.TestCase):
    def test_import_policy_is_immutable_validated_and_shares_retry_allowlist(self):
        policy = FilingImportPolicy(shard_count=8, shard_index=3, run_id="batch-123")
        self.assertEqual(policy.shard_count, 8)
        with self.assertRaises(FrozenInstanceError):
            policy.max_attempts = 4
        for kwargs in (
            {"shard_count": 0},
            {"shard_count": 2, "shard_index": 2},
            {"max_attempts": 0},
            {"retry_backoff_seconds": -1},
            {"time_budget_seconds": 10, "per_item_reserve_seconds": 10},
            {"run_id": " "},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                FilingImportPolicy(**kwargs)
        self.assertTrue(is_retryable_filing_error("PROVIDER", "PROVIDER_UNAVAILABLE"))
        self.assertFalse(is_retryable_filing_error("SCHEMA", "SCHEMA_INVALID"))

    def test_known_issuer_year_groups_have_reproducible_assignments(self):
        self.assertEqual(filing_shard(filing("TEST"), 8), 6)
        bbri_q1 = {
            **filing("BBRI"),
            "period_end": "2024-03-31",
            "published_at": "2024-04-01T00:00:00Z",
        }
        bbri_q3 = {
            **bbri_q1,
            "filing_type": "Q3",
            "period_end": "2024-09-30",
            "published_at": "2024-10-01T00:00:00Z",
            "source_url": "https://idx.co.id/BBRI-q3.zip",
        }
        self.assertEqual(filing_shard(bbri_q1, 8), 5)
        self.assertEqual(filing_shard(bbri_q3, 8), 5)
        self.assertEqual(filing_shard({**bbri_q1, "period_end": "2025-03-31"}, 8), 7)

    def test_invalid_shard_count_fails(self):
        for count in (0, -1):
            with self.assertRaises(ValueError):
                filing_shard(filing(), count)


class ShardedImporterTests(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.preflight_schema_migrations.return_value = {"ok": True}
        self.repo.filing_download_fence.side_effect = lambda _row: nullcontext(True)
        self.repo.prepare_filing_import.side_effect = lambda rows: [
            {
                **row,
                "issuer_id": index + 1,
                "state": "PENDING",
                "attempt_count": 0,
            }
            for index, row in enumerate(rows)
        ]
        self.repo.claim_filing_work.return_value = {"lease_token": "token"}
        self.repo.renew_filing_work.return_value = True
        self.repo.complete_filing_import.return_value = {"state": "ACCEPTED"}
        self.repo.finalize_filing_work.return_value = {"state": "RETRYABLE"}
        self.acquire = Mock(side_effect=accepted_artifact)
        self.parse = Mock(return_value={"facts": [{}], "diagnostics": {}})

    def run_import(self, rows, **kwargs):
        policy_fields = {
            name: kwargs.pop(name)
            for name in tuple(kwargs)
            if name
            in {
                "shard_count",
                "shard_index",
                "run_id",
                "max_attempts",
                "retry_backoff_seconds",
                "time_budget_seconds",
                "per_item_reserve_seconds",
            }
        }
        return import_filings(
            {"filings": rows},
            self.repo,
            acquire=self.acquire,
            parse=self.parse,
            upload=Mock(),
            policy=FilingImportPolicy(**policy_fields),
            **kwargs,
        )

    def test_shard_syncs_full_manifest_but_touches_only_assigned_work(self):
        bbri = {
            **filing("BBRI"),
            "period_end": "2024-03-31",
            "published_at": "2024-04-01T00:00:00Z",
        }
        bbca = {
            **filing("BBCA"),
            "period_end": "2024-03-31",
            "published_at": "2024-04-01T00:00:00Z",
        }
        result = self.run_import([bbca, bbri], shard_count=8, shard_index=5)
        self.assertEqual(result["counts"]["manifest"], 2)
        self.assertEqual(result["counts"]["assigned"], 1)
        self.assertEqual(result["filings"][0]["identity"][0], "BBRI")
        self.assertEqual(len(self.repo.prepare_filing_import.call_args.args[0]), 2)
        self.assertEqual(self.acquire.call_count, 1)

    def test_retry_is_allowlisted_exponential_and_stops_at_durable_ceiling(self):
        self.repo.prepare_filing_import.side_effect = lambda rows: [
            {
                **rows[0],
                "issuer_id": 1,
                "state": "RETRYABLE",
                "attempt_count": 1,
                "last_error_class": "PROVIDER",
                "last_error_summary": "PROVIDER_UNAVAILABLE",
                "state_changed_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ]
        self.acquire.side_effect = RuntimeError("private provider body")
        sleeper = Mock()
        result = self.run_import(
            [filing()],
            max_attempts=3,
            retry_backoff_seconds=2,
            sleep=sleeper,
        )
        self.assertEqual(self.acquire.call_count, 2)
        sleeper.assert_called_once_with(4)
        self.assertTrue(
            all(
                call.kwargs["max_attempts"] == 3
                for call in self.repo.claim_filing_work.call_args_list
            )
        )
        self.assertEqual(result["counts"]["retryable"], 1)
        self.assertEqual(result["filings"][0]["code"], "RETRY_LIMIT_REACHED")
        self.assertNotIn("private provider body", str(result))

    def test_non_allowlisted_retryable_is_never_claimed(self):
        self.repo.prepare_filing_import.side_effect = lambda rows: [
            {
                **rows[0],
                "issuer_id": 1,
                "state": "RETRYABLE",
                "attempt_count": 1,
                "last_error_class": "SCHEMA",
                "last_error_summary": "SCHEMA_INVALID",
            }
        ]
        result = self.run_import([filing()], max_attempts=3)
        self.assertEqual(result["filings"][0]["code"], "RETRY_NOT_ALLOWED")
        self.assertEqual(result["counts"]["retryable"], 1)
        self.repo.claim_filing_work.assert_not_called()
        self.acquire.assert_not_called()

    def test_restart_observes_durable_retry_backoff_before_claim(self):
        changed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.repo.prepare_filing_import.side_effect = lambda rows: [
            {
                **rows[0],
                "issuer_id": 1,
                "state": "RETRYABLE",
                "attempt_count": 2,
                "last_error_class": "DATABASE",
                "last_error_summary": "DATABASE_UNAVAILABLE",
                "state_changed_at": changed_at,
            }
        ]
        result = self.run_import(
            [filing()],
            max_attempts=3,
            retry_backoff_seconds=30,
            now=lambda: changed_at,
        )
        self.assertEqual(result["filings"][0]["code"], "RETRY_BACKOFF")
        self.assertEqual(result["counts"]["retryable"], 1)
        self.repo.claim_filing_work.assert_not_called()
        self.acquire.assert_not_called()

    def test_budget_stops_before_starting_another_filing(self):
        clock = Mock(side_effect=[0, 95])
        result = self.run_import(
            [filing()],
            time_budget_seconds=100,
            per_item_reserve_seconds=10,
            monotonic=clock,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["filings"][0]["code"], "BUDGET_EXHAUSTED")
        self.assertEqual(result["counts"]["remaining"], 1)
        self.repo.claim_filing_work.assert_not_called()
        self.acquire.assert_not_called()


class DurableAggregationTests(unittest.TestCase):
    def test_aggregate_validates_and_reads_durable_ledger(self):
        repository = Mock()
        repository.preflight_schema_migrations.return_value = {"ok": True}
        repository.prepare_filing_import.side_effect = lambda rows: [
            {**row, "issuer_id": index + 1, "state": "PENDING"}
            for index, row in enumerate(rows)
        ]
        repository.aggregate_filing_progress.return_value = {
            "manifest": 2,
            "accepted": 1,
            "skipped_accepted": 1,
            "quarantined": 0,
            "retryable": 0,
            "leased_elsewhere": 0,
            "remaining": 0,
        }
        rows = [filing("AAAA"), filing("BBBB")]
        result = aggregate_filing_progress(
            {"filings": rows}, repository, run_id="batch-123"
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "COMPLETE")
        repository.aggregate_filing_progress.assert_called_once()
        prepared, run_id = repository.aggregate_filing_progress.call_args.args
        self.assertEqual(len(prepared), 2)
        self.assertEqual(run_id, "batch-123")

    def test_cli_passes_explicit_shard_policy_and_aggregate_mode(self):
        from operations.research_cli import main

        aggregate = {
            "ok": False,
            "code": "INCOMPLETE",
            "counts": {"remaining": 1},
        }
        with (
            TemporaryDirectory() as directory,
            patch(
                "operations.research_cli.ingest_idx_xbrl_manifest",
                return_value=aggregate,
            ) as ingest,
        ):
            report = Path(directory) / "report.json"
            code = main(
                [
                    "ingest-idx-xbrl",
                    "--manifest",
                    "manifest.json",
                    "--report",
                    str(report),
                    "--shard-count",
                    "8",
                    "--shard-index",
                    "3",
                    "--run-id",
                    "batch-123",
                    "--max-attempts",
                    "3",
                    "--retry-backoff-seconds",
                    "5",
                    "--time-budget-seconds",
                    "1200",
                    "--aggregate-only",
                ]
            )
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(report.read_text()), aggregate)
            self.assertEqual(
                ingest.call_args.kwargs,
                {
                    "archive_directory": None,
                    "use_r2": False,
                    "shard_count": 8,
                    "shard_index": 3,
                    "run_id": "batch-123",
                    "max_attempts": 3,
                    "retry_backoff_seconds": 5.0,
                    "time_budget_seconds": 1200.0,
                    "aggregate_only": True,
                },
            )


if __name__ == "__main__":
    unittest.main()
