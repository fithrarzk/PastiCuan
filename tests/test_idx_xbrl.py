import io
import unittest
from zipfile import ZipFile

from analysis.factor_dataset import _ttm
from analysis.snapshots import ResearchSnapshot
from data.idx_xbrl import parse_idx_xbrl, validate_official_idx_url
from data.idx_reports import discover_idx_xbrl_manifest
from operations.research_cli import candidate_readiness


def _instance() -> bytes:
    return b'''<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:idx="http://www.idx.co.id/xbrl/taxonomy/2020-01-01/cor"
 xmlns:dei="http://www.idx.co.id/xbrl/taxonomy/2020-01-01/dei"
 xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
 <xbrli:context id="FY"><xbrli:entity><xbrli:identifier scheme="idx">TEST</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="Q1"><xbrli:entity><xbrli:identifier scheme="idx">TEST</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="Q1P"><xbrli:entity><xbrli:identifier scheme="idx">TEST</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-03-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="DIM"><xbrli:entity><xbrli:identifier scheme="idx">TEST</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="idx:X">idx:Y</xbrldi:explicitMember></xbrli:scenario></xbrli:context>
 <xbrli:unit id="IDR"><xbrli:measure>iso4217:IDR</xbrli:measure></xbrli:unit>
 <xbrli:unit id="EPS"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:IDR</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
 <dei:EntityCode contextRef="Q1">TEST</dei:EntityCode>
 <dei:Sector contextRef="Q1">Consumer non-cyclicals</dei:Sector>
 <idx:ProfitLossAttributableToParentEntity contextRef="FY" unitRef="IDR">1000</idx:ProfitLossAttributableToParentEntity>
 <idx:ProfitLossAttributableToParentEntity contextRef="Q1" unitRef="IDR">300</idx:ProfitLossAttributableToParentEntity>
 <idx:ProfitLossAttributableToParentEntity contextRef="Q1P" unitRef="IDR">200</idx:ProfitLossAttributableToParentEntity>
 <idx:ProfitLoss contextRef="Q1" unitRef="IDR">999</idx:ProfitLoss>
 <idx:BasicEarningsLossPerShareFromContinuingOperations contextRef="FY" unitRef="EPS">10</idx:BasicEarningsLossPerShareFromContinuingOperations>
 <idx:BasicEarningsLossPerShareFromContinuingOperations contextRef="Q1" unitRef="EPS">3</idx:BasicEarningsLossPerShareFromContinuingOperations>
 <idx:BasicEarningsLossPerShareFromContinuingOperations contextRef="Q1P" unitRef="EPS">2</idx:BasicEarningsLossPerShareFromContinuingOperations>
 <idx:TotalEquity contextRef="Q1" unitRef="IDR">5000</idx:TotalEquity>
 <idx:TotalEquity contextRef="DIM" unitRef="IDR">123</idx:TotalEquity>
</xbrli:xbrl>'''


class IdxXbrlTests(unittest.TestCase):
    def _parse(self, body):
        return parse_idx_xbrl(
            body, ticker="TEST", source_url="https://www.idx.co.id/static/test-instance.zip",
            published_at="2026-04-30T09:00:00+07:00", filing_type="Q1",
            filing_period_end="2026-03-31", document_checksum="a" * 64,
            object_key="sources/idx/a.zip",
        )

    def test_parses_reviewed_concepts_and_excludes_dimensions(self):
        result = self._parse(_instance())
        self.assertEqual(result["diagnostics"]["entity_code"], "TEST")
        q1_income = [row for row in result["facts"] if row["normalized_concept"] == "net_income"
                     and row["period_end"] == "2026-03-31"]
        self.assertEqual(len(q1_income), 1)
        self.assertEqual(q1_income[0]["value"], "300")
        equities = [row for row in result["facts"] if row["normalized_concept"] == "stockholders_equity"]
        self.assertEqual([row["value"] for row in equities], ["5000"])

    def test_accepts_small_instance_zip(self):
        stream = io.BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("TEST-2026-03-31.xbrl", _instance())
        self.assertGreater(self._parse(stream.getvalue())["diagnostics"]["fact_count"], 0)

    def test_rejects_non_official_host_and_ticker_mismatch(self):
        with self.assertRaises(ValueError):
            validate_official_idx_url("https://example.com/filing.zip")
        with self.assertRaisesRegex(ValueError, "does not match"):
            parse_idx_xbrl(
                _instance(), ticker="OTHER", source_url="https://idx.co.id/file.xml",
                published_at="2026-04-30T09:00:00+07:00", filing_type="Q1",
                filing_period_end="2026-03-31", document_checksum="b" * 64,
                object_key="sources/idx/b.xml",
            )

    def test_ttm_supports_idx_cumulative_interims(self):
        parsed = self._parse(_instance())
        self.assertEqual(_ttm(parsed["facts"], {"net_income"}), 1100.0)
        self.assertEqual(_ttm(parsed["facts"], {"basic_earnings_per_share"}), 11.0)


class IdxDiscoveryTests(unittest.TestCase):
    def test_discovery_selects_non_inline_official_instance(self):
        def fetch(year, period):
            modified = "2026-07-30T12:00:00" if period == "tw2" else "/Date(1767139200000)/"
            return [{
                "KodeEmiten": "TEST", "File_Modified": modified,
                "Attachments": [
                    {"File_Name": "inlineXBRL.zip", "File_Path": "/files/inlineXBRL.zip"},
                    {"File_Name": "instance.zip", "File_Path": "/files/instance.zip"},
                ],
            }, {"KodeEmiten": "OTHER", "File_Modified": modified, "Attachments": []}]

        result = discover_idx_xbrl_manifest(["TEST"], year=2026, period="tw2", fetch_catalog=fetch)
        self.assertEqual(len(result["filings"]), 2)
        current = [row for row in result["filings"] if row["filing_type"] == "Q2"][0]
        self.assertEqual(current["period_end"], "2026-06-30")
        self.assertEqual(current["source_url"], "https://www.idx.co.id/files/instance.zip")
        self.assertTrue(current["published_at"].endswith("+07:00"))
        self.assertEqual(result["discovery"]["current_period_missing"], [])


class CandidateReadinessTests(unittest.TestCase):
    def test_requires_45_members_and_90_percent_coverage(self):
        tickers = [f"T{index:02d}" for index in range(45)]
        rankings = {ticker: {"composite_percentile": 50, "coverage_pct": 75}
                    for ticker in tickers}
        base = ResearchSnapshot(
            snapshot_id="candidate", effective_at="2026-08-16T00:00:00+00:00",
            created_at="2026-08-16T00:00:00+00:00", model_version="test",
            model_status="CANDIDATE", constituents=tickers, rankings=rankings,
        )
        snapshot = ResearchSnapshot(**{**base.unsigned_dict(), "checksum": base.calculated_checksum()})
        self.assertTrue(candidate_readiness(snapshot)["ready"])
        rankings[tickers[0]]["coverage_pct"] = 50
        broken = ResearchSnapshot(**{**base.unsigned_dict(), "rankings": rankings})
        broken = ResearchSnapshot(**{**broken.unsigned_dict(), "checksum": broken.calculated_checksum()})
        # One missing row still passes the >=90% universe threshold.
        self.assertTrue(candidate_readiness(broken)["ready"])
        for ticker in tickers[:5]:
            rankings[ticker]["coverage_pct"] = 50
        broken = ResearchSnapshot(**{**base.unsigned_dict(), "rankings": rankings})
        broken = ResearchSnapshot(**{**broken.unsigned_dict(), "checksum": broken.calculated_checksum()})
        self.assertFalse(candidate_readiness(broken)["ready"])


if __name__ == "__main__":
    unittest.main()
