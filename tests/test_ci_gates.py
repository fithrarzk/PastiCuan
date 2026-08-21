import json
import tempfile
import unittest
from pathlib import Path

from scripts.ci.check_migrations import migration_checksums
from scripts.ci.check_workflow_policy import validate_workflow
from scripts.ci.validate_manifest import validate_manifest


ROOT = Path(__file__).resolve().parents[1]


class MigrationGateTests(unittest.TestCase):
    def test_checksum_ledger_is_deterministic_and_ordered(self):
        checksums = migration_checksums(ROOT / "storage/migrations")
        self.assertEqual(list(checksums), sorted(checksums))
        self.assertEqual(len(checksums), 6)
        self.assertTrue(all(len(value) == 64 for value in checksums.values()))


class ManifestGateTests(unittest.TestCase):
    def test_reviewed_manifest_has_official_identity_and_no_removals(self):
        path = ROOT / "data/idx_filing_manifest.json"
        self.assertEqual(validate_manifest(path), [])

    def test_manifest_rejects_duplicate_identity_and_removal(self):
        entry = {
            "ticker": "TEST",
            "source_url": "https://www.idx.co.id/filing.zip",
            "published_at": "2026-01-01T00:00:00+00:00",
            "filing_type": "Q1",
            "period_end": "2025-03-31",
        }
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "current.json"
            baseline = Path(directory) / "baseline.json"
            current.write_text(json.dumps({"filings": [entry, entry]}))
            baseline.write_text(json.dumps({"filings": [entry, {**entry, "ticker": "OLD"}]}))
            errors = validate_manifest(current, baseline)
        self.assertTrue(any("duplicate filing identity" in error for error in errors))
        self.assertTrue(any("filing identities removed" in error for error in errors))


class WorkflowGateTests(unittest.TestCase):
    def test_pull_request_workflow_has_all_stable_jobs_and_pins_actions(self):
        errors = validate_workflow(ROOT / ".github/workflows/ci.yml", require_required_jobs=True)
        self.assertEqual(errors, [])

    def test_legacy_and_generated_workflows_remain_policy_safe(self):
        for name in ("test.yml", "validate-branch.yml"):
            self.assertEqual(validate_workflow(ROOT / ".github/workflows" / name), [])


if __name__ == "__main__":
    unittest.main()
