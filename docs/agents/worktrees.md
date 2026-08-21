# Worktrees and Model Routing

## Orchestrator workflow

The orchestrator owns the dependency graph, task assignment, file ownership, PR ordering, and production verification. It does not ask implementation agents to rediscover the roadmap.

For each ready task:

1. Fetch `origin/main` and record its SHA in the task card.
2. As the only claim writer, record the task and exact file ownership in `docs/tasks/CLAIMS.md`; when GitHub is available, atomically assign its task issue and add `status:claimed` before creating a worktree.
3. Create `../PastiCuan-wt/<task-id>-<short-name>` from `origin/main`.
4. Give the agent only `AGENTS.md`, `CONTEXT.md`, its task card, linked specs, and exact files.
5. Require a test-first commit and structured handoff.
6. Run independent review, file the PR, monitor current-head checks, and squash merge when policy allows.
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

Implementation agents never self-claim. A claim is valid only when the orchestrator records it against the current `origin/main` SHA. If two sessions propose the same task, the first GitHub issue assignment wins; the other stops before editing. The committed registry is human-readable recovery state, while the GitHub assignment is the coordination lock.

## Routing

Use Sol for task decomposition, domain and schema decisions, finance/statistics, incidents, review, and merge arbitration. Use Luna for an accepted bounded task card, test-first implementation, fixtures, repetitive documentation, and focused refactors.

An implementation agent does not merge its own work. A separate reviewer compares the task branch against its base and task card. A babysit agent monitors only current-head feedback and checks.

## Context efficiency

- Task cards should fit on one page and link to exact specifications.
- Prefer paths, symbols, failing outputs, and acceptance tests over narrative history.
- Use `rg` before broad reads.
- Never send secrets, entire logs, database dumps, or unrelated diffs to an agent.
- Finish with the handoff template so successors do not repeat exploration.
