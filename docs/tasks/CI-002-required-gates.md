# CI-002: Required pull-request gates

- Status: verified
- Priority: P0
- Owner/model: Luna implementation, Sol security review
- Reasoning effort: high implementation, high review
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests,mocking}.md`, this card, `docs/specs/ci-cd-contract.md`, and the exact owned files; maximum 28k tokens
- Retry ceiling: four bounded implementation cycles; the fourth is authorized only for the final-review cross-job, SQL-ASCII repository, credential-bypass, and failure-path findings; security findings do not auto-waive
- Escalation condition: a required external service cannot run on GitHub's free runner or ruleset administration is unavailable
- Parallelism: one Luna implementation agent; one root integration owner; two later read-only reviewers. No nested writers.
- Base SHA: `693af474baa11d73ad41d116b626a1bb44e5ed3d`; synchronized through `64849127b06f6ea01a5c8352b82a11a36ce208fb`
- Branch: `feat/CI-002-required-gates`
- Worktree: `../PastiCuan-wt/ci-002-required-gates`
- Depends on: CI-001, CI-002A, CI-002B
- File ownership: `.github/workflows/test.yml`, `.github/workflows/validate-branch.yml`, `.github/workflows/ci.yml` (new), `.dockerignore` (new), `Dockerfile`, `requirements-ci.txt` (new), `scripts/ci/check_migrations.py` (new), `scripts/ci/check_workflow_policy.py` (new), `scripts/ci/validate_manifest.py` (new), `scripts/ci/check_security.py` (new correction seam), `scripts/ci/check_dependencies.sh` (new correction seam), `scripts/ci/container_smoke.sh` (new correction seam), `tests/test_ci_gates.py` (new), `tests/test_workflow_policy.py`, this task card, and `docs/tasks/CLAIMS.md` (root orchestrator only)
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

CI-002A merged as `a60a561`, restoring a supported dependency chain without an advisory waiver. CI-002B merged as `6484912`, fixing SQL-ASCII migration identity decoding at the storage boundary without weakening the exact gate. CI-002 merged through PR #22 as `88409306f0dbc6eae42a1759231118cf7667b469`; its final reviewed task head was `dc265f25029b6037369cdf8fe1ccbef5f5643df4`. The changed files are the owned workflows, container definition, CI requirements/helpers, gate tests, and this task record. Behavior now provides the legacy `test` context plus stable `unit`, `quality`, `workflow-policy`, `migration`, `container-smoke`, `manifest-validate`, and `security` contexts on ordinary pull requests and exact-head generated validation.

Local verification passed the clean Python 3.12 suite, compilation, research-release check, diff check, strict four-profile dependency audit, workflow policy, secret scan, manifest checks, Ruff, Mypy, shell syntax, real container probes, and six migrations applied twice with exact repository identity comparison in both UTF-8 and SQL-ASCII. Independent Standards and Spec reviews reported zero findings. On the real final-head PR, all eight required contexts passed. Generated validation run `32562878089` passed for the exact final head, while deliberate mismatched-SHA run `32562868244` failed the guard and all eight contexts. Ruleset `20977060` now requires all eight contexts with strict freshness and no bypass actors. Merge-SHA run `32563023464` passed compile, release policy, and the full test suite. Rollback is the documented workflow revert plus atomic restoration of the prior ruleset contexts; no production data or schema changed. Exact-SHA Railway linkage remains unavailable until DEP-001, and CI-002 does not claim research refresh recovery.
