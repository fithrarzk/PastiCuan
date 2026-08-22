import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from analysis.scan_v2 import _quant_is_fresh
from operations.research_cli import (
    automatic_idx_period,
    discovery_blockers,
    run_daily_research,
)
from operations.research_release import calculation_digest, load_release


class ReleasePolicyTests(unittest.TestCase):
    def test_calculation_digest_changes_with_code_and_is_deterministic(self):
        with TemporaryDirectory() as root:
            base = Path(root)
            (base / "analysis").mkdir()
            code = base / "analysis" / "score.py"
            code.write_text("WEIGHT = 1\n")
            release = {
                "release_id": "test-r1",
                "model_version": "test-shadow",
                "formula_version": "test-v1",
                "calculation_revision": 1,
                "status": "SHADOW",
                "calculation_paths": ["analysis/score.py"],
            }
            first = calculation_digest(release, repository_root=base)
            self.assertEqual(first, calculation_digest(release, repository_root=base))
            code.write_text("WEIGHT = 2\n")
            self.assertNotEqual(
                first, calculation_digest(release, repository_root=base)
            )

    def test_automatic_release_cannot_be_validated_status(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "release.json"
            path.write_text(
                json.dumps(
                    {
                        "release_id": "test",
                        "model_version": "test",
                        "formula_version": "test",
                        "calculation_revision": 1,
                        "status": "VALIDATED_RESEARCH",
                        "calculation_paths": ["x.py"],
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "restricted to SHADOW"):
                load_release(path)


class CalendarPolicyTests(unittest.TestCase):
    def test_official_calendar_excludes_holiday_from_quant_age(self):
        snapshot = SimpleNamespace(
            snapshot_id="quant",
            effective_at="2026-08-14T17:00:00+07:00",
        )

        class Calendar:
            def expected_session_age(self, start, end):
                self.window = (start, end)
                return 1  # 17 August is HOLIDAY; only 18 August counts.

        calendar = Calendar()
        observed = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)
        self.assertTrue(_quant_is_fresh(snapshot, observed, calendar))
        self.assertEqual(calendar.window, ("2026-08-14", "2026-08-18"))

    def test_idx_period_is_derived_without_manual_inputs(self):
        self.assertEqual(automatic_idx_period("2026-08-18T00:00:00Z"), (2026, "tw2"))
        self.assertEqual(automatic_idx_period("2026-02-01T00:00:00Z"), (2025, "tw3"))

    def test_historical_ipo_gaps_do_not_block_manifest_review(self):
        discovery = {
            "current_period_missing": [],
            "annual_missing": {"2021": ["AADI", "AMMN"], "2022": ["AADI"]},
            "prior_annual_missing": ["AADI"],
        }
        self.assertEqual(discovery_blockers(discovery), [])
        discovery["current_period_missing"] = ["BBCA"]
        self.assertEqual(discovery_blockers(discovery), ["BBCA"])


class DailyOrchestrationTests(unittest.TestCase):
    def _run_not_ready(
        self, final_attempt, *, session_age=1, membership_count=45, coverage_pct=80.0
    ):
        repository = SimpleNamespace(
            record_research_job=lambda value: None,
            applied_schema_migrations=lambda: [],
        )
        market = {
            "ready": False,
            "observed": datetime(2026, 8, 18, 12, tzinfo=timezone.utc),
            "on_date": "2026-08-18",
            "session_date": "2026-08-18",
            "coverage_pct": coverage_pct,
            "membership_count": membership_count,
            "imported_count": 0,
            "session_age": session_age,
            "reason": "Current session is not complete.",
            "bases": [],
            "same_session": [],
            "excluded": [],
        }
        provenance = {
            "release_id": "test-r1",
            "calculation_digest": "a" * 64,
            "git_commit": "test",
            "model_version": "test",
            "formula_version": "test",
            "calculation_revision": 1,
            "type": "research_release",
        }
        with (
            TemporaryDirectory() as root,
            patch.dict(
                "os.environ",
                {
                    "SUPABASE_WRITER_DATABASE_URL": "database-configured",
                    "SNAPSHOT_ED25519_PRIVATE_KEY": "enabled",
                },
                clear=False,
            ),
            patch("storage.database.connect_from_env"),
            patch("storage.repository.SnapshotRepository", return_value=repository),
            patch(
                "operations.research_cli.load_release",
                return_value={"status": "SHADOW"},
            ),
            patch(
                "operations.research_cli.release_provenance", return_value=provenance
            ),
            patch("operations.research_cli._required_migrations", return_value=[]),
            patch(
                "operations.research_cli.refresh_lq45_market_history",
                return_value=market,
            ),
        ):
            output = str(Path(root) / "report.json")
            result = run_daily_research(output, final_attempt=final_attempt)
            persisted = json.loads(Path(output).read_text())
        self.assertEqual(result, persisted)
        return result

    def test_early_current_session_waits_without_publication(self):
        result = self._run_not_ready(False)
        self.assertEqual(result["outcome"]["exit_code"], 10)
        self.assertEqual(result["outcome"]["persisted_status"], "DEGRADED")

    def test_final_attempt_fails_closed(self):
        result = self._run_not_ready(True)
        self.assertEqual(result["outcome"]["exit_code"], 20)
        self.assertEqual(result["outcome"]["persisted_status"], "DEGRADED")

    def test_stale_or_short_market_is_unavailable_even_before_final_attempt(self):
        stale = self._run_not_ready(False, session_age=2)
        short = self._run_not_ready(False, membership_count=44)
        absent = self._run_not_ready(False, session_age=None, coverage_pct=0.0)
        self.assertEqual(stale["outcome"]["exit_code"], 20)
        self.assertEqual(short["outcome"]["exit_code"], 20)
        self.assertEqual(absent["outcome"]["exit_code"], 20)

    def test_matching_primary_session_is_an_idempotent_noop(self):
        digest = "b" * 64
        latest = SimpleNamespace(
            mode="PRIMARY",
            session_date="2026-08-18",
            source_summary={"research_release": {"calculation_digest": digest}},
            quant_snapshot_id="quant",
            snapshot_id="scan",
            checksum="scan-checksum",
        )
        repository = SimpleNamespace(
            record_research_job=lambda value: None,
            applied_schema_migrations=lambda: [],
            latest_scan_snapshot=lambda: latest,
        )
        market = {
            "ready": True,
            "observed": datetime(2026, 8, 18, 12, tzinfo=timezone.utc),
            "on_date": "2026-08-18",
            "session_date": "2026-08-18",
            "coverage_pct": 100.0,
            "membership_count": 45,
            "imported_count": 0,
            "session_age": 0,
            "reason": None,
            "bases": [],
            "same_session": [],
            "excluded": [],
        }
        release = {
            "release_id": "test-r1",
            "calculation_digest": digest,
            "git_commit": "test",
            "model_version": "test",
            "formula_version": "test",
            "calculation_revision": 1,
            "type": "research_release",
        }
        with (
            TemporaryDirectory() as root,
            patch.dict(
                "os.environ",
                {
                    "SUPABASE_WRITER_DATABASE_URL": "database-configured",
                    "SNAPSHOT_ED25519_PRIVATE_KEY": "enabled",
                },
                clear=False,
            ),
            patch("storage.database.connect_from_env"),
            patch("storage.repository.SnapshotRepository", return_value=repository),
            patch(
                "operations.research_cli.load_release",
                return_value={"status": "SHADOW"},
            ),
            patch("operations.research_cli.release_provenance", return_value=release),
            patch("operations.research_cli._required_migrations", return_value=[]),
            patch(
                "operations.research_cli.refresh_lq45_market_history",
                return_value=market,
            ),
            patch(
                "operations.research_cli.evaluate_signal_outcomes",
                return_value={"saved": 0, "pending": 0},
            ),
            patch("operations.research_cli.build_snapshot_from_database") as build,
        ):
            result = run_daily_research(str(Path(root) / "report.json"))
        self.assertEqual(result["status"], "NOOP")
        build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
