import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from data.filing_manifest import ManifestError, exact_identity, merge_manifests


def filing(version=1, ticker="TEST", **changes):
    row = {
        "ticker": ticker,
        "filing_type": "ANNUAL",
        "period_end": "2025-12-31",
        "restatement_version": version,
        "source_url": f"https://www.idx.id/{ticker.lower()}-{version}.zip",
        "published_at": "2026-03-01T00:00:00+00:00",
        "audit_status": "AUDITED",
    }
    row.update(changes)
    return row


class FilingManifestTests(unittest.TestCase):
    def test_merge_preserves_baseline_and_appends_restatement(self):
        result = merge_manifests(
            {"discovery": {"year": 2026}, "filings": [filing()]},
            {"discovery": {"year": 2027}, "filings": [filing(2)]},
        )
        self.assertEqual([row["restatement_version"] for row in result["filings"]], [1, 2])
        self.assertEqual(result["discovery"], {"year": 2027})
        self.assertNotIn("available_at", json.dumps(result))

    def test_duplicate_and_provenance_conflict_fail(self):
        with self.assertRaisesRegex(ManifestError, "duplicate exact identity"):
            merge_manifests({"filings": [filing(), filing()]}, {"filings": []})
        with self.assertRaisesRegex(ManifestError, "provenance conflict"):
            merge_manifests({"filings": [filing()]}, {"filings": [filing(source_url="https://www.idx.id/changed.zip")]})

    def test_narrow_draft_preserves_history_and_lower_restatement_fails(self):
        result = merge_manifests({"filings": [filing(), filing(2)]}, {"filings": [filing()]})
        self.assertEqual(len(result["filings"]), 2)
        with self.assertRaisesRegex(ManifestError, "regression"):
            merge_manifests({"filings": [filing(2)]}, {"filings": [filing()]})

    def test_atomic_cli_merges_real_manifest_without_loss(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "merged.json"
            command = [
                "python",
                "-m",
                "data.filing_manifest",
                "--baseline",
                str(root / "data/idx_filing_manifest.json"),
                "--discovered",
                str(root / "data/idx_filing_manifest.json"),
                "--output",
                str(output),
            ]
            completed = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                len(json.loads(output.read_text())["filings"]),
                len(json.loads((root / "data/idx_filing_manifest.json").read_text())["filings"]),
            )

    def test_identity_normalizes_ticker_and_requires_positive_version(self):
        self.assertEqual(exact_identity(filing(ticker="test.JK")), ("TEST", "ANNUAL", "2025-12-31", 1))
        with self.assertRaisesRegex(ManifestError, "positive"):
            merge_manifests({"filings": [filing(0)]}, {"filings": []})


if __name__ == "__main__":
    unittest.main()
