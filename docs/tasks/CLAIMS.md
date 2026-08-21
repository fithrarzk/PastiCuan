# Active Task Claims

This registry is written only by the orchestrator. GitHub task-issue assignment with label `status:claimed` is the coordination lock when GitHub is available; this file is its recoverable human-readable mirror.

| Task | Status | Owner | Model/effort | Base SHA | Branch/worktree | Exact files | Claimed at |
|---|---|---|---|---|---|---|---|
| DOC-001 | verified | root orchestrator | Sol/high | f5166c7 | `docs/DOC-001-autonomous-context` | `.agents/skills/**`, `AGENTS.md`, `CONTEXT.md`, `docs/**`, `README.md`, `DEPLOY_FREE.md`; merged as `b9f889e` | 2026-08-22 |
| OPS-001 | verified | root orchestrator + CI/CD audit | Sol/high | f5166c7 | read-only audit | GitHub/ruleset/workflow/Railway inventory; no file ownership | 2026-08-22 |
| CI-001 | review | Luna implementation, root integration | Luna/medium | b9f889e | `fix/CI-001-generated-pr-checks` / `../PastiCuan-wt/ci-001-generated-pr-checks` | `.github/workflows/idx-filings.yml`, `.github/workflows/validate-branch.yml`, `tests/test_workflow_policy.py`, `docs/tasks/CI-001-generated-pr-validation.md`, `docs/tasks/CLAIMS.md` | 2026-08-22 |

Before adding a row, the orchestrator verifies dependencies and checks that no active row owns the same file or contract. On verification, change the task to `verified`, record the final SHA in its task card, and release the GitHub claim. Never delete claim history.
