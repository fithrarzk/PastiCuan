# DOC-002: Architecture and operational documentation

- Status: active
- Priority: P0
- Owner/model: Luna implementation, Sol independent review
- Reasoning effort: medium implementation, high review
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/domain-modeling/{SKILL,CONTEXT-FORMAT,ADR-FORMAT}.md`, this card, `docs/README.md`, `README.md`, `DEPLOY_FREE.md`, `docs/specs/{ci-cd-contract,ingestion-contract,snapshot-lifecycle}.md`, `docs/runbooks/stale-snapshot.md`, and exact owned files; maximum 24k tokens
- Retry ceiling: two documentation correction cycles; broken-link or contradicted-current-state findings are retryable
- Escalation condition: repository code and an accepted specification materially disagree and neither is explicitly marked planned/current
- Parallelism: one Luna documentation writer; one root integration owner; two later read-only reviewers. No nested writers.
- Base SHA: `693af474baa11d73ad41d116b626a1bb44e5ed3d`; synchronized through `88409306f0dbc6eae42a1759231118cf7667b469`
- Branch: `docs/DOC-002-architecture`
- Worktree: `../PastiCuan-wt/doc-002-architecture`
- Depends on: DOC-001
- File ownership: `docs/README.md`, `docs/architecture/system-map.md` (new), `docs/architecture/data-lifecycle.md` (new), `docs/architecture/reliability-boundaries.md` (new), `docs/reference/command-data-dictionary.md` (new), `docs/models/README.md` (new), `docs/runbooks/ci-cd.md` (new), `docs/runbooks/backfill.md` (new), `docs/runbooks/refresh.md` (new), `docs/runbooks/deployment.md` (new), `docs/runbooks/recovery.md` (new), `docs/runbooks/incident-response.md` (new), this task card, and root-orchestrator updates to `docs/tasks/CI-002-required-gates.md` and `docs/tasks/CLAIMS.md`
- Merge policy: autonomous

## Outcome

A new operator or agent can locate each production source of truth, domain owner, invariant, command, evidence store, test seam, and operating procedure without chat history.

## Non-goals

- Change `CONTEXT.md`, runtime behavior, analytics formulas, workflows, deployment settings, or research/publication gates.
- Present roadmap contracts as already implemented.
- Claim production recovery, validated analytics, exact-SHA Railway verification, atomic publication, cumulative discovery, or runtime-resumable ingestion.

## Current evidence

`docs/README.md` currently links the glossary, agent contract, roadmap, three specifications, and one stale-snapshot runbook. There is no architecture directory, command/data dictionary, model-card index, or end-to-end CI/CD, backfill, refresh, deployment, recovery, and incident documentation. Current code is production code only after merge to `origin/main`; production research remains accepted Supabase evidence plus signed published snapshots. IDX ingestion is storage-idempotent but not runtime-resumable before `ING-003`; publication is not atomic before `REL-001`; exact-SHA Railway verification is not established before `DEP-001`; analytics remain `SHADOW` until their later validation tasks.

## Invariants

- `CONTEXT.md` remains glossary-only and unchanged.
- Use canonical evidence and lifecycle terms from `CONTEXT.md`.
- Every page distinguishes current implemented behavior, accepted contract, and planned roadmap behavior.
- Never turn candidate snapshots into bot-readable production evidence by documentation claim.
- Never describe storage-idempotent ingestion as resumable.
- Operational procedures fail closed and preserve the last good snapshot.
- No credentials, provider bodies, private URLs, or secret values appear.

## Implementation contract

Document the system map, data lifecycle, and reliability boundaries with direct links to owning code/specs. Add a command/data dictionary naming interface, owner, inputs, outputs, evidence identity, availability behavior, and public test seam. Add a model-card index that labels existing formulas and future model cards without implying validation. Add concise runbooks for CI/CD, backfill, refresh, deployment, recovery, and incident response; each must state prerequisites, procedure, verification, fail-closed stop condition, and rollback/last-good behavior. Update `docs/README.md` as the navigable entry point. Do not edit `CONTEXT.md` or create an ADR unless the task discovers a genuinely hard-to-reverse, surprising trade-off; escalate that contradiction instead of inventing one.

## Acceptance tests

- All owned Markdown links resolve locally, including anchors used by the new index.
- `rg` finds explicit implemented/planned status and the warnings for non-resumable ingestion, non-atomic publication, unverified Railway linkage, and unvalidated analytics.
- Each requested architecture/reference/runbook subject has one canonical page linked from `docs/README.md`.
- Commands and data stores point to real source paths and use `CONTEXT.md` vocabulary.
- `CONTEXT.md` has no diff; no source code, workflow, or research artifact changes.
- `git diff --check` and the repository full verification commands pass.

## Rollout and rollback

Publish through the documentation PR. No production action is required. Roll back by reverting the documentation commit; runtime and evidence are unchanged.

## Handoff

The branch adds the architecture, lifecycle, reliability, command/data, model-index, and six operational runbook pages listed in file ownership, updates the documentation index, and records the completed CI-002 rollout. An inline local-link validator checked all 13 owned Markdown files and found every local path and anchor resolvable. In a clean Python 3.12 environment, compilation passed, all 120 tests passed, `check-research-release` returned the accepted research release, and `git diff --check` passed. `CONTEXT.md`, runtime code, workflows, research artifacts, formulas, gates, and production state are unchanged by DOC-002.

The documentation deliberately retains these limitations: ingestion is storage-idempotent but not runtime-resumable, publication is not atomic, exact-SHA Railway linkage is not verified, and analytics remain unvalidated `SHADOW` research. PR URL, reviewed head, required-check results, merge SHA, and post-merge verification must be recorded in the final orchestrator handoff. With CI-002 verified, REG-001 and ING-001 are the next dependency-ready roadmap tasks; their separate concerns and file ownership must remain separate.
