import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from data.filing_manifest import (
    ManifestError,
    exact_identity,
    merge_files,
    merge_manifests,
)
from scripts.ci.check_workflow_policy import validate_workflow


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
    def test_idx_workflow_syncs_before_merge_and_policy_allowlist_is_exact(self):
        workflow_path = (
            Path(__file__).resolve().parents[1] / ".github/workflows/idx-filings.yml"
        )
        text = workflow_path.read_text()
        self.assertLess(
            text.index('git checkout -b "$branch" origin/main'),
            text.index("python -m data.filing_manifest"),
        )
        merge_index = text.index("python -m data.filing_manifest")
        self.assertLess(
            text.index('git checkout -B "$branch" "origin/$branch"'), merge_index
        )
        self.assertLess(text.index("git merge --no-edit origin/main"), merge_index)
        self.assertNotIn(
            "cp /tmp/idx_filing_manifest.json data/idx_filing_manifest.json", text
        )
        self.assertNotRegex(
            text, r"uses: actions/(checkout|setup-python|upload-artifact)@v"
        )
        self.assertEqual(validate_workflow(workflow_path), [])

        minimal = """name: idx-filings
on: workflow_dispatch
permissions: {contents: read}
concurrency: {group: idx}
jobs:
  discover:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions: {contents: write, pull-requests: write, actions: write}
    steps: [{uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5}]
  import:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions: {contents: read, actions: write}
    steps: [{uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5}]
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "idx-filings.yml"
            path.write_text(minimal)
            self.assertEqual(validate_workflow(path), [])
            path.write_text(
                minimal.replace(
                    "contents: read, actions: write", "contents: write, actions: write"
                )
            )
            self.assertTrue(
                any(
                    "permissions must be exactly" in error
                    for error in validate_workflow(path)
                )
            )

    def test_merge_preserves_baseline_and_appends_restatement(self):
        result = merge_manifests(
            {"discovery": {"year": 2026}, "filings": [filing()]},
            {"discovery": {"year": 2027}, "filings": [filing(2)]},
        )
        self.assertEqual(
            [row["restatement_version"] for row in result["filings"]], [1, 2]
        )
        self.assertEqual(result["discovery"], {"year": 2027})
        self.assertNotIn("available_at", json.dumps(result))

    def test_narrow_2026_draft_retains_2021_to_2026_history(self):
        history = [
            filing(ticker=f"T{year}", period_end=f"{year}-12-31")
            for year in range(2021, 2027)
        ]
        result = merge_manifests({"filings": history}, {"filings": [history[-1]]})
        self.assertEqual(len(result["filings"]), 6)

    def test_timestamp_audit_and_checksum_conflicts_fail(self):
        values = {
            "published_at": ("2026-03-02T00:00:00+00:00", "2026-03-03T00:00:00+00:00"),
            "audit_status": ("AUDITED", "UNAUDITED"),
            "checksum": ("a" * 64, "b" * 64),
        }
        for field, (left, right) in values.items():
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ManifestError, "provenance conflict"),
            ):
                merge_manifests(
                    {"filings": [filing(**{field: left})]},
                    {"filings": [filing(**{field: right})]},
                )

    def test_serialization_is_deterministic_and_output_has_no_temp_residue(self):
        first = merge_manifests(
            {"filings": [filing(ticker="B"), filing(ticker="A")]}, {"filings": []}
        )
        second = merge_manifests(
            {"filings": [filing(ticker="A"), filing(ticker="B")]}, {"filings": []}
        )
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )

    def test_merge_files_bytes_are_canonical_for_mapping_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline_a = root / "baseline-a.json"
            baseline_b = root / "baseline-b.json"
            discovered = root / "discovered.json"
            output_a = root / "output-a.json"
            output_b = root / "output-b.json"
            row = filing()
            baseline_a.write_text(
                json.dumps({"filings": [row], "discovery": {"z": 1, "a": 2}})
            )
            baseline_b.write_text(
                json.dumps(
                    {
                        "discovery": {"a": 2, "z": 1},
                        "filings": [dict(reversed(row.items()))],
                    }
                )
            )
            discovered.write_text(json.dumps({"filings": []}))
            merge_files(baseline_a, discovered, output_a)
            merge_files(baseline_b, discovered, output_b)
            self.assertEqual(output_a.read_bytes(), output_b.read_bytes())

    def test_validator_normalizes_filing_type_across_baseline(self):
        from scripts.ci.validate_manifest import validate_manifest

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = filing(filing_type=" annual ")
            current = filing(filing_type="ANNUAL")
            (root / "baseline.json").write_text(json.dumps({"filings": [baseline]}))
            (root / "current.json").write_text(json.dumps({"filings": [current]}))
            errors = validate_manifest(
                root / "current.json", root / "baseline.json", kind="filing"
            )
            self.assertFalse(
                any("removed" in error or "conflict" in error for error in errors)
            )

    def test_duplicate_and_provenance_conflict_fail(self):
        with self.assertRaisesRegex(ManifestError, "duplicate exact identity"):
            merge_manifests({"filings": [filing(), filing()]}, {"filings": []})
        with self.assertRaisesRegex(ManifestError, "provenance conflict"):
            merge_manifests(
                {"filings": [filing()]},
                {"filings": [filing(source_url="https://www.idx.id/changed.zip")]},
            )

    def test_narrow_draft_preserves_history_and_lower_restatement_fails(self):
        result = merge_manifests(
            {"filings": [filing(), filing(2)]}, {"filings": [filing()]}
        )
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
            completed = subprocess.run(
                command, cwd=root, capture_output=True, text=True
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                len(json.loads(output.read_text())["filings"]),
                len(
                    json.loads((root / "data/idx_filing_manifest.json").read_text())[
                        "filings"
                    ]
                ),
            )

    def test_conflict_cli_leaves_existing_output_and_no_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "baseline.json"
            discovered = root / "discovered.json"
            output = root / "output.json"
            baseline.write_text(json.dumps({"filings": [filing()]}))
            discovered.write_text(
                json.dumps(
                    {"filings": [filing(source_url="https://www.idx.id/changed.zip")]}
                )
            )
            output.write_text("sentinel")
            completed = subprocess.run(
                [
                    "python",
                    "-m",
                    "data.filing_manifest",
                    "--baseline",
                    str(baseline),
                    "--discovered",
                    str(discovered),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(output.read_text(), "sentinel")
            self.assertEqual(list(root.glob(f".{output.name}.*")), [])

    def test_malformed_inputs_fail_before_output_write(self):
        with self.assertRaises(ManifestError):
            merge_manifests({"filings": [{"ticker": "TEST"}]}, {"filings": []})
        with self.assertRaises(ManifestError):
            merge_manifests({"filings": []}, {"filings": [{"ticker": "TEST"}]})

    def test_identity_normalizes_ticker_and_requires_positive_version(self):
        self.assertEqual(
            exact_identity(filing(ticker="test.JK")),
            ("TEST", "ANNUAL", "2025-12-31", 1),
        )
        with self.assertRaisesRegex(ManifestError, "positive"):
            merge_manifests({"filings": [filing(0)]}, {"filings": []})


if __name__ == "__main__":
    unittest.main()
