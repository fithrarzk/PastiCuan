# CI-001: Validate generated pull requests

- Status: review
- Priority: P0
- Owner/model: Luna implementation from Sol contract
- Reasoning effort: medium
- Context budget: `AGENTS.md`, `CONTEXT.md`, this card, `docs/specs/ci-cd-contract.md`, `.github/workflows/{idx-filings,test}.yml`; maximum 18k tokens
- Retry ceiling: two implementation cycles and two CI reruns; retry only runner/network failures
- Escalation condition: repository rules reject the check produced by an explicit dispatch on the tested commit
- Parallelism: one implementation agent, one independent reviewer; serialize `.github/workflows/idx-filings.yml`
- Base SHA: `b9f889e549555a8d0d5f431997b3bce2f2b07575`
- Branch: `fix/CI-001-generated-pr-checks`
- Worktree: `../PastiCuan-wt/ci-001-generated-pr-checks`
- Depends on: OPS-001
- File ownership: `.github/workflows/idx-filings.yml`, `.github/workflows/validate-branch.yml`, `tests/test_workflow_policy.py`, this task card, `docs/tasks/CLAIMS.md`
- Merge policy: autonomous

## Outcome

Every manifest PR created with `GITHUB_TOKEN` receives the required test result on its exact head SHA.

## Non-goals

- Introduce a GitHub App or long-lived PAT.
- Change research calculations, import behavior, or branch-rule gates.

## Current evidence

The 2026-08-22 audit found that generated manifest PRs are pushed with `GITHUB_TOKEN`; ordinary recursive workflow triggers are suppressed, leaving the required `test` check absent. The open generated PR at audit time was therefore unmergeable despite having a valid branch.

## Invariants

- Validate the exact generated branch head SHA.
- Do not add a PAT, paid service, recursive discovery trigger, or production secret to validation.
- A missing or failed check remains blocking.
- Keep `main` protected by PRs and preserve fail-closed research behavior.

## Implementation contract

Choose the free explicit-dispatch design: after pushing the generated branch, dispatch a reusable branch-validation workflow at that branch. Grant only required Actions/contents permissions. The validation workflow uses stable check names, no write token, and cannot call discovery or create another PR.

## Acceptance tests

- A generated test branch produces the required check on its head SHA.
- A failing test blocks merge and reports its command.
- Dispatch cannot recurse into discovery.
- A repeated discovery updates one PR and triggers validation once for the new SHA.
- Workflow syntax/policy and the existing 79+ tests pass.

## Rollout and rollback

Merge, run one dry-run discovery branch, and verify ruleset recognition before enabling auto-merge. Roll back by reverting the workflow change; no data changes occur.

## Handoff

- Implementation commits: `7b7c913`, `2feae90`
- Focused workflow-policy tests: 5 passed.
- Full suite: 84 passed.
- YAML parse, isolated compile, research-release integrity, and `git diff --check`: passed.
- Independent standards and spec reviews: no blockers after immutable action pinning.
- PR checks, generated-branch dry run, merge, and post-merge verification remain pending.
