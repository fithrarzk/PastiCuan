import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.ci.check_workflow_policy import _workflow_data, validate_workflow


ROOT = Path(__file__).resolve().parents[1]
IDX_WORKFLOW = (ROOT / ".github/workflows/idx-filings.yml").read_text()
VALIDATE_WORKFLOW = (ROOT / ".github/workflows/validate-branch.yml").read_text()
RESEARCH_WORKFLOW = (ROOT / ".github/workflows/research-daily.yml").read_text()
RESEARCH_WORKFLOW_PATH = ROOT / ".github/workflows/research-daily.yml"
VALIDATION_WORKFLOW = (ROOT / ".github/workflows/research-validation.yml").read_text()
BACKUP_WORKFLOW = (ROOT / ".github/workflows/backup.yml").read_text()


class GeneratedPullRequestWorkflowPolicyTests(unittest.TestCase):
    def test_import_uses_bounded_shards_and_durable_aggregation_gate(self):
        workflow = _workflow_data(ROOT / ".github/workflows/idx-filings.yml")
        jobs = workflow["jobs"]
        self.assertEqual(
            set(jobs), {"discover", "prepare-import", "import-shards", "aggregate"}
        )
        shards = jobs["import-shards"]
        self.assertFalse(shards["strategy"]["fail-fast"])
        self.assertEqual(shards["strategy"]["matrix"]["shard"], list(range(8)))
        self.assertEqual(shards["timeout-minutes"], 45)
        shard_runs = "\n".join(step.get("run", "") for step in shards["steps"])
        self.assertIn('--shard-count 8 --shard-index "${{ matrix.shard }}"', shard_runs)
        self.assertIn('--run-id "${{ github.run_id }}"', shard_runs)
        self.assertIn("--max-attempts 3", shard_runs)
        self.assertIn("--retry-backoff-seconds 5", shard_runs)
        self.assertIn("--time-budget-seconds 1200", shard_runs)
        self.assertNotIn("research-daily.yml", shard_runs)

        aggregate = jobs["aggregate"]
        self.assertEqual(set(aggregate["needs"]), {"prepare-import", "import-shards"})
        self.assertEqual(aggregate["timeout-minutes"], 10)
        aggregate_runs = "\n".join(step.get("run", "") for step in aggregate["steps"])
        self.assertIn("--aggregate-only", aggregate_runs)
        refresh = next(
            step
            for step in aggregate["steps"]
            if step.get("name") == "Request a research refresh"
        )
        self.assertEqual(
            refresh.get("if"),
            "needs.import-shards.result == 'success' && steps.progress.outcome == 'success'",
        )

    def test_import_validates_before_source_ingestion_and_uses_shared_shards(self):
        workflow = _workflow_data(ROOT / ".github/workflows/idx-filings.yml")
        discover_steps = workflow["jobs"]["discover"]["steps"]
        discover_names = [step.get("name") for step in discover_steps]
        self.assertLess(
            discover_names.index("Validate reviewed source manifest before discovery"),
            discover_names.index("Import reviewed source manifest"),
        )
        self.assertLess(
            discover_names.index(
                "Validate reviewed Filing manifest before source ingestion"
            ),
            discover_names.index("Import reviewed source manifest"),
        )
        discover_validation = "\n".join(
            step.get("run", "")
            for step in discover_steps
            if step.get("name")
            in {
                "Validate reviewed source manifest before discovery",
                "Validate reviewed Filing manifest before source ingestion",
            }
        )
        self.assertIn("data/source_manifest.json --kind source", discover_validation)
        self.assertIn(
            "data/idx_filing_manifest.json --kind filing", discover_validation
        )
        prepare_steps = workflow["jobs"]["prepare-import"]["steps"]
        validation = next(
            index
            for index, step in enumerate(prepare_steps)
            if step.get("name") == "Validate reviewed manifests before import"
        )
        ingestion = next(
            index
            for index, step in enumerate(prepare_steps)
            if step.get("name") == "Import reviewed source manifest"
        )
        self.assertLess(validation, ingestion)
        self.assertIn(
            "validate_manifest.py data/source_manifest.json",
            prepare_steps[validation]["run"],
        )
        self.assertIn(
            "validate_manifest.py data/idx_filing_manifest.json",
            prepare_steps[validation]["run"],
        )
        shard_runs = "\n".join(
            step.get("run", "") for step in workflow["jobs"]["import-shards"]["steps"]
        )
        self.assertIn("production_db_lock --mode shared", shard_runs)
        aggregate_runs = "\n".join(
            step.get("run", "") for step in workflow["jobs"]["aggregate"]["steps"]
        )
        self.assertIn("production_db_lock --mode exclusive", aggregate_runs)

    def test_all_production_writer_workflows_use_the_shared_lock_wrapper(self):
        for path, text in (
            (ROOT / ".github/workflows/idx-filings.yml", IDX_WORKFLOW),
            (ROOT / ".github/workflows/research-daily.yml", RESEARCH_WORKFLOW),
            (ROOT / ".github/workflows/research-validation.yml", VALIDATION_WORKFLOW),
            (ROOT / ".github/workflows/backup.yml", BACKUP_WORKFLOW),
        ):
            self.assertIn("SUPABASE_WRITER_DATABASE_URL", text, path)
            self.assertIn("operations.production_db_lock", text, path)
        self.assertIn("production_db_lock --mode exclusive", VALIDATION_WORKFLOW)
        self.assertIn("production_db_lock --mode exclusive", BACKUP_WORKFLOW)

    def test_research_push_ignores_only_reviewed_non_runtime_paths(self):
        workflow = _workflow_data(RESEARCH_WORKFLOW_PATH)
        trigger = workflow.get("on", workflow.get(True, {}))
        push = trigger["push"]
        self.assertEqual(push["branches"], ["main"])
        self.assertEqual(
            set(push["paths-ignore"]),
            {
                ".agents/**",
                ".github/workflows/ci.yml",
                ".github/workflows/test.yml",
                ".github/workflows/validate-branch.yml",
                "AGENTS.md",
                "CONTEXT.md",
                "DEPLOY_FREE.md",
                "README.md",
                "docs/**",
                "requirements-ci.txt",
                "scripts/ci/**",
                "tests/**",
                "data/idx_filing_manifest.json",
                "data/source_manifest.json",
            },
        )
        self.assertEqual(validate_workflow(RESEARCH_WORKFLOW_PATH), [])

    def test_research_policy_rejects_runtime_path_exclusions(self):
        unsafe = RESEARCH_WORKFLOW.replace(
            '      - "docs/**"',
            '      - "analysis/**"',
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "research-daily.yml"
            path.write_text(unsafe)
            errors = validate_workflow(path)
        self.assertTrue(any("safe paths-ignore" in error for error in errors))

    def test_research_policy_rejects_unwrapped_writer_command(self):
        unsafe = RESEARCH_WORKFLOW.replace(
            "operations.production_db_lock", "operations.not_a_lock"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "research-daily.yml"
            path.write_text(unsafe)
            errors = validate_workflow(path)
        self.assertTrue(any("lock coverage mismatch" in error for error in errors))

    def test_idx_policy_rejects_unwrapped_discovery_writer(self):
        unsafe = IDX_WORKFLOW.replace(
            "operations.production_db_lock", "operations.not_a_lock"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "idx-filings.yml"
            path.write_text(unsafe)
            errors = validate_workflow(path)
        self.assertTrue(any("discover-idx-xbrl" in error for error in errors))

    def test_idx_policy_rejects_missing_discover_filing_validation(self):
        unsafe = IDX_WORKFLOW.replace(
            "      - name: Validate reviewed Filing manifest before source ingestion\n"
            "        run: python scripts/ci/validate_manifest.py data/idx_filing_manifest.json --kind filing\n",
            "",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "idx-filings.yml"
            path.write_text(unsafe)
            errors = validate_workflow(path)
        self.assertTrue(any("Filing manifest" in error for error in errors))

    def test_idx_policy_rejects_unguarded_refresh_dispatch(self):
        unsafe = IDX_WORKFLOW.replace(
            "if: needs.import-shards.result == 'success' && steps.progress.outcome == 'success'",
            "if: always()",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "idx-filings.yml"
            path.write_text(unsafe)
            errors = validate_workflow(path)
        self.assertTrue(
            any("guard" in error or "dispatch" in error for error in errors)
        )

    def test_writer_policy_rejects_mixed_wrapped_and_unwrapped_commands(self):
        unsafe = RESEARCH_WORKFLOW.replace(
            "            python -m operations.research_cli run-daily-research \\\n",
            "            python -m operations.research_cli run-daily-research \\\n"
            "          python -m operations.research_cli backup\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "research-daily.yml"
            path.write_text(unsafe)
            errors = validate_workflow(path)
        self.assertTrue(any("lock coverage mismatch" in error for error in errors))

    def test_writer_policy_rejects_decoy_wrapper_before_unwrapped_command(self):
        unsafe = RESEARCH_WORKFLOW.replace(
            "            python -m operations.research_cli run-daily-research \\\n",
            "            echo wrapped-looking command\n"
            "          python -m operations.research_cli run-daily-research\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "research-daily.yml"
            path.write_text(unsafe)
            errors = validate_workflow(path)
        self.assertTrue(any("lock coverage mismatch" in error for error in errors))

    def test_new_writer_workflow_is_not_exempt_from_lock_policy(self):
        unsafe = RESEARCH_WORKFLOW.replace("name: research-daily", "name: new-writer")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new-writer.yml"
            path.write_text(
                unsafe.replace("operations.production_db_lock", "operations.not_a_lock")
            )
            errors = validate_workflow(path)
        self.assertTrue(
            any(
                "production database lock wrapper is required" in error
                for error in errors
            )
        )

    def test_validation_inputs_are_env_quoted_for_nested_shell(self):
        self.assertIn(
            "VALIDATION_START: ${{ inputs.validation_start }}", VALIDATION_WORKFLOW
        )
        self.assertIn(
            "VALIDATION_END: ${{ inputs.validation_end }}", VALIDATION_WORKFLOW
        )
        self.assertIn(
            '--start "$VALIDATION_START" --end "$VALIDATION_END"',
            VALIDATION_WORKFLOW,
        )
        run_body = VALIDATION_WORKFLOW.split("        run: |", 1)[1]
        self.assertNotIn("${{ inputs.validation_start }}", run_body)
        self.assertNotIn("${{ inputs.validation_end }}", run_body)

    def test_hostile_validation_input_remains_data_in_nested_shell(self):
        hostile = "2026-01-01'; touch /tmp/not-a-command; echo '"
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", 'printf "%s" "$VALIDATION_START"'],
            env={"VALIDATION_START": hostile},
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout, hostile)

    def test_discovery_dispatches_validation_for_the_pushed_head(self):
        self.assertIn("actions: write", IDX_WORKFLOW)
        self.assertRegex(
            IDX_WORKFLOW,
            r"gh workflow run validate-branch\.yml --ref \"\$branch\"",
        )
        self.assertIn('-f branch="$branch"', IDX_WORKFLOW)
        self.assertIn('-f sha="$head_sha"', IDX_WORKFLOW)

    def test_discovery_reuses_one_review_branch_and_pr(self):
        self.assertIn('branch="idx-manifest-review"', IDX_WORKFLOW)
        self.assertRegex(IDX_WORKFLOW, r"gh pr list .*--head \"\$branch\"")
        self.assertIn('if [[ -z "$pr_number" ]]', IDX_WORKFLOW)
        self.assertNotIn("GITHUB_RUN_ID", IDX_WORKFLOW)

    def test_existing_review_branch_is_synchronized_with_main(self):
        self.assertIn("git fetch origin main", IDX_WORKFLOW)
        self.assertIn("git merge --no-edit origin/main", IDX_WORKFLOW)
        self.assertIn('git checkout -b "$branch" origin/main', IDX_WORKFLOW)

    def test_validation_is_explicit_dispatch_only(self):
        self.assertRegex(VALIDATE_WORKFLOW, r"(?m)^on:\s*$")
        self.assertIn("workflow_dispatch:", VALIDATE_WORKFLOW)
        self.assertNotRegex(VALIDATE_WORKFLOW, r"(?m)^\s+(push|pull_request|schedule):")
        self.assertNotIn("pull_request", VALIDATE_WORKFLOW)
        self.assertNotIn("discover-idx-xbrl", VALIDATE_WORKFLOW)
        self.assertNotIn("gh pr", VALIDATE_WORKFLOW)

    def test_validation_checks_the_exact_remote_branch_head(self):
        self.assertIn("contents: read", VALIDATE_WORKFLOW)
        self.assertNotRegex(VALIDATE_WORKFLOW, r"contents:\s+write")
        self.assertIn(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1",
            VALIDATE_WORKFLOW,
        )
        self.assertIn(
            "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0",
            VALIDATE_WORKFLOW,
        )
        self.assertNotRegex(
            VALIDATE_WORKFLOW, r"(?m)^\s+- uses: [^\n]+@(v\d|main|master)\b"
        )
        self.assertIn("git rev-parse HEAD", VALIDATE_WORKFLOW)
        self.assertIn("git ls-remote origin", VALIDATE_WORKFLOW)
        self.assertIn("EXPECTED_SHA", VALIDATE_WORKFLOW)
        self.assertRegex(VALIDATE_WORKFLOW, r"(?m)^\s+test:\s*$")
        self.assertIn("python -m unittest discover -s tests -v", VALIDATE_WORKFLOW)

    def test_research_job_normalizes_only_waiting_exit(self):
        self.assertIn(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1",
            RESEARCH_WORKFLOW,
        )
        self.assertIn(
            "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0",
            RESEARCH_WORKFLOW,
        )
        self.assertIn(
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2",
            RESEARCH_WORKFLOW,
        )
        self.assertIn('case "$exit_code" in', RESEARCH_WORKFLOW)
        self.assertIn("10)", RESEARCH_WORKFLOW)
        self.assertIn("exit 0", RESEARCH_WORKFLOW)
        self.assertIn('exit "$exit_code"', RESEARCH_WORKFLOW)
        self.assertIn("--output /tmp/daily-research-report.json", RESEARCH_WORKFLOW)


if __name__ == "__main__":
    unittest.main()
