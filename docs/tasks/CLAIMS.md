# Active Task Claims

This registry is written only by the orchestrator. GitHub task-issue assignment with label `status:claimed` is the coordination lock when GitHub is available; this file is its recoverable human-readable mirror.

| Task | Status | Owner | Model/effort | Base SHA | Branch/worktree | Exact files | Claimed at |
|---|---|---|---|---|---|---|---|
| DOC-001 | active | root orchestrator | Sol/high | f5166c7 | `automate-research` / repository root | `.agents/skills/**`, `AGENTS.md`, `CONTEXT.md`, `docs/**`, documentation corrections in `README.md` and `DEPLOY_FREE.md` | 2026-08-22 |

Before adding a row, the orchestrator verifies dependencies and checks that no active row owns the same file or contract. On verification, change the task to `verified`, record the final SHA in its task card, and release the GitHub claim. Never delete claim history.
