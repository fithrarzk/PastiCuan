# Worktrees and Model Routing

## Orchestrator workflow

The orchestrator owns the dependency graph, task assignment, file ownership, PR ordering, and production verification. It does not ask implementation agents to rediscover the roadmap.

For each Fast task:

1. Fetch `origin/main` and record the base SHA in the task note.
2. Confirm ownership cannot collide; claim it only when it is roadmap work or
   another active writer could overlap.
3. Create one task branch and external worktree from `origin/main`.
4. Implement with the root agent, run focused validation, and self-review the
   diff against the task note.
5. File one PR, require current-head CI, squash merge, and verify only relevant
   post-merge behavior.

For each ready Standard or High-risk task:

1. Fetch `origin/main` and record its SHA in the task card.
2. As the only claim writer, record the task and exact file ownership in `docs/tasks/CLAIMS.md`; when GitHub is available, atomically assign its task issue and add `status:claimed` before creating a worktree.
3. Create `../PastiCuan-wt/<task-id>-<short-name>` from `origin/main`.
4. Give the agent only `AGENTS.md`, `CONTEXT.md`, its task card, linked specs, and exact files.
5. Require test-first implementation for behavior changes and a structured handoff.
6. Run the review required by the selected [delivery lane](delivery-lanes.md), file the PR, monitor current-head checks, and squash merge when policy allows.
7. Verify post-merge workflows and production evidence before closing the task.

Example:

```bash
git fetch origin
git worktree add ../PastiCuan-wt/ing-001-resume -b feat/ING-001-resume origin/main
```

## Parallelism

Safe parallel work has disjoint ownership. Examples:

- ingestion implementation in `data/` plus focused repository methods;
- independent bot contract tests;
- documentation/runbook work;
- read-only analytics or CI audits.

Serialize changes to shared snapshot contracts, `operations/research_cli.py`, migrations, formula releases, and the same workflow file. The orchestrator resolves cross-task interfaces before parallel work begins.

Implementation agents never self-claim. A roadmap claim is valid only when the orchestrator records it against the current `origin/main` SHA. If two sessions propose the same task, the first GitHub issue assignment wins; the other stops before editing. The committed registry is human-readable recovery state, while the GitHub assignment is the coordination lock. A non-roadmap Fast task needs a claim only when ownership could collide.

## Routing

Use Sol for task decomposition, domain and schema decisions, finance/statistics, incidents, review, and merge arbitration. Use Luna for an accepted bounded task card, test-first implementation, fixtures, repetitive documentation, and focused refactors.

Fast and Standard tasks are implemented and integrated by one root agent. A
fresh reviewer compares High-risk work against its base and task card. Use a
babysit agent only when CI or review is long-running; short checks are polled
directly.

## Context efficiency

- Task cards should fit on one page and link to exact specifications.
- Prefer paths, symbols, failing outputs, and acceptance tests over narrative history.
- Use `rg` before broad reads.
- Never send secrets, entire logs, database dumps, or unrelated diffs to an agent.
- Finish with the handoff template so successors do not repeat exploration.
