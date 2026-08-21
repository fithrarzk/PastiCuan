import json
import tempfile
import unittest
from pathlib import Path

from scripts.ci.check_migrations import migration_checksums
from scripts.ci.check_migrations import migration_pairs, read_sql
from scripts.ci.check_security import scan_paths
from scripts.ci.check_workflow_policy import validate_workflow
from scripts.ci.validate_manifest import validate_manifest


ROOT = Path(__file__).resolve().parents[1]


class MigrationGateTests(unittest.TestCase):
    def test_checksum_ledger_is_deterministic_and_ordered(self):
        checksums = migration_checksums(ROOT / "storage/migrations")
        self.assertEqual(list(checksums), sorted(checksums))
        self.assertEqual(len(checksums), 6)
        self.assertTrue(all(len(value) == 64 for value in checksums.values()))

    def test_migration_pair_and_utf8_failures_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "001_demo.up.sql").write_bytes("-- café\nSELECT 1;".encode())
            with self.assertRaisesRegex(ValueError, "up/down"):
                migration_pairs(root)
            (root / "001_demo.down.sql").write_text("SELECT 1;")
            self.assertIn("café", read_sql(root / "001_demo.up.sql"))
            (root / "001_demo.up.sql").write_bytes(b"-- \xff")
            with self.assertRaises(UnicodeDecodeError):
                read_sql(root / "001_demo.up.sql")


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
            baseline.write_text(
                json.dumps({"filings": [entry, {**entry, "ticker": "OLD"}]})
            )
            errors = validate_manifest(current, baseline)
        self.assertTrue(any("duplicate filing identity" in error for error in errors))
        self.assertTrue(any("filing identities removed" in error for error in errors))


class WorkflowGateTests(unittest.TestCase):
    def test_pull_request_workflow_has_all_stable_jobs_and_pins_actions(self):
        errors = validate_workflow(
            ROOT / ".github/workflows/ci.yml", require_required_jobs=True
        )
        self.assertEqual(errors, [])

    def test_legacy_and_generated_workflows_remain_policy_safe(self):
        for name in ("test.yml", "validate-branch.yml"):
            self.assertEqual(validate_workflow(ROOT / ".github/workflows" / name), [])

    def test_workflow_negative_permissions_timeout_action_and_trigger(self):
        workflow = """
name: bad
on: push
jobs:
  bad:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ci.yml"
            path.write_text(workflow)
            errors = validate_workflow(path)
        self.assertTrue(any("permissions" in error for error in errors))
        self.assertTrue(any("timeout" in error for error in errors))
        self.assertTrue(any("immutable" in error for error in errors))
        self.assertTrue(any("pull_request" in error for error in errors))


class SecurityGateTests(unittest.TestCase):
    def test_secret_fixture_fails_without_disclosing_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.txt"
            path.write_text("postgres" + "ql://u:password@db.internal/research\n")
            findings = scan_paths([path])
        self.assertEqual(findings, [(str(path), "database URL")])


class ContainerGateTests(unittest.TestCase):
    def test_smoke_uses_image_cmd_and_dynamic_port_healthcheck(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        smoke = (ROOT / "scripts/ci/container_smoke.sh").read_text()
        self.assertIn("os.getenv('PORT','8080')", dockerfile)
        self.assertIn("UVICORN_LIFESPAN=off", smoke)
        self.assertIn("docker run --detach", smoke)
        self.assertNotIn("uvicorn bot_webhook", smoke)


if __name__ == "__main__":
    unittest.main()
