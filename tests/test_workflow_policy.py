import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IDX_WORKFLOW = (ROOT / ".github/workflows/idx-filings.yml").read_text()
VALIDATE_WORKFLOW = (ROOT / ".github/workflows/validate-branch.yml").read_text()
RESEARCH_WORKFLOW = (ROOT / ".github/workflows/research-daily.yml").read_text()


class GeneratedPullRequestWorkflowPolicyTests(unittest.TestCase):
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
        self.assertIn('case "$exit_code" in', RESEARCH_WORKFLOW)
        self.assertIn("10)", RESEARCH_WORKFLOW)
        self.assertIn('exit 0', RESEARCH_WORKFLOW)
        self.assertIn('exit "$exit_code"', RESEARCH_WORKFLOW)
        self.assertIn("--output /tmp/daily-research-report.json", RESEARCH_WORKFLOW)


if __name__ == "__main__":
    unittest.main()
