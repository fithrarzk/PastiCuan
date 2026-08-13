import unittest
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from analysis.backtest import BrokerCostProfile, backtest_technical_strategy
from analysis.buy_range import build_buy_range
from analysis.ai import generate_ai_analysis
from analysis.contracts import DataQualityReport
from analysis.decision import build_decision_report
from analysis.fundamental import analyze_fundamental
from analysis.financials import growth, ttm, valuation_multiple, ytd_to_discrete
from analysis.presentation import decision_view
from analysis.portfolio import allocate_lots
from analysis.quant import compute_cross_sectional_factors
from analysis.technical import _atr, _rsi
from data.validation import completed_eod_history, split_adjusted_ohlcv, validate_ohlcv


def history(length=320, start=1000.0):
    index = pd.bdate_range("2024-01-02", periods=length)
    close = pd.Series(start * np.exp(np.arange(length) * 0.001), index=index)
    return pd.DataFrame({"Open": close * .999, "High": close * 1.01,
                         "Low": close * .99, "Close": close,
                         "Volume": 2_000_000.0}, index=index)


class IndicatorGoldenTests(unittest.TestCase):
    def test_wilder_rsi_zero_loss_and_flat(self):
        rising = pd.Series(range(1, 31), dtype=float)
        flat = pd.Series([10.0] * 30)
        self.assertEqual(_rsi(rising, 14).iloc[-1], 100.0)
        self.assertEqual(_rsi(flat, 14).iloc[-1], 50.0)

    def test_wilder_atr_constant_range(self):
        close = pd.Series([100.0] * 30)
        result = _atr(close + 2, close - 2, close, 14)
        self.assertAlmostEqual(result.iloc[-1], 4.0, places=10)


class QualityAndFundamentalTests(unittest.TestCase):
    def test_invalid_range_is_quarantined(self):
        df = history(20)
        df.iloc[-1, df.columns.get_loc("High")] = 1
        report = validate_ohlcv(df, datetime(2024, 2, 1, 17, tzinfo=ZoneInfo("Asia/Jakarta")))
        self.assertTrue(report.quarantined)
        self.assertIn("INVALID_OHLC_RANGE", {issue.code for issue in report.issues})

    def test_incomplete_current_candle_excluded(self):
        df = history(3)
        df.index = pd.to_datetime(["2026-08-12", "2026-08-13", "2026-08-14"])
        result = completed_eod_history(df, datetime(2026, 8, 14, 15, tzinfo=ZoneInfo("Asia/Jakarta")))
        self.assertEqual(len(result), 2)

    def test_split_adjustment_does_not_include_dividends(self):
        df = history(4)
        df["Stock Splits"] = [0, 0, 2, 0]
        df["Dividends"] = [0, 5, 0, 0]
        adjusted = split_adjusted_ohlcv(df)
        self.assertAlmostEqual(adjusted["Close"].iloc[0], df["Close"].iloc[0] / 2)
        self.assertAlmostEqual(adjusted["Close"].iloc[2], df["Close"].iloc[2])

    def test_negative_multiples_not_meaningful(self):
        result = analyze_fundamental({"trailingPE": -5, "priceToBook": -1}, "Industrials")
        self.assertEqual(result["pe_status"], "NOT_MEANINGFUL")
        self.assertEqual(result["pbv_status"], "NOT_MEANINGFUL")
        self.assertNotIn("Undervalued", result["overall"])

    def test_ttm_requires_four_discrete_quarters(self):
        from decimal import Decimal
        self.assertEqual(ytd_to_discrete(Decimal(30), Decimal(18)), Decimal(12))
        self.assertEqual(ttm([Decimal(1), Decimal(2), Decimal(3), Decimal(4)]), Decimal(10))
        self.assertIsNone(ttm([Decimal(1), None, Decimal(3), Decimal(4)]))

    def test_transition_and_negative_valuation_are_explicit(self):
        from decimal import Decimal
        self.assertEqual(growth(Decimal(5), Decimal(-2)).status, "LOSS_TO_PROFIT")
        self.assertEqual(valuation_multiple(Decimal(100), Decimal(-4))[0], "NOT_MEANINGFUL")


class CausalityAndGateTests(unittest.TestCase):
    def test_buy_range_is_only_the_overlap_and_remains_research(self):
        index = pd.bdate_range("2025-01-01", periods=2)
        bands = {
            "pe": {"band_m1": pd.Series([80, 90], index=index),
                   "band_mean": pd.Series([120, 130], index=index)},
            "pbv": {"band_m1": pd.Series([100, 110], index=index),
                    "band_mean": pd.Series([140, 150], index=index)},
        }
        result = build_buy_range(
            {"current_price": 130, "support": 100, "atr": 25,
             "stop_loss": 90, "take_profit": 150, "risk_reward": 2,
             "technical_score": 70, "rsi": 55},
            {"pe_status": "AVAILABLE", "pbv_status": "AVAILABLE",
             "source": "Yahoo fallback", "authoritative_source": False},
            bands, data_usable=True,
        )
        self.assertEqual(result["technical_range"], {"low": 100.0, "high": 120.0})
        self.assertEqual(result["valuation_reference_range"], {"low": 100.0, "high": 140.0})
        self.assertEqual(result["preferred_range"], {"low": 100.0, "high": 120.0})
        self.assertEqual(result["policy_label"], "RESEARCH_ONLY")
        self.assertFalse(result["authoritative_fundamentals"])

    def test_buy_range_does_not_invent_non_overlapping_range(self):
        index = pd.bdate_range("2025-01-01", periods=1)
        result = build_buy_range(
            {"current_price": 120, "support": 100, "atr": 10},
            {"pe_status": "AVAILABLE", "pbv_status": "INSUFFICIENT_DATA",
             "authoritative_source": True},
            {"pe": {"band_m1": pd.Series([150], index=index),
                    "band_mean": pd.Series([180], index=index)}},
            data_usable=True,
        )
        self.assertEqual(result["status"], "NO_OVERLAP")
        self.assertIsNone(result["preferred_range"])

    def test_signal_executes_after_signal_date(self):
        df = history()
        costs = BrokerCostProfile("test", .001, .002, .001, .0005, 2)
        result = backtest_technical_strategy(df, broker_costs=costs)
        trades = result["trades"]
        if not trades.empty:
            self.assertTrue((trades["Entry Date"] > trades["Signal Date"]).all())
        self.assertEqual(result["signal_stats"]["execution"], "signal close -> next tradable open")

    def test_gates_override_high_scores(self):
        quality = DataQualityReport("A", 100, True, False)
        decision = build_decision_report(
            {"technical_score": 99, "risk_reward": 3, "entry_zone": (1, 2)},
            {"fundamental_score": 99, "authoritative_source": False},
            backtest={"costs_configured": False, "research_only": True},
            liquidity={"avg_value": 99_000_000_000}, data_quality=quality,
        )
        self.assertEqual(decision["final_verdict"], "RESEARCH_ONLY")
        self.assertIsNone(decision["action"])

    def test_shared_presentation_contract(self):
        decision = {"final_score": 61, "final_verdict": "RESEARCH_ONLY",
                    "coverage_pct": 80, "decision_components": {"technical": 61},
                    "warnings": ["gate"]}
        streamlit_values = decision_view(decision)
        telegram_values = decision_view(decision)
        self.assertEqual(streamlit_values, telegram_values)

    def test_narrative_cannot_create_action_label(self):
        text = generate_ai_analysis(
            {"decision_label": "RESEARCH_ONLY", "overall": "Peer valuation unavailable"},
            {"technical_score": 99, "confidence": 99, "entry_zone": ("Rp 1", "Rp 2")},
            "TEST.JK",
        )
        self.assertIn("POLICY LABEL: RESEARCH_ONLY", text)
        self.assertNotIn("FINAL VERDICT: BUY", text)

    def test_telegram_credentials_are_redacted_from_logs(self):
        import bot
        original_token = bot.TELEGRAM_BOT_TOKEN
        try:
            bot.TELEGRAM_BOT_TOKEN = "secret-token-for-test"
            record = logging.LogRecord("httpx", logging.INFO, __file__, 1,
                                       "POST https://api.telegram.org/bot%s/getMe",
                                       (bot.TELEGRAM_BOT_TOKEN,), None)
            bot._SecretRedactionFilter().filter(record)
            self.assertNotIn("secret-token-for-test", record.getMessage())
            self.assertIn("<redacted>", record.getMessage())
        finally:
            bot.TELEGRAM_BOT_TOKEN = original_token


class CrossSectionTests(unittest.TestCase):
    def test_sector_factor_is_relative_and_deterministic(self):
        rows = []
        for sector in ("Bank", "Energy"):
            for i in range(6):
                rows.append({"ticker": f"{sector[0]}{i}", "sector": sector,
                             "earnings_yield": i + 1, "realized_volatility": 30 - i})
        first = compute_cross_sectional_factors(pd.DataFrame(rows))
        second = compute_cross_sectional_factors(pd.DataFrame(rows))
        pd.testing.assert_frame_equal(first["scores"], second["scores"])
        self.assertTrue(first["scores"]["value"].between(0, 100).all())

    def test_lot_allocation_never_overspends(self):
        result = allocate_lots({"A": .7, "B": .3}, {"A": 1250, "B": 4300}, 10_000_000)
        self.assertGreaterEqual(result["cash_remaining"], 0)
        self.assertLessEqual(result["invested"], 10_000_000)
        self.assertTrue(all(row["shares"] % 100 == 0 for row in result["allocations"].values()))


if __name__ == "__main__":
    unittest.main()
