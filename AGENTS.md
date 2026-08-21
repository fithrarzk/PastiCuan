# PastiCuan Agent Contract

## Mission and non-negotiable safety

PastiCuan is a `RESEARCH_ONLY`, point-in-time IDX system. Accuracy, causality, and explicit unavailability take priority over output coverage.

- Never weaken freshness, source-quality, point-in-time, coverage, publication, or risk gates to make a command look available.
- Never replace missing official evidence with an estimate or Yahoo fundamental data.
- Candidate snapshots are never bot-readable production evidence.
- Formula or gate changes require a reviewed release revision and tests.
- Model promotion, production schema application, secret rotation, and destructive data operations require an explicit task authorization even in autonomous mode.
- Never expose credentials, private keys, database URLs, provider bodies, or Telegram secrets.

Read [CONTEXT.md](CONTEXT.md) before planning. Use its terms in code, tests, task cards, PRs, and operational reports.

## Establish truth before work

Production code is `origin/main`; production research is accepted Supabase evidence plus signed published snapshots. A local branch, manifest, candidate artifact, or cached bot process is not production truth.

Every task starts with:

```bash
git status --short
git branch --show-current
git fetch origin
git merge-base HEAD origin/main
git log -5 --oneline origin/main
```

Then inspect only the relevant workflow state, task card, spec, and files. Use `rg` and bounded file slices before opening large modules. Do not claim a production fix from local tests alone.

## Task and worktree discipline

- One task card, one concern, one branch, one worktree, and one PR.
- Worktrees live outside the repository at `../PastiCuan-wt/<task-id>-<short-name>`.
- Branches use `<type>/<task-id>-<short-name>` where type is `fix`, `feat`, `refactor`, `test`, `docs`, or `ops`.
- Record task ID, owner, model, base SHA, dependencies, and file ownership before editing.
- Never let two active writers own the same file or shared contract. Parallelize only independent file sets.
- Agents must not assume another worktree's uncommitted changes exist.
- Sync with `origin/main` before final verification; coordinate before resolving overlapping changes.
- Preserve user changes and unrelated dirty files.

Domain ownership:

- `data/`: acquisition, provider policy, parsing, and input validation.
- `storage/`: persistence, migrations, roles, and point-in-time queries.
- `analysis/`: models, factors, scoring, ranges, snapshots, and outcome logic.
- `operations/`: orchestration, release policy, health, and job interfaces.
- `bot.py`, `bot_webhook.py`, `telegram_utils/`, `ui/`: delivery and presentation only.
- `.github/workflows/`: CI/CD and scheduled automation.
- `docs/`: domain, specs, tasks, runbooks, decisions, and handoffs.

## Model routing and token budget

- Use **Sol** for architecture, financial/statistical reasoning, incidents, migrations, contracts, task decomposition, release-risk review, and merge arbitration.
- Use **Luna** for a bounded accepted task card: test-first implementation, fixtures, mechanical refactors, documentation, and focused verification.
- Use a fresh reviewer agent for spec and standards review; use a babysit agent only after a PR exists.
- Give each implementation agent a one-page task card and exact file list, not conversation history.
- Read `AGENTS.md`, `CONTEXT.md`, the task card, and only its linked specs/runbooks.
- Handoffs replace rediscovery: include commits, changed files, commands, results, limitations, and next task.

Use stronger models when a mistake can create look-ahead bias, incorrect financial semantics, schema loss, secret exposure, or production publication. Do not spend strong-model context on formatting or repetitive edits.

## Implementation and verification

- Use TDD for behavior changes: reproduce the failure, make the smallest implementation pass, then refactor.
- Tests must cover complete, missing, stale, quarantined, and conflicting evidence where relevant.
- Point-in-time tests must prove evidence cannot appear before `available_at`.
- Focused tests run during development; the full suite and compilation run before handoff:

```bash
python -m compileall -q analysis data storage operations telegram_utils bot.py bot_webhook.py
python -m unittest discover -s tests -v
python -m operations.research_cli check-research-release
git diff --check
```

- Workflow changes also require syntax validation, least-privilege review, timeout/concurrency analysis, and a failure-path test or dry-run.
- Database changes require matching up/down migrations, role grants, compatibility analysis, and a documented rollout/rollback.
- Never describe storage-idempotent ingestion as resumable unless accepted inputs are skipped before download and progress survives process termination.

## Git, review, and autonomous merge

- Never commit directly to `main`; commit coherent changes to the task branch.
- Review the diff against `origin/main` and the task spec before filing a PR.
- PRs use concise Conventional Commit titles and explain outcome and reason. Never add an AI tool as author or co-author.
- Required checks must pass on the current head. A missing required check is not green.
- Use squash merge and delete the remote task branch.
- The repository owner has granted standing authorization for agents to inspect the repository and GitHub state; create worktrees and branches; edit code, tests, workflows, and documentation; run tests; commit; push; open and update PRs; respond to review; enable or use auto-merge; squash-merge green PRs; delete merged task branches; run non-destructive workflows; deploy already-reviewed code; and perform read-only production verification. Do not pause for confirmation for these routine task actions.
- Autonomous merge is allowed when the task card says `merge_policy: autonomous`, required checks and independent review are green, and the change remains inside the standing authorization above.
- Standing authorization is not permission to bypass platform approval prompts or safeguards. It excludes revealing or rotating secrets, destructive data/schema operations, force pushes, lowering research/safety gates, publishing or promoting an unvalidated model, spending money, and changing repository or cloud access for people. These require a narrowly scoped explicit authorization or must fail closed.
- Workflow-driven additive migrations may run autonomously only after their migration task was independently reviewed, CI proved a clean-database apply and compatibility, a verified backup exists, and the task card explicitly declares the rollout. Automated rollback is forward-fix or last-good deployment; never execute destructive down migrations in production.
- After merge, verify the triggered workflow and production evidence. A merged PR is not a completed operational task.
- If GitHub authentication, permissions, an external service, or human-reviewed official data blocks completion, report it explicitly; never fabricate success.

Use the repository `file-pr`, `code-review`, and `babysit-pr` skills when their triggers apply.

The complete authority matrix and failure policy are in [docs/agents/autonomy.md](docs/agents/autonomy.md).

## Handoff and done definition

Every handoff must include:

- Task ID, outcome, base SHA, and final SHA.
- Files changed and behavior changed.
- Tests/commands run and exact results.
- PR, checks, review, merge, and post-merge workflow state.
- Data or production evidence when applicable.
- Known limitations, unresolved decisions, rollback, and recommended next task.

A task is done only when code, tests, documentation, review, merge, and required post-merge verification are complete. See [docs/agents/handoffs.md](docs/agents/handoffs.md).
