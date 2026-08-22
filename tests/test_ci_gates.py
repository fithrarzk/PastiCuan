import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.ci.check_migrations import migration_checksums
from scripts.ci.check_migrations import migration_pairs, normalize_version, read_sql
from scripts.ci.check_security import scan_paths
from scripts.ci.check_workflow_policy import _workflow_data, validate_workflow
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
        self.assertEqual(normalize_version(b"001_demo"), "001_demo")
        self.assertEqual(normalize_version("001_demo"), "001_demo")


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

    def test_filing_manifest_rejects_non_attachment_url(self):
        path = ROOT / "data/idx_filing_manifest.example.json"
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory) / "broken.json"
            broken.write_text(path.read_text().replace("instance.zip", "landing.html"))
            errors = validate_manifest(broken, kind="filing")
        self.assertTrue(any("filing attachment" in error for error in errors))

    def test_source_manifest_has_separate_schema_and_host_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.json"
            path.write_text(
                json.dumps(
                    {"sources": [{"source_url": "https://licensed.example/data.csv"}]}
                )
            )
            errors = validate_manifest(path, kind="source")
        self.assertTrue(any("provider and artifact_type" in error for error in errors))


class WorkflowGateTests(unittest.TestCase):
    def test_unittest_jobs_install_ci_dependencies(self):
        workflow_paths = (
            ROOT / ".github/workflows/test.yml",
            ROOT / ".github/workflows/ci.yml",
            ROOT / ".github/workflows/validate-branch.yml",
        )
        for path in workflow_paths:
            workflow = _workflow_data(path)
            for job_name, job in workflow["jobs"].items():
                runs = "\n".join(
                    step.get("run", "")
                    for step in job.get("steps", [])
                    if isinstance(step, dict)
                )
                if "python -m unittest discover" in runs:
                    self.assertIn(
                        "pip install -r requirements-bot.txt -r requirements-ci.txt",
                        runs,
                        f"{path.name}:{job_name}",
                    )

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

    def test_generated_validation_rejects_recursion_commands(self):
        workflow = """
name: validate-branch
on:
  workflow_dispatch:
permissions:
  contents: read
concurrency: {group: validation}
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - run: gh workflow run validate-branch.yml
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validate-branch.yml"
            path.write_text(workflow)
            errors = validate_workflow(path)
        self.assertTrue(any("recursion" in error for error in errors))

    def test_required_generated_contexts_need_stable_ids_and_names(self):
        workflow = """
name: validate-branch
on:
  workflow_dispatch:
permissions:
  contents: read
concurrency: {group: validation}
jobs:
  unit:
    name: renamed-unit
    runs-on: ubuntu-latest
    timeout-minutes: 5
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validate-branch.yml"
            path.write_text(workflow)
            errors = validate_workflow(path, require_required_jobs=True)
        self.assertTrue(any("missing jobs" in error for error in errors))

    def test_generated_stable_jobs_depend_on_head_guard_not_legacy_test(self):
        workflow = _workflow_data(ROOT / ".github/workflows/validate-branch.yml")
        self.assertIn("verify-head", workflow["jobs"])
        for job_name in (
            "test",
            "unit",
            "quality",
            "workflow-policy",
            "migration",
            "container-smoke",
            "manifest-validate",
            "security",
        ):
            self.assertEqual(workflow["jobs"][job_name].get("needs"), "verify-head")

    def test_quality_discovery_is_nul_safe_and_excludes_deleted_paths(self):
        for name in ("ci.yml", "validate-branch.yml"):
            text = (ROOT / ".github/workflows" / name).read_text()
            self.assertIn("--diff-filter=ACMR", text)
            self.assertIn("--name-only -z", text)
            self.assertIn("mapfile -d ''", text)
            self.assertIn('"${changed[@]}"', text)
            self.assertIn("--", text)


class SecurityGateTests(unittest.TestCase):
    def test_secret_fixture_fails_without_disclosing_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.txt"
            path.write_text("postgres" + "ql://u:password@db.internal/research\n")
            findings = scan_paths([path])
        self.assertEqual(findings, [(str(path), "database URL")])

    def test_database_credentials_are_not_hidden_by_familiar_hostnames(self):
        urls = (
            "postgres" + "ql://u:secret@localhost/research",
            "postgres" + "ql://u:secret@db.example/research",
            "postgres" + "ql://pasticuan_ci:secret@db.internal/research",
        )
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, url in enumerate(urls):
                path = Path(directory) / f"fixture-{index}"
                path.write_text(url)
                paths.append(path)
            findings = scan_paths(paths)
        self.assertEqual(len(findings), len(urls))
        self.assertTrue(all("secret" not in str(finding) for finding in findings))

    def test_secret_categories_fail_without_returning_secret_values(self):
        values = {
            "telegram": "123456789:" + "a" * 35,
            "aws": "AKIA" + "A" * 16,
            "r2": "R2_SECRET_ACCESS_KEY=" + "b" * 24,
            "private": "-----BEGIN " + "PRIVATE KEY-----",
            "github": "ghp_" + "c" * 24,
            "slack": "xoxb-" + "d" * 24,
        }
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for category, value in values.items():
                path = Path(directory) / category
                path.write_text(value)
                paths.append(path)
            findings = scan_paths(paths)
        self.assertEqual(
            {category for _, category in findings},
            {
                "Telegram token",
                "cloud access key",
                "private key",
                "GitHub token",
                "Slack token",
            },
        )
        self.assertTrue(all(value not in str(findings) for value in values.values()))

    def test_dependency_wrapper_propagates_audit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "auditor"
            fake.write_text("#!/bin/sh\nexit 23\n")
            fake.chmod(0o755)
            env = {**os.environ, "PIP_AUDIT_BIN": str(fake)}
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/ci/check_dependencies.sh")],
                env=env,
                capture_output=True,
            )
        self.assertEqual(result.returncode, 23)


class ContainerGateTests(unittest.TestCase):
    def test_smoke_uses_image_cmd_and_dynamic_port_healthcheck(self):
        dockerfile = (ROOT / "Dockerfile").read_text()
        smoke = (ROOT / "scripts/ci/container_smoke.sh").read_text()
        self.assertIn("os.getenv('PORT','8080')", dockerfile)
        self.assertIn("UVICORN_LIFESPAN=off", smoke)
        self.assertIn("docker run --detach", smoke)
        self.assertNotIn("uvicorn bot_webhook", smoke)
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/ci/container_smoke.sh")],
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_smoke_failure_propagates_logs_and_cleanup_with_fake_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "marker"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            (fake_bin / "docker").write_text(
                "#!/bin/sh\n"
                f"echo \"$*\" >> '{marker}'\n"
                'case "$1" in logs) exit 0;; *) exit 0;; esac\n'
            )
            (fake_bin / "curl").write_text("#!/bin/sh\nexit 1\n")
            for tool in (fake_bin / "docker", fake_bin / "curl"):
                tool.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "SMOKE_ATTEMPTS": "1",
            }
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/ci/container_smoke.sh"), "ci-image"],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            calls = marker.read_text()
            self.assertIn("run", calls)
            self.assertIn("logs", calls)
            self.assertIn("rm --force", calls)


if __name__ == "__main__":
    unittest.main()
