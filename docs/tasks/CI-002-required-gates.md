# CI-002: Required pull-request gates

- Status: proposed
- Priority: P0
- Owner/model: Luna implementation, Sol security review
- Reasoning effort: medium implementation, high review
- Context budget: `AGENTS.md`, this card, `docs/specs/ci-cd-contract.md`, `.github/workflows/**`, dependency and migration files; maximum 28k tokens
- Retry ceiling: three bounded implementation cycles; security findings do not auto-waive
- Escalation condition: a required external service cannot run on GitHub's free runner or ruleset administration is unavailable
- Parallelism: one workflow writer; independent migration/container fixture agents may work only in disjoint files
- Base SHA: set from `origin/main` when claimed
- Branch: `feat/CI-002-required-gates`
- Worktree: `../PastiCuan-wt/ci-002-required-gates`
- Depends on: CI-001
- File ownership: `.github/workflows/test.yml`, new CI workflows/scripts, dependency lock/config, CI-only database/container fixtures
- Merge policy: autonomous

## Outcome

Replace the single coarse `test` gate with stable, reproducible checks for code, workflows, database compatibility, container startup, manifests, and supply-chain risk.

## Non-goals

- Apply production migrations or deploy Railway.
- Make network-dependent research calculations part of ordinary PR CI.

## Implementation contract

Implement the named checks from `docs/specs/ci-cd-contract.md`. Pin action SHAs and tool versions. Use ephemeral PostgreSQL. Conditional checks must still produce a deterministic successful status when not applicable so rulesets do not wait forever.

## Acceptance tests

- A normal code PR gets one PR-triggered suite without duplicate push execution.
- Intentional unit, workflow, migration, container, manifest, and secret/dependency failures each fail their named check.
- Clean database migrations and repository integration pass without production credentials.
- Required names are documented for the ruleset.

## Rollout and rollback

Land workflows before replacing the old required check. Observe one real PR, then update the ruleset and remove the compatibility gate in a later commit. Revert workflows if runner limits make the suite unavailable; never leave a required check with no producer.

## Handoff

Record timings, cache behavior, check names, ruleset state, failure fixtures, and runner-cost estimate.
