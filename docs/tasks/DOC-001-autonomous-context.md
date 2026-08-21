# DOC-001: Autonomous repository context

- Status: active
- Priority: P0
- Owner/model: root orchestrator, Sol
- Reasoning effort: high
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/{domain-modeling,file-pr,code-review,babysit-pr,tdd}`, `README.md`, `DEPLOY_FREE.md`, `docs/**`
- Retry ceiling: two correction/review cycles; deterministic documentation checks may rerun
- Escalation condition: authentication or protected-platform control prevents PR/merge
- Parallelism: two read-only reviewers; orchestrator is the only writer
- Base SHA: `f5166c792d4e9b33fc5d4201476565c06689fd4e`
- Branch: `automate-research`
- Worktree: repository root for this bootstrap only
- Depends on: none
- File ownership: `.agents/skills/**`, `AGENTS.md`, `CONTEXT.md`, `docs/**`, `README.md`, `DEPLOY_FREE.md`
- Merge policy: autonomous

## Outcome

Give future agents one trustworthy vocabulary, authority model, task graph, worktree protocol, model-routing policy, CI/ingestion/publication contracts, and evidence-based handoff format.

## Non-goals

- Implement roadmap code or modify production data.
- Weaken publication gates or claim the stale production incident is recovered.

## Current evidence

The 2026-08-22 analytics, CI/CD, and documentation audits are summarized in `docs/tasks/ROADMAP.md`. Existing installed skills contained unrelated-repository instructions and current deployment prose overstated automation.

## Invariants

- `CONTEXT.md` is glossary-only.
- `origin/main` is production code truth.
- Research remains point-in-time, `RESEARCH_ONLY`, and fail-closed.
- Standing autonomy never bypasses credentials, required checks, or destructive-operation safeguards.

## Acceptance tests

- All relative Markdown links resolve.
- `git diff --check` passes.
- Full repository compilation, unit suite, and research-release check pass.
- Independent standards and spec reviews have no blocking findings.

## Rollout and rollback

Squash-merge after current-head checks. Documentation rollback reverts this PR; it does not alter production evidence.

## Handoff

Complete after PR, merge, and post-merge documentation visibility are verified.
