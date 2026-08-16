from datetime import date, datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from analysis.scan_snapshots import ScanResearchSnapshot, signed_scan_snapshot
from analysis.scan_v2 import (
    _quant_is_fresh,
    build_full_lq45_scan,
    planned_entry_risk_reward,
    risk_reward_score,
    score_candidate,
)
from storage.repository import SnapshotRepository


def base_record(**overrides):
    value = {
        "ticker": "TEST", "display_ticker": "TEST.JK", "company": "Test",
        "sector": "Industrials", "session_date": "2026-08-14",
        "data_usable": True, "quality_reasons": [], "current_price": 100,
        "technical_score": 80, "technical_coverage": 100,
        "avg_value": 30_000_000_000,
        "buy_range": {
            "preferred_range": None,
            "technical_range": {"low": 95, "high": 100},
        },
        "stop_loss": 90, "take_profit": 120,
    }
    value.update(overrides)
    return value


class ScanScoringTests(unittest.TestCase):
    def test_weekend_quant_snapshot_is_fresh_for_sunday_scan(self):
        snapshot = SimpleNamespace(
            snapshot_id="weekend-quant", effective_at="2026-08-16T00:00:00+00:00",
        )
        observed = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
        self.assertTrue(_quant_is_fresh(snapshot, observed))

    def test_planned_rr_uses_conservative_entry_high(self):
        result = planned_entry_risk_reward(base_record())
        self.assertEqual(result["entry_reference"], 100)
        self.assertEqual(result["planned_rr"], 2)
        self.assertEqual(result["price_state"], "IN_ZONE")
        self.assertEqual(result["zone_type"], "technical_only")

    def test_primary_score_uses_fixed_weights_without_renormalizing_coverage(self):
        quant = {"composite_percentile": 70, "coverage_pct": 75,
                 "value": 60, "quality": 70, "momentum": 80, "low_volatility": 70}
        candidate, reason = score_candidate(base_record(), quant, primary=True)
        self.assertIsNone(reason)
        self.assertAlmostEqual(candidate["ranking_score"], 81.0)
        self.assertAlmostEqual(candidate["coverage_pct"], 90.0)
        self.assertEqual(candidate["eligibility"], "SHORTLIST")

    def test_degraded_mode_never_publishes_an_overall_score(self):
        candidate, reason = score_candidate(base_record(), None, primary=False)
        self.assertIsNone(reason)
        self.assertIsNone(candidate["ranking_score"])
        self.assertIsNone(candidate["composite_score"])
        self.assertEqual(candidate["eligibility"], "WATCH")

    def test_sub_one_rr_is_excluded(self):
        low_rr = base_record(stop_loss=80, take_profit=110)
        candidate, reason = score_candidate(low_rr, None, primary=False)
        self.assertIsNone(candidate)
        self.assertIn("below 1.0R", reason)
        self.assertIsNone(risk_reward_score(.99))

    def test_invalid_price_order_is_rejected(self):
        result = planned_entry_risk_reward(base_record(stop_loss=101))
        self.assertEqual(result["status"], "INVALID")


class ScanSnapshotTests(unittest.TestCase):
    def _snapshot(self):
        return signed_scan_snapshot(
            snapshot_id="11111111-1111-1111-1111-111111111111",
            session_date="2026-08-14", created_at="2026-08-14T17:30:00+07:00",
            mode="PRIMARY", universe_coverage_pct=100,
            quant_snapshot_id="22222222-2222-2222-2222-222222222222",
            candidates=[
                {"ticker": "BBCA", "ranking_score": 80, "eligibility": "SHORTLIST"},
                {"ticker": "TLKM", "ranking_score": 60, "eligibility": "WATCH"},
            ],
            excluded=[{"ticker": "ASII", "reason": "R/R below 1.0R"}],
        )

    def test_filtering_does_not_recalculate_full_universe_rank(self):
        snapshot = self._snapshot()
        filtered = snapshot.to_bundle(["TLKM", "BBCA", "OUT"], today=date(2026, 8, 16))
        self.assertEqual([row["ranking_score"] for row in filtered.candidates], [80, 60])
        self.assertTrue(any(row["ticker"] == "OUT" for row in filtered.excluded))

    def test_stale_snapshot_returns_no_ranking(self):
        bundle = self._snapshot().to_bundle(today=date(2026, 8, 20))
        self.assertEqual(bundle.mode, "UNAVAILABLE")
        self.assertEqual(bundle.candidates, [])

    def test_checksum_tampering_is_rejected(self):
        payload = self._snapshot().to_dict()
        payload["mode"] = "DEGRADED"
        with self.assertRaisesRegex(ValueError, "checksum"):
            ScanResearchSnapshot.from_dict(payload)

    def test_exact_constituent_count_is_required_before_provider_calls(self):
        class Repository:
            def constituent_issuers_as_of(self, *_): return [{"ticker": "BBCA"}]

        snapshot = build_full_lq45_scan(
            Repository(), now=datetime(2026, 8, 14, 10, tzinfo=timezone.utc),
            loader=lambda *_args, **_kwargs: self.fail("provider must not be called"),
        )
        self.assertEqual(snapshot.mode, "UNAVAILABLE")
        self.assertIn("found 1", snapshot.warnings[0])

    def test_full_universe_build_joins_approved_quant_and_persists_market_input(self):
        tickers = [f"T{i:02d}" for i in range(45)]
        history = pd.DataFrame(
            {"Open": [99], "High": [102], "Low": [98], "Close": [100], "Volume": [1_000_000]},
            index=pd.to_datetime(["2026-08-14"]),
        )
        quant = {
            ticker: {"composite_percentile": 70, "coverage_pct": 100,
                     "value": 60, "quality": 70, "momentum": 80, "low_volatility": 70}
            for ticker in tickers
        }

        class Repository:
            imported = None
            recorded = None

            def constituent_issuers_as_of(self, *_):
                return [{"ticker": ticker, "sector": "Test", "legal_name": ticker} for ticker in tickers]

            def completed_session_age(self, *_): return 0

            def import_yahoo_market_histories(self, values, *, available_at):
                self.imported = (values, available_at)
                return len(values)

            def record_completed_market_session(self, session_date, *, observed_at):
                self.recorded = (session_date, observed_at)

            def latest_approved_quant_snapshot(self):
                return SimpleNamespace(
                    snapshot_id="22222222-2222-2222-2222-222222222222",
                    effective_at="2026-08-01T16:00:00+07:00", rankings=quant,
                )

        repository = Repository()
        bases = {ticker: base_record(ticker=ticker, display_ticker=f"{ticker}.JK", _history=history)
                 for ticker in tickers}
        def unavailable_archive(_key, _body):
            raise PermissionError("fixture must not block scan publication")
        with patch("analysis.scan_v2._fetch_base", side_effect=lambda ticker, *_: bases[ticker]):
            snapshot = build_full_lq45_scan(
                repository, now=datetime(2026, 8, 14, 10, 30, tzinfo=timezone.utc),
                loader=lambda *_args, **_kwargs: None,
                archive_callback=unavailable_archive,
            )

        self.assertEqual(snapshot.mode, "PRIMARY")
        self.assertEqual(snapshot.universe_coverage_pct, 100)
        self.assertEqual(snapshot.quant_snapshot_id, "22222222-2222-2222-2222-222222222222")
        self.assertEqual(len(snapshot.candidates), 45)
        self.assertEqual(len(repository.imported[0]), 45)
        self.assertEqual(repository.recorded[0], "2026-08-14")
        self.assertEqual(snapshot.source_summary["r2_archive"]["status"], "FAILED")
        self.assertTrue(any("R2" in warning for warning in snapshot.warnings))

    def test_primary_requires_90_percent_usable_quant_rows(self):
        tickers = [f"T{i:02d}" for i in range(45)]
        history = pd.DataFrame(
            {"Open": [99], "High": [102], "Low": [98], "Close": [100], "Volume": [1_000_000]},
            index=pd.to_datetime(["2026-08-14"]),
        )
        quant = {
            ticker: {"composite_percentile": 70, "coverage_pct": 100 if i < 40 else 50}
            for i, ticker in enumerate(tickers)
        }

        class Repository:
            def constituent_issuers_as_of(self, *_):
                return [{"ticker": ticker, "sector": "Test", "legal_name": ticker} for ticker in tickers]
            def completed_session_age(self, *_): return 0
            def import_yahoo_market_histories(self, *_args, **_kwargs): return 45
            def record_completed_market_session(self, *_args, **_kwargs): pass
            def latest_approved_quant_snapshot(self):
                return SimpleNamespace(snapshot_id="quant", effective_at="2026-08-01", rankings=quant)

        bases = {ticker: base_record(ticker=ticker, _history=history) for ticker in tickers}
        with patch("analysis.scan_v2._fetch_base", side_effect=lambda ticker, *_: bases[ticker]):
            snapshot = build_full_lq45_scan(
                Repository(), now=datetime(2026, 8, 14, 10, 30, tzinfo=timezone.utc),
                loader=lambda *_args, **_kwargs: None,
            )
        self.assertEqual(snapshot.mode, "DEGRADED")
        self.assertTrue(all(row["ranking_score"] is None for row in snapshot.candidates))

    def test_missing_database_sessions_cannot_make_stale_prices_look_fresh(self):
        tickers = [f"T{i:02d}" for i in range(45)]
        history = pd.DataFrame(
            {"Open": [99], "High": [102], "Low": [98], "Close": [100], "Volume": [1_000_000]},
            index=pd.to_datetime(["2026-08-14"]),
        )

        class Repository:
            def constituent_issuers_as_of(self, *_):
                return [{"ticker": ticker, "sector": "Test", "legal_name": ticker} for ticker in tickers]
            def completed_session_age(self, *_): return 0

        bases = {ticker: base_record(ticker=ticker, _history=history) for ticker in tickers}
        with patch("analysis.scan_v2._fetch_base", side_effect=lambda ticker, *_: bases[ticker]):
            snapshot = build_full_lq45_scan(
                Repository(), now=datetime(2026, 8, 18, 10, 30, tzinfo=timezone.utc),
                loader=lambda *_args, **_kwargs: None,
            )
        self.assertEqual(snapshot.mode, "UNAVAILABLE")
        self.assertIn("2 completed-session", snapshot.warnings[0])


class MarketHistoryPersistenceTests(unittest.TestCase):
    class Cursor:
        def __init__(self, latest):
            self.latest = latest
            self.result = []
            self.inserted = []

        def __enter__(self): return self
        def __exit__(self, *_): pass

        def execute(self, query, _params=None):
            self.result = [("BBCA", 7)] if "FROM issuers" in query else list(self.latest)

        def fetchall(self): return self.result

        def executemany(self, _query, values): self.inserted.extend(values)

    class Connection:
        def __init__(self, cursor): self._cursor = cursor
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def cursor(self): return self._cursor

    def _import(self, close, latest=()):
        history = pd.DataFrame(
            {"Open": [99], "High": [max(102, close)], "Low": [98],
             "Close": [close], "Volume": [1_000_000]},
            index=pd.to_datetime(["2026-08-14"]),
        )
        cursor = self.Cursor(latest)
        repository = SnapshotRepository(lambda: self.Connection(cursor))
        count = repository.import_yahoo_market_histories(
            {"BBCA": history}, available_at="2026-08-14T17:30:00+07:00",
        )
        return count, cursor.inserted

    def test_new_bar_starts_at_version_one(self):
        count, inserted = self._import(100)
        self.assertEqual(count, 1)
        self.assertEqual(inserted[0][2], 1)

    def test_provider_revision_creates_next_point_in_time_version(self):
        _, initial = self._import(100)
        initial_checksum = initial[0][-1]
        count, inserted = self._import(
            101, latest=[(7, date(2026, 8, 14), 1, initial_checksum)],
        )
        self.assertEqual(count, 1)
        self.assertEqual(inserted[0][2], 2)

    def test_identical_provider_bar_is_not_duplicated(self):
        _, initial = self._import(100)
        count, inserted = self._import(
            100, latest=[(7, date(2026, 8, 14), 1, initial[0][-1])],
        )
        self.assertEqual(count, 0)
        self.assertEqual(inserted, [])


if __name__ == "__main__":
    unittest.main()
