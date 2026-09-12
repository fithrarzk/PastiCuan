import io
import json
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import pandas as pd

from analysis.snapshots import ResearchSnapshot
from operations.readiness_diagnostics import concept_diagnostics
from operations.research_cli import build_snapshot, candidate_readiness, main
from storage.repository import SnapshotRepository


def candidate(rankings, constituents=None):
    base = ResearchSnapshot(
        snapshot_id="candidate-readiness",
        effective_at="2026-08-16T00:00:00+00:00",
        created_at="2026-08-16T00:00:00+00:00",
        model_version="lq45-factor-v2-shadow",
        model_status="CANDIDATE",
        formula_version="lq45-cross-section-v4+business-quality-v2",
        constituents=constituents or sorted(rankings),
        rankings=rankings,
    )
    return ResearchSnapshot(
        **{**base.unsigned_dict(), "checksum": base.calculated_checksum()}
    )


class ConceptDiagnosticsTests(unittest.TestCase):
    def test_repository_query_fences_profile_filing_and_fact_at_same_cutoff(self):
        class Column:
            def __init__(self, name):
                self.name = name

        class Cursor:
            description = [
                Column(name)
                for name in (
                    "ticker",
                    "issuer_profile",
                    "profile_source_url",
                    "profile_checksum",
                    "available_concepts",
                    "financial_periods",
                    "source_urls",
                    "source_documents",
                    "annual_history_years",
                )
            ]

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def execute(self, sql, parameters):
                self.sql = sql
                self.parameters = parameters

            def fetchall(self):
                return [("AAAA", None, None, None, [], [], [], [], 0)]

        cursor = Cursor()

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def cursor(self):
                return cursor

        cutoff = "2026-01-01T00:00:00Z"
        result = SnapshotRepository(Connection).readiness_evidence_as_of(
            "LQ45", "2026-01-01", cutoff
        )
        self.assertIn("i.profile_verified_at <= %s", cursor.sql)
        self.assertIn("f.available_at<=%s", cursor.sql)
        self.assertIn("sf.available_at<=%s", cursor.sql)
        self.assertEqual(cursor.parameters[:5], (cutoff,) * 5)
        self.assertEqual(result[0]["issuer_profile"], None)

    def test_profile_specific_missing_groups_are_exact_and_sorted(self):
        general = concept_diagnostics(
            [
                "net_income_common_stockholders",
                "stockholders_equity",
                "total_assets",
            ],
            "GENERAL",
        )
        self.assertEqual(general["status"], "AVAILABLE")
        self.assertEqual(
            general["missing_concepts"],
            ["basic_eps", "cash", "debt", "operating_cash_flow"],
        )
        bank = concept_diagnostics(["net_income"], "BANK")
        self.assertEqual(
            bank["missing_concepts"],
            [
                "assets",
                "basic_eps",
                "capital_adequacy_ratio",
                "cash",
                "credit_impairment",
                "deposits",
                "equity",
                "impaired_loans",
                "loan_allowance",
                "loans",
            ],
        )

    def test_unverified_profile_never_guesses_an_accounting_model(self):
        result = concept_diagnostics([], "UNVERIFIED")
        self.assertEqual(
            result, {"status": "PROFILE_UNVERIFIED", "missing_concepts": []}
        )


class CandidateDiagnosticTests(unittest.TestCase):
    def test_malformed_evidence_fields_fail_closed_without_echoing_values(self):
        snapshot = candidate(
            {
                "AAAA": {
                    "issuer_profile": "GENERAL",
                    "issuer_profile_checksum": "not-a-checksum",
                    "issuer_profile_source": "raw provider body",
                    "missing_concepts": "not-a-list",
                    "financial_periods": {"unexpected": "shape"},
                    "source_urls": ["raw provider body"],
                    "source_documents": ["not-a-checksum"],
                    "concept_diagnostic_status": "UNKNOWN_PROVIDER_VALUE",
                }
            }
        )
        issuer = candidate_readiness(snapshot)["issuers"][0]
        self.assertEqual(
            issuer["diagnostic_errors"],
            ["checksums", "financial_periods", "missing_concepts", "sources"],
        )
        self.assertEqual(issuer["concept_diagnostic_status"], "UNAVAILABLE")
        self.assertEqual(issuer["sources"], [])
        self.assertEqual(issuer["checksums"], {"issuer_profile": None, "documents": []})
        self.assertNotIn("raw provider body", json.dumps(issuer))

    def test_candidate_carries_point_in_time_concept_diagnostics(self):
        with TemporaryDirectory() as root:
            input_path = Path(root) / "inputs.csv"
            output_path = Path(root) / "candidate.json"
            pd.DataFrame(
                [
                    {
                        "ticker": "AAAA",
                        "sector": "Test",
                        "concept_diagnostic_status": "AVAILABLE",
                        "missing_concepts": '["cash", "debt"]',
                    }
                ]
            ).to_csv(input_path, index=False)
            quant = {
                "status": "AVAILABLE",
                "scores": pd.DataFrame(
                    [{"ticker": "AAAA", "composite_percentile": 50}]
                ),
                "warnings": [],
            }
            business = {
                "status": "AVAILABLE",
                "scores": pd.DataFrame([{"ticker": "AAAA", "business_score": None}]),
            }
            with (
                patch(
                    "operations.research_cli.compute_cross_sectional_factors",
                    return_value=quant,
                ),
                patch(
                    "operations.research_cli.compute_business_scores",
                    return_value=business,
                ),
            ):
                snapshot = build_snapshot(
                    str(input_path),
                    str(output_path),
                    "2026-08-16T00:00:00+00:00",
                    "test",
                    readiness_evidence=[
                        {
                            "ticker": "AAAA",
                            "issuer_profile": "GENERAL",
                            "available_concepts": [
                                "net_income",
                                "operating_cash_flow",
                                "basic_earnings_per_share",
                                "stockholders_equity",
                                "total_assets",
                            ],
                            "financial_periods": ["2025-12-31"],
                        }
                    ],
                )
        self.assertEqual(
            snapshot.rankings["AAAA"]["missing_concepts"], ["cash", "debt"]
        )
        self.assertEqual(
            snapshot.rankings["AAAA"]["concept_diagnostic_status"], "AVAILABLE"
        )

    def test_readiness_lists_exact_blockers_and_bounded_redacted_evidence(self):
        snapshot = candidate(
            {
                "AAAA": {
                    "composite_percentile": 50,
                    "factor_coverage_pct": 75,
                    "raw_component_coverage_pct": 70,
                    "issuer_profile": "GENERAL",
                    "issuer_profile_checksum": "a" * 64,
                    "business_score": 70,
                    "annual_history_years": 5,
                    "financial_periods": '["2025-12-31"]',
                    "source_urls": '["https://www.idx.co.id/a.zip"]',
                    "source_documents": f'["{"b" * 64}"]',
                    "missing_concepts": "[]",
                    "concept_diagnostic_status": "AVAILABLE",
                    "provider_body": "must not appear",
                },
                "BBBB": {
                    "composite_percentile": None,
                    "factor_coverage_pct": 50,
                    "raw_component_coverage_pct": 60,
                    "issuer_profile": "UNVERIFIED",
                    "issuer_profile_checksum": None,
                    "business_score": None,
                    "annual_history_years": 1,
                    "financial_periods": [],
                    "source_urls": [],
                    "source_documents": [],
                    "missing_concepts": [],
                    "concept_diagnostic_status": "PROFILE_UNVERIFIED",
                },
            },
            constituents=["BBBB", "CCCC", "AAAA"],
        )
        result = candidate_readiness(snapshot)
        self.assertEqual(result["unverified_tickers"], ["BBBB", "CCCC"])
        self.assertEqual(result["business_unscored_tickers"], ["BBBB", "CCCC"])
        self.assertEqual(result["quant_ineligible_tickers"], ["BBBB", "CCCC"])
        self.assertEqual(
            [row["ticker"] for row in result["issuers"]], ["AAAA", "BBBB", "CCCC"]
        )
        aaaa = result["issuers"][0]
        self.assertEqual(aaaa["sources"], ["https://www.idx.co.id/a.zip"])
        self.assertEqual(aaaa["checksums"]["documents"], ["b" * 64])
        self.assertEqual(aaaa["history"]["missing_annual_years"], 0)
        self.assertNotIn("must not appear", json.dumps(result))
        cccc = result["issuers"][2]
        self.assertFalse(cccc["gates"]["ranking_present"])
        self.assertEqual(cccc["concept_diagnostic_status"], "RANKING_MISSING")

    def test_inspection_cli_prints_rejected_diagnostics_without_weakening_check(self):
        snapshot = candidate({}, constituents=["MISS"])
        with TemporaryDirectory() as root:
            path = Path(root) / "candidate.json"
            path.write_text(json.dumps(snapshot.to_dict()))
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = main(["inspect-candidate-readiness", "--snapshot", str(path)])
            report = json.loads(stream.getvalue())
            self.assertEqual(code, 2)
            self.assertFalse(report["ready"])
            self.assertEqual(report["quant_ineligible_tickers"], ["MISS"])
            with self.assertRaises(ValueError):
                from operations.research_cli import check_candidate

                check_candidate(str(path))


@unittest.skipUnless(
    os.getenv("PASTICUAN_TEST_DATABASE_URL"), "disposable PostgreSQL required"
)
class ReadinessPointInTimeIntegrationTests(unittest.TestCase):
    def test_later_profile_and_fact_are_invisible_before_available_at(self):
        import psycopg

        database_url = os.environ["PASTICUAN_TEST_DATABASE_URL"]
        repository = SnapshotRepository(lambda: psycopg.connect(database_url))
        ticker = "O" + uuid4().hex[:7].upper()
        index_code = "O" + uuid4().hex[:7].upper()
        checksum = uuid4().hex * 2
        source_url = f"https://www.idx.co.id/{ticker}.zip"
        with psycopg.connect(database_url) as connection:
            issuer_id = connection.execute(
                """INSERT INTO issuers(ticker,legal_name,sector,issuer_type,currency,active_from,
                                        profile_verified_at,profile_source_url,profile_checksum)
                   VALUES (%s,%s,'Industrials','general','IDR','2025-01-01',
                           '2026-02-01T00:00:00Z',%s,%s) RETURNING id""",
                (ticker, ticker, source_url, checksum),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO index_constituents
                       (index_code,issuer_id,effective_from,effective_to,source_url,checksum)
                   VALUES (%s,%s,'2025-01-01','2026-12-31',%s,%s)""",
                (index_code, issuer_id, source_url, checksum),
            )
            filing_id = connection.execute(
                """INSERT INTO filings
                       (issuer_id,filing_type,period_end,published_at,available_at,consolidated,
                        audit_status,restatement_version,source_url,object_key,document_checksum)
                   VALUES (%s,'ANNUAL','2025-12-31','2026-01-31T00:00:00Z',
                           '2026-02-01T00:00:00Z',true,'AUDITED',1,%s,%s,%s)
                   RETURNING id""",
                (issuer_id, source_url, checksum, checksum),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO statement_facts
                       (filing_id,taxonomy,concept,normalized_concept,period_start,period_end,
                        published_at,available_at,value,currency,scale,unit,consolidated,
                        audit_status,source_url,document_checksum,restatement_version,
                        period_type,duration_class,fiscal_year,fiscal_quarter)
                   VALUES (%s,'IDX','Profit','net_income','2025-01-01','2025-12-31',
                           '2026-01-31T00:00:00Z','2026-02-01T00:00:00Z',1,'IDR',0,'IDR',
                           true,'AUDITED',%s,%s,1,'DURATION','FY',2025,4)""",
                (filing_id, source_url, checksum),
            )
        early = repository.readiness_evidence_as_of(
            index_code, "2026-01-15", "2026-01-15T00:00:00Z"
        )[0]
        late = repository.readiness_evidence_as_of(
            index_code, "2026-03-01", "2026-03-01T00:00:00Z"
        )[0]
        self.assertIsNone(early["issuer_profile"])
        self.assertEqual(early["available_concepts"], [])
        self.assertEqual(late["issuer_profile"], "GENERAL")
        self.assertEqual(late["available_concepts"], ["net_income"])
        self.assertEqual(late["source_documents"], [checksum])
        self.assertEqual(late["annual_history_years"], 1)


if __name__ == "__main__":
    unittest.main()
