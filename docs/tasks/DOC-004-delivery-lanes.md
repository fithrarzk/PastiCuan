# DOC-004: Risk-tiered delivery lanes

- Status: review
- Priority: P0
- Lane: High-risk (agent contract)
- Owner/model: root implementation; Sol independent review
- Reasoning effort: high
- Context budget: `AGENTS.md`, `CONTEXT.md`, `docs/README.md`, `docs/agents/{autonomy,delivery-lanes,handoffs,worktrees}.md`, `docs/tasks/{README,CLAIMS,ROADMAP,DOC-003-program-status,DOC-004-delivery-lanes}.md`; maximum 30k tokens
- Retry ceiling: two documentation correction cycles
- Escalation condition: any proposal weakens research, evidence, publication, migration, secret, or production safeguards
- Parallelism: one writer; two fresh read-only reviewers
- Base SHA: `1f14012cf94eabdcdb9d3846bb1c956bd22de13b`
- Branch: `docs/DOC-004-delivery-lanes`
- Worktree: `../PastiCuan-wt/doc-004-delivery-lanes`
- Depends on: DOC-003
- File ownership: `AGENTS.md`, `docs/README.md`, `docs/agents/{autonomy,delivery-lanes,handoffs,worktrees}.md`, `docs/tasks/{README,CLAIMS,ROADMAP,DOC-003-program-status,DOC-004-delivery-lanes}.md`
- Merge policy: autonomous

## Outcome

Make the default delivery path one root-owned worktree with risk-proportional
planning, review, testing, time, and token budgets while retaining full controls
for high-risk research and production changes.

## Non-goals

Do not change application behavior, CI workflows, required checks, production
triggers, schemas, research formulas, safety gates, secrets, or the user-owned
`PROMPT-ORCHES.md` file. CI efficiency is the separate CI-003 concern.

## Current evidence

Recent PR checks complete in roughly one minute, while the prior process uses
separate implementation, Standards, Spec, and babysit agents for every task and
runs the full suite both locally and twice in PR CI. Worktree creation itself
takes seconds and protects the user-owned main checkout.

## Invariants

- Production truth, point-in-time, source, freshness, publication, and explicit
  unavailability rules do not change.
- Every change still uses an isolated branch/worktree and PR.
- High-risk work retains fresh independent review and complete verification.

## Implementation contract

Define one authoritative lane table with deterministic escalation, budgets,
stop rules, review, and verification. Make the surrounding agent, autonomy,
worktree, task-card, and handoff documents point to and consistently authorize
that policy. Keep CI behavior for the separate CI-003 task.

## Acceptance tests

- Fast, Standard, and High-risk lanes have deterministic escalation triggers,
  budgets, stop rules, review requirements, and verification levels.
- Agent, autonomy, worktree, task-card, and handoff guidance agree.
- All local Markdown links resolve and `git diff --check` passes.

## Rollout and rollback

This documentation-only contract applies to tasks claimed after merge. Revert
normally if it produces unsafe classification or worse delivery evidence.

## Handoff

- Lane/model: High-risk; root implementation with Sol/high independent review.
- Elapsed/context/corrections: under one hour through first review; under the
  30k task budget; one correction cycle.
- Focused Markdown link validation: all repository-local links resolved.
- `git diff --check`: passed.
- Full suite: 155/156 passed locally; the only failure was the pre-existing
  environment mismatch `yfinance 1.2.0 != 1.5.2`. Required PR CI installs the
  pinned requirements and remains required.
