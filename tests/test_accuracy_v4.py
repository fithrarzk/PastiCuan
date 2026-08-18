from datetime import datetime, timezone
import base64
import os
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from analysis.alerts import alert_policy
from analysis.business import compute_business_scores
from analysis.factor_dataset import _ttm
from analysis.outcomes import evaluate_signal_window
from analysis.scan_snapshots import ScanResearchSnapshot, signed_scan_snapshot
from analysis.scan_v2 import planned_entry_risk_reward
from analysis.seasonality import compute_seasonality
from data.providers import ProviderResult, ProviderRouter


class FundamentalAccuracyTests(unittest.TestCase):
    def test_four_q1_reports_from_different_years_are_not_ttm(self):
        facts = []
        for year in range(2022, 2026):
            facts.append({
                "normalized_concept": "net_income", "period_start": f"{year}-01-01",
                "period_end": f"{year}-03-31", "duration_class": "QTD",
                "fiscal_year": year, "fiscal_quarter": 1, "value": 10, "scale": 0,
            })
        self.assertIsNone(_ttm(facts, {"net_income"}))

    def test_sparse_business_evidence_never_creates_score(self):
        universe = pd.DataFrame({
            "ticker": [f"T{i}" for i in range(10)], "sector": ["Industry"] * 10,
            "roe": np.linspace(.05, .20, 10),
        })
        result = compute_business_scores(universe)
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertTrue(result["scores"]["business_score"].isna().all())
        self.assertTrue((result["scores"]["business_state"] == "LIMITED_HISTORY").all())

    def test_bank_never_uses_general_company_components(self):
        count = 6
        universe = pd.DataFrame({
            "ticker": [f"B{i}" for i in range(count)], "sector": ["Banks"] * count,
            "issuer_profile": ["BANK"] * count, "annual_history_years": [5] * count,
            "roe": np.linspace(.10, .22, count), "roa": np.linspace(.01, .03, count),
            "earnings_stability": np.linspace(.20, .05, count),
            "npl_ratio": np.linspace(.04, .01, count), "credit_cost": np.linspace(.03, .01, count),
            "allowance_coverage": np.linspace(1.0, 2.0, count),
            "capital_adequacy_ratio": np.linspace(.18, .26, count),
            "equity_to_assets": np.linspace(.08, .14, count),
            "loans_to_deposits": np.linspace(.95, .75, count),
            "liquid_assets_to_deposits": np.linspace(.10, .20, count),
            "earnings_yield": np.linspace(.05, .12, count), "book_yield": np.linspace(.4, .8, count),
        })
        result = compute_business_scores(universe)["scores"]
        self.assertTrue(result["business_score"].notna().all())
        self.assertTrue((result["business_model"] == "BANK_V1_SHADOW").all())
        self.assertTrue(result["quality_score"].isna().all())

    def test_unverified_profile_is_not_scored(self):
        universe = pd.DataFrame({
            "ticker": [f"U{i}" for i in range(6)], "sector": ["Unknown"] * 6,
            "issuer_profile": ["UNVERIFIED"] * 6,
        })
        result = compute_business_scores(universe)["scores"]
        self.assertTrue(result["business_score"].isna().all())
        self.assertTrue((result["business_state"] == "PROFILE_UNVERIFIED").all())


class ExecutionAccuracyTests(unittest.TestCase):
    def test_idx_price_floor_prevents_non_executable_stop(self):
        result = planned_entry_risk_reward({
            "buy_range": {"preferred_range": {"low": 50, "high": 50}},
            "atr": 1, "resistance": 55, "current_price": 50,
        })
        self.assertEqual(result["status"], "INVALID")

    def test_signal_outcome_uses_fixed_subsequent_sessions(self):
        signal = {
            "snapshot_id": "s", "issuer_id": 1, "business_state": "QUALITY_CANDIDATE",
            "entry_state": "FAVORABLE_ENTRY", "business_score": 80,
            "prices": [{"session_date": f"2026-08-{day:02d}", "close": price}
                       for day, price in zip(range(1, 7), [100, 105, 95, 110, 108, 200])],
        }
        result = evaluate_signal_window(signal, 5)
        self.assertAlmostEqual(result["absolute_return"], .08)
        self.assertAlmostEqual(result["maximum_favorable_excursion"], .10)
        self.assertAlmostEqual(result["maximum_adverse_excursion"], -.05)
        self.assertEqual(result["evaluated_session"], "2026-08-05")


class OperationalAccuracyTests(unittest.TestCase):
    def test_provider_router_falls_back_and_opens_circuit(self):
        records = []
        calls = {"official": 0}

        def broken():
            calls["official"] += 1
            raise TimeoutError("offline")

        fallback = lambda: ProviderResult(
            data={"ok": True}, provider="fallback", source_class="yahoo_fallback",
            observed_at=datetime.now(timezone.utc),
        )
        router = ProviderRouter(failure_threshold=1, cooldown_seconds=60, record=records.append)
        providers = [("official", "official", broken), ("fallback", "yahoo_fallback", fallback)]
        self.assertEqual(router.run("prices", providers).provider, "fallback")
        self.assertEqual(router.run("prices", providers).provider, "fallback")
        self.assertEqual(calls["official"], 1)
        self.assertTrue(any(row["status"] == "CIRCUIT_OPEN" for row in records))

    def test_quiet_hours_suppress_noncritical_alerts(self):
        late = datetime(2026, 8, 18, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(alert_policy("IMPORTANT", now=late)["reason"], "QUIET_HOURS")
        self.assertTrue(alert_policy("CRITICAL", now=late)["send"])

    def test_snapshot_signature_is_verified_when_public_key_is_configured(self):
        private = Ed25519PrivateKey.generate()
        private_raw = private.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        public_raw = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        environment = {
            "SNAPSHOT_ED25519_PRIVATE_KEY": base64.b64encode(private_raw).decode(),
            "SNAPSHOT_ED25519_PUBLIC_KEY": base64.b64encode(public_raw).decode(),
        }
        with patch.dict(os.environ, environment, clear=False):
            snapshot = signed_scan_snapshot(
                snapshot_id="11111111-1111-1111-1111-111111111111",
                session_date="2026-08-18", created_at="2026-08-18T10:00:00+00:00",
                mode="DEGRADED",
            )
            snapshot.validate()
            payload = snapshot.to_dict()
            payload["signature"] = base64.b64encode(b"x" * 64).decode()
            with self.assertRaisesRegex(ValueError, "signature"):
                ScanResearchSnapshot.from_dict(payload)


class SeasonalityAccuracyTests(unittest.TestCase):
    def test_small_month_samples_do_not_claim_best_month(self):
        dates = pd.bdate_range("2022-01-03", "2026-08-18")
        history = pd.DataFrame({"Close": np.linspace(100, 180, len(dates))}, index=dates)
        result = compute_seasonality(history, minimum_observations=8)
        self.assertIsNone(result["best_month"])
        self.assertFalse(result["eligible"].any())


if __name__ == "__main__":
    unittest.main()
