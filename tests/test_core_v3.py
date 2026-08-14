import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from analysis.backtest import BrokerCostProfile
from analysis.contracts import DataQualityReport
from analysis.decision import build_decision_report
from analysis.portfolio import optimize_portfolio
from analysis.quant_backtest import assess_holdout, backtest_monthly_quant
from analysis.factor_dataset import build_factor_inputs
from analysis.snapshots import ResearchSnapshot, load_snapshot, write_snapshot
from analysis.valuation_bands import compute_valuation_bands
from operations.research_cli import approve_snapshot, build_snapshot
from data.parsers import parse_canonical_csv


class SnapshotContractTests(unittest.TestCase):
    def _inputs(self):
        rows = []
        for i in range(10):
            rows.append({
                "ticker": f"T{i}", "sector": "A" if i < 5 else "B",
                "earnings_yield": i + 1, "book_yield": i + 2,
                "dividend_yield": i / 100, "roe": i / 20,
                "roic": i / 25, "cash_conversion": 1 + i / 20,
                "leverage": 100 - i, "return_6m_skip_1m": i / 20,
                "return_12m_skip_1m": i / 10,
                "realized_volatility": 1 - i / 20,
                "downside_deviation": 1 - i / 25,
            })
        return pd.DataFrame(rows)

    def test_candidate_requires_explicit_approval_and_checksum(self):
        with TemporaryDirectory() as directory:
            inputs = Path(directory) / "inputs.csv"
            candidate = Path(directory) / "candidate.json.gz"
            approved = Path(directory) / "approved.json.gz"
            self._inputs().to_csv(inputs, index=False)
            build_snapshot(str(inputs), str(candidate), "2026-07-31T16:15:00+07:00", "factor-v1")
            with self.assertRaises(ValueError):
                load_snapshot(candidate)
            result = approve_snapshot(str(candidate), str(approved), "SHADOW", None)
            loaded = load_snapshot(approved)
            self.assertEqual(loaded.checksum, result.checksum)
            self.assertEqual(len(loaded.rankings), 10)
            payload = json.loads(__import__("gzip").decompress(approved.read_bytes()))
            payload["rankings"]["T0"]["coverage_pct"] = 0
            tampered = Path(directory) / "tampered.json"
            tampered.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                load_snapshot(tampered)

    def test_unsigned_candidate_cannot_bypass_explicit_write_flag(self):
        candidate = ResearchSnapshot(
            snapshot_id="candidate", effective_at="2026-07-31T16:15:00+07:00",
            created_at="2026-08-01T00:00:00+00:00", model_version="factor-v1",
            model_status="CANDIDATE",
        )
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "reviewed SHADOW"):
                write_snapshot(candidate, Path(directory) / "candidate.json")
            write_snapshot(candidate, Path(directory) / "candidate.json", allow_candidate=True)


class CanonicalParserTests(unittest.TestCase):
    def test_unknown_layout_is_quarantined_instead_of_guessed(self):
        with self.assertRaisesRegex(ValueError, "No reviewed parser"):
            parse_canonical_csv("idx_filing_pdf", b"%PDF")

    def test_constituent_schema_is_strict(self):
        valid = (
            b"ticker,legal_name,sector,currency,active_from,effective_from,effective_to,source_url,checksum\n"
            b"BBCA,Bank Central Asia,Financial Services,IDR,2000-01-01,2026-02-01,2026-07-31,https://idx.example/a,abc\n"
        )
        rows = parse_canonical_csv("lq45_constituents_csv", valid)
        self.assertEqual(rows[0]["ticker"], "BBCA")
        with self.assertRaisesRegex(ValueError, "missing"):
            parse_canonical_csv("lq45_constituents_csv", b"ticker\nBBCA\n")


class PointInTimeValuationTests(unittest.TestCase):
    def test_yahoo_period_labels_do_not_create_historical_bands(self):
        dates = pd.bdate_range("2024-01-01", periods=300)
        history = pd.DataFrame({"Close": np.linspace(100, 150, len(dates))}, index=dates)
        quarters = pd.date_range("2023-03-31", periods=8, freq="QE")
        income = pd.DataFrame([np.arange(8) + 10], index=["Net Income"], columns=quarters)
        result = compute_valuation_bands(history, income, pd.DataFrame(), {"sharesOutstanding": 100})
        self.assertIsNone(result["pe"])
        self.assertEqual(result["status"], "INSUFFICIENT_POINT_IN_TIME_DATA")

    def test_facts_begin_only_after_fourth_availability_date(self):
        dates = pd.bdate_range("2023-01-01", periods=650)
        history = pd.DataFrame({"Close": np.linspace(100, 180, len(dates))}, index=dates)
        quarters = pd.date_range("2022-03-31", periods=8, freq="QE")
        availability_dates = quarters + pd.offsets.Day(30)
        available = pd.Series(availability_dates, index=quarters)
        income = pd.DataFrame([np.arange(8) + 10], index=["Net Income"], columns=quarters)
        balance = pd.DataFrame([np.arange(8) + 100], index=["Stockholders Equity"], columns=quarters)
        shares = pd.DataFrame({
            "period_end": quarters, "available_at": availability_dates,
            "weighted_average_shares": 10.0, "period_end_shares": 10.0,
        })
        result = compute_valuation_bands(
            history, income, balance, {}, income_available_at=available,
            balance_available_at=available, shares_history=shares,
        )
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertGreaterEqual(result["pe"]["dates"].min(), available.iloc[3])


class ValidationAuthorityTests(unittest.TestCase):
    def test_environment_cannot_enable_action_policy(self):
        with patch.dict(os.environ, {"MODEL_VALIDATED": "true", "SHADOW_COMPLETED_SESSIONS": "999"}):
            report = build_decision_report(
                {"technical_score": 90, "risk_reward": 3, "entry_zone": (1, 2)},
                {"fundamental_score": 90, "authoritative_source": True},
                backtest={"costs_configured": True, "research_only": False,
                          "summary": {"total_trades": 40, "sample_sessions": 1300,
                                      "profit_factor": 1.5, "expectancy": 1, "win_rate": 60}},
                liquidity={"avg_value": 50_000_000_000},
                data_quality=DataQualityReport("A", 100, True, False),
                model_validated=True, shadow_sessions=100,
            )
        self.assertEqual(report["final_verdict"], "RESEARCH_ONLY")
        self.assertFalse(next(g for g in report["gates"] if g["name"] == "action_policy")["passed"])


class QuantValidationTests(unittest.TestCase):
    def _panel(self):
        rebalance = pd.date_range("2023-01-31", periods=30, freq="ME")
        score_rows = []
        business = pd.bdate_range("2023-01-01", "2025-08-15")
        bar_rows = []
        for i in range(10):
            ticker = f"T{i}"
            for date in rebalance:
                score_rows.append({"rebalance_date": date, "ticker": ticker,
                                   "composite_percentile": (i + 1) * 10})
            growth = 0.00005 + i * 0.00002
            for n, date in enumerate(business):
                bar_rows.append({"date": date, "ticker": ticker, "open": 100 * np.exp(growth * n)})
        return pd.DataFrame(score_rows), pd.DataFrame(bar_rows)

    def test_monthly_quant_executes_after_rank_and_measures_edge(self):
        scores, bars = self._panel()
        costs = BrokerCostProfile("test", .0001, .0001, 0, 0, 0)
        result = backtest_monthly_quant(scores, bars, broker_costs=costs)
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertGreater(result["net_excess_cagr"], 0)
        self.assertGreater(result["average_rank_ic"], 0)
        self.assertTrue((result["observations"]["entry_date"] > result["observations"]["rebalance_date"]).all())

    def test_acceptance_requires_every_frozen_gate(self):
        passed = assess_holdout(
            {"net_excess_cagr": .03, "average_rank_ic": .05, "information_ratio": .4},
            usable_years=6, holdout_months=24, higher_cost_positive=True,
            delayed_entry_positive=True, deterministic_rebuild=True,
        )
        self.assertTrue(passed["passed"])
        passed["checks"]["holdout_months"] = False
        failed = assess_holdout(
            {"net_excess_cagr": .03, "average_rank_ic": .05, "information_ratio": .2},
            usable_years=6, holdout_months=24, higher_cost_positive=True,
            delayed_entry_positive=True, deterministic_rebuild=True,
        )
        self.assertFalse(failed["passed"])


class FactorDatasetTests(unittest.TestCase):
    def test_point_in_time_repository_builds_raw_factor_inputs(self):
        periods = pd.date_range("2025-03-31", periods=4, freq="QE")
        facts = []
        for period in periods:
            start = period - pd.offsets.Day(89)
            for concept, value in (("net_income", 10), ("operating_cash_flow", 12)):
                facts.append({"normalized_concept": concept, "period_start": start.date(),
                              "period_end": period.date(), "value": value, "scale": 0})
        facts.extend([
            {"normalized_concept": "stockholders_equity", "period_start": None,
             "period_end": periods[-1].date(), "value": 100, "scale": 0},
            {"normalized_concept": "total_debt", "period_start": None,
             "period_end": periods[-1].date(), "value": 20, "scale": 0},
        ])
        bars = [{"session_date": date.date(), "close": 2 + i / 100}
                for i, date in enumerate(pd.bdate_range("2024-01-01", periods=300))]

        class Repository:
            def constituent_issuers_as_of(self, *_):
                return [{"id": 1, "ticker": "TEST", "sector": "Industrials"}]
            def facts_as_of(self, *_): return facts
            def market_bars_as_of(self, *_): return bars
            def corporate_actions_as_of(self, *_):
                return [
                    {"action_type": "DIVIDEND", "ex_date": "2025-08-01", "cash_amount": 1},
                    {"action_type": "DIVIDEND", "ex_date": "2026-02-01", "cash_amount": 100},
                ]
            def shares_as_of(self, *_): return {"period_end_shares": 10}

        result = build_factor_inputs(Repository(), "2026-01-31T16:15:00+07:00")
        self.assertEqual(result.iloc[0]["ticker"], "TEST")
        self.assertAlmostEqual(result.iloc[0]["cash_conversion"], 1.2)
        self.assertAlmostEqual(result.iloc[0]["leverage"], .2)
        self.assertAlmostEqual(result.iloc[0]["dividend_yield"], 1 / bars[-1]["close"])
        self.assertIsNotNone(result.iloc[0]["return_6m_skip_1m"])


class PortfolioSemanticsTests(unittest.TestCase):
    def test_max_sharpe_is_unavailable_without_policy_rate(self):
        dates = pd.bdate_range("2025-01-01", periods=100)
        columns = pd.MultiIndex.from_product([["Adj Close"], ["A.JK", "B.JK", "C.JK"]])
        prices = pd.DataFrame(np.linspace(100, 120, 300).reshape(100, 3), index=dates, columns=columns)
        with patch("analysis.portfolio.yf.download", return_value=prices):
            result = optimize_portfolio(["A", "B", "C"], risk_free_rate=None)
        self.assertEqual(result["max_sharpe"]["status"], "UNAVAILABLE_WITHOUT_POLICY_RATE")
        self.assertEqual(result["max_sharpe"]["weights"], {})


if __name__ == "__main__":
    unittest.main()
