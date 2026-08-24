# DOC-003: Shutdown-safe program status

- Status: verified
- Priority: P0
- Owner/model: orchestrator documentation; Sol independent review
- Reasoning effort: high
- Context budget: `AGENTS.md`, `CONTEXT.md`, `docs/README.md`, `docs/agents/handoffs.md`, `docs/tasks/{README,ROADMAP,CLAIMS,ING-002-filing-work-ledger}.md`, GitHub task/PR/workflow evidence, and exact owned files
- Retry ceiling: two documentation correction cycles for factual, status, ownership, or broken-link findings
- Escalation condition: production truth conflicts with accepted evidence, a user-owned local commit would need modification/publication, or the handoff would require claiming unverified recovery
- Parallelism: one orchestrator writer and two read-only reviewers
- Base SHA: `25c6f2e691e8757b54c76787fe57ff0d5da0f629`
- Branch: `docs/DOC-003-program-status`
- Worktree: `../PastiCuan-wt/doc-003-program-status`
- Depends on: ING-002
- File ownership: `docs/README.md`, `docs/status/2026-08-24-program-handoff.md`, `docs/tasks/{DOC-003-program-status,ING-002-filing-work-ledger,ING-003-skip-before-download,ROADMAP,CLAIMS}.md`
- Merge policy: autonomous

## Outcome

Record verified delivery through ING-002, unresolved production/rollout conditions, the unclaimed ING-003 design, workspace truth, and a safe shutdown/resume procedure.

## Non-goals

Do not implement or claim ING-003, apply migration 007, dispatch production workflows, claim research recovery, edit user-owned local commits, or publish `PROMPT-ORCHES.md`.

## Current evidence

`origin/main` is `25c6f2e`; PR #29 and merge verification `32571008743` passed. Production refresh `32571008822` failed closed. Shared local `main` contains user-owned commits `0518e21` and `9627336` ahead of `origin/main`.

## Invariants

- Production truth remains `origin/main` plus accepted Supabase evidence and signed snapshots.
- Merged code is not production schema or research recovery.
- User-owned local commits are described but never pushed, rewritten, or included.
- ING-003 remains ready and unclaimed.

## Implementation contract

Add one canonical dated handoff linked from the documentation index, update ING-002/claims evidence, add a decision-complete ING-003 card, and point the roadmap to the current handoff.

## Acceptance tests

- Every local Markdown link resolves.
- Merge/run/task evidence matches GitHub and `origin/main`.
- The handoff explicitly records production failures, unapplied migration 007, non-resumable ingestion, non-atomic publication, and unverified Railway deployment.
- `git diff --check` and focused documentation-adjacent tests pass.

## Rollout and rollback

Land as a documentation-only PR. Roll back with a normal revert; no production, data, schema, workflow, or secret change occurs.

## Handoff

Merged as `1f14012` through PR #31. All eight required PR checks and merge
verification run `32709997351` passed. The next production-roadmap task is
ING-003, which remains unclaimed.
