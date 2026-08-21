"""Offline characterization of the supported yfinance public seams."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import yfinance
from packaging.requirements import Requirement

from analysis.portfolio import optimize_portfolio
from data.extended import get_extended_data


class _Ticker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.history_calls: list[dict] = []

    def history(self, **kwargs):
        self.history_calls.append(kwargs)
        return pd.DataFrame(
            {"Close": [100.0, 101.0]}, index=pd.date_range("2026-01-01", periods=2)
        )

    @property
    def info(self):
        return {"longName": "Example", "currency": "IDR", "financialCurrency": "IDR"}

    @property
    def quarterly_income_stmt(self):
        return pd.DataFrame({"2026Q1": [1.0]}, index=["Net Income"])

    @property
    def quarterly_balance_sheet(self):
        return pd.DataFrame({"2026Q1": [2.0]}, index=["Assets"])

    @property
    def quarterly_cash_flow(self):
        return pd.DataFrame({"2026Q1": [3.0]}, index=["Operating Cash Flow"])


class YfinanceCompatibilityTests(unittest.TestCase):
    def test_supported_runtime_pins_are_consistent(self):
        expected = {
            "yfinance": "1.5.2",
            "curl-cffi": "0.16.1",
            "cryptography": "50.0.0",
        }
        for filename in ("requirements.txt", "requirements-bot.txt"):
            requirements = Path(filename).read_text()
            for package, version in expected.items():
                self.assertIn(f"{package}=={version}", requirements)

    def test_installed_public_surface_and_curl_metadata_are_compatible(self):
        self.assertTrue(callable(yfinance.Ticker))
        self.assertTrue(callable(yfinance.download))
        for attribute in (
            "history",
            "info",
            "quarterly_income_stmt",
            "quarterly_balance_sheet",
            "quarterly_cash_flow",
        ):
            self.assertTrue(hasattr(yfinance.Ticker, attribute), attribute)
        metadata = __import__("importlib.metadata", fromlist=["metadata"]).metadata(
            "yfinance"
        )
        curl_requirements = [
            Requirement(raw)
            for raw in metadata.get_all("Requires-Dist", [])
            if Requirement(raw).name.lower().replace("_", "-") == "curl-cffi"
        ]
        if yfinance.__version__ != "1.5.2":
            self.skipTest(
                f"dependency environment has yfinance {yfinance.__version__}; pin check runs on supported environment"
            )
        self.assertTrue(curl_requirements)
        self.assertTrue(
            any(req.specifier.contains("0.16.1") for req in curl_requirements)
        )

    def test_ticker_public_interfaces_are_available_offline(self):
        ticker = _Ticker("BBCA.JK")
        with patch("data.extended.yf.Ticker", return_value=ticker) as constructor:
            result = get_extended_data("BBCA", include_fundamentals=True)

        constructor.assert_called_once_with("BBCA.JK")
        self.assertFalse(result["history"].empty)
        self.assertEqual(result["info"]["longName"], "Example")
        self.assertFalse(result["quarterly_income"].empty)
        self.assertFalse(result["quarterly_balance"].empty)
        self.assertFalse(result["quarterly_cashflow"].empty)
        self.assertEqual(ticker.history_calls[0]["auto_adjust"], False)

    def test_price_only_path_does_not_request_info(self):
        class PriceOnlyTicker(_Ticker):
            @property
            def info(self):
                raise AssertionError("price-only path must not request info")

        ticker = PriceOnlyTicker("BBCA.JK")
        with patch("data.extended.yf.Ticker", return_value=ticker):
            result = get_extended_data("BBCA", include_fundamentals=False)
        self.assertIsNone(result["error"])
        self.assertTrue(result["info"] == {})

    def test_download_public_interface_is_used_for_uninjected_history(self):
        dates = pd.date_range("2024-01-01", periods=2, freq="B")
        prices = pd.DataFrame(
            {
                "BBCA.JK": np.linspace(100, 150, len(dates)),
                "BMRI.JK": np.linspace(80, 120, len(dates)),
            },
            index=dates,
        )
        with patch("analysis.portfolio.yf.download", return_value=prices) as download:
            result = optimize_portfolio(["BBCA", "BMRI"], risk_free_rate=0.0)

        download.assert_called_once_with(
            ["BBCA.JK", "BMRI.JK"],
            period="3y",
            progress=False,
            auto_adjust=False,
            actions=True,
        )
        self.assertIn("504 overlapping completed sessions", result["error"])


if __name__ == "__main__":
    unittest.main()
