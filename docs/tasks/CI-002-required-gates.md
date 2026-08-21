# CI-002: Required pull-request gates

- Status: active
- Priority: P0
- Owner/model: Luna implementation, Sol security review
- Reasoning effort: high implementation, high review
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests,mocking}.md`, this card, `docs/specs/ci-cd-contract.md`, and the exact owned files; maximum 28k tokens
- Retry ceiling: three bounded implementation cycles; security findings do not auto-waive
- Escalation condition: a required external service cannot run on GitHub's free runner or ruleset administration is unavailable
- Parallelism: one Luna implementation agent; one root integration owner; two later read-only reviewers. No nested writers.
- Base SHA: `693af474baa11d73ad41d116b626a1bb44e5ed3d`
- Branch: `feat/CI-002-required-gates`
- Worktree: `../PastiCuan-wt/ci-002-required-gates`
- Depends on: CI-001
- File ownership: `.github/workflows/test.yml`, `.github/workflows/validate-branch.yml`, `.github/workflows/ci.yml` (new), `.dockerignore` (new), `Dockerfile`, `requirements-ci.txt` (new), `scripts/ci/check_migrations.py` (new), `scripts/ci/check_workflow_policy.py` (new), `scripts/ci/validate_manifest.py` (new), `scripts/ci/check_security.py` (new correction seam), `scripts/ci/container_smoke.sh` (new correction seam), `tests/test_ci_gates.py` (new), `tests/test_workflow_policy.py`, this task card, and `docs/tasks/CLAIMS.md` (root orchestrator only)
- Merge policy: autonomous

## Outcome

Replace the single coarse `test` gate with stable, reproducible checks for code, workflows, database compatibility, container startup, manifests, and supply-chain risk.

## Non-goals

- Apply production migrations or deploy Railway.
- Make network-dependent research calculations part of ordinary PR CI.

## Current evidence

At the 2026-08-22 audit, `.github/workflows/test.yml` only compiled Python, checked the research release, and ran unit tests. There was no workflow-policy, real-PostgreSQL migration/integration, container startup, manifest semantic, secret, or dependency gate.

CI-001 is verified at `693af47`: exact-head dispatch run `32523578280` succeeded and mismatched-SHA run `32523704901` failed closed. The active ruleset still requires only `test`, Actions permit all actions without repository-level SHA pinning, and default workflow permissions are write. CI-002 must establish least privilege in each owned workflow and retain the legacy producer until the replacement gates are observed on a real PR.

## Invariants

- CI uses no production database, R2, Telegram, signing, or Railway credential.
- A check name configured in the ruleset always has a producer.
- Conditional gates return an explicit not-applicable success rather than disappearing.
- Research formulas and publication policy are unchanged by this task.
- Do not trade deterministic coverage for network-dependent PR tests.

## Implementation contract

Implement `unit`, `quality`, `workflow-policy`, `migration`, `container-smoke`, `manifest-validate`, and `security` from `docs/specs/ci-cd-contract.md` on GitHub-hosted free runners. Use immutable action SHAs, pinned CI tool versions, explicit timeouts, concurrency cancellation, and least-privilege permissions. Use an ephemeral PostgreSQL service for clean-database up-migration, checksum-ledger, and repository compatibility checks. Build the real `Dockerfile`, start the webhook container, and probe `/` and `/ready`. Keep the conditional manifest job present and successful when paths are not applicable. Ensure ordinary feature branches execute the suite once through `pull_request`; preserve explicit exact-head validation for bot-generated branches without discovery recursion. Keep network research and all production credentials out of PR CI. Do not alter analytics formulas, evidence gates, migrations, or publication behavior.

Public test seams are workflow job/check names, executable CI helper command exit codes, clean PostgreSQL migration state, container HTTP health endpoints, and `python -m unittest` behavior. Tests observe those seams without private implementation mocks.

## Acceptance tests

- A normal code PR gets one PR-triggered suite without duplicate push execution.
- Intentional unit, workflow, migration, container, manifest, and secret/dependency failures each fail their named check.
- Clean database migrations and repository integration pass without production credentials.
- Required names are documented for the ruleset.
- Workflow YAML parses; every job has a timeout; workflow permissions are read-only unless a narrower write permission is demonstrably required; all third-party actions are SHA-pinned.
- The generated-branch dispatch validates the requested remote head and produces all stable required names without triggering discovery.
- Focused tests, the repository full verification commands, and `git diff --check` pass.

## Rollout and rollback

Land workflows while retaining the old `test` producer. Observe all new checks on the real task PR, then the orchestrator may atomically add the seven stable names to the ruleset while retaining `test`; removal of the compatibility gate is a separately reviewed follow-up after generated-branch proof. Roll back by reverting the workflow commit and restoring the prior ruleset contexts; no production data or schema changes occur.

## Handoff

Record timings, cache behavior, check names, ruleset state, failure fixtures, and runner-cost estimate.
