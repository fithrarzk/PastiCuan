# CI-003: Efficient required gates and refresh triggers

- Status: active
- Priority: P0
- Lane: High-risk (production workflow)
- Owner/model: root implementation; Sol independent review
- Reasoning effort: high
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests,mocking}.md`, `docs/agents/delivery-lanes.md`, this card, `docs/specs/ci-cd-contract.md`, `docs/runbooks/ci-cd.md`, and exact owned files; maximum 40k tokens
- Retry ceiling: three red-green correction cycles
- Escalation condition: required context cannot remain stable; runtime path could be excluded; permission/concurrency/secret behavior changes; research gate or command semantics change
- Parallelism: one writer; two fresh read-only reviewers
- Base SHA: `93d308603e438bb8a7b41606523db2938e1cd320`
- Branch: `fix/CI-003-efficient-gates`
- Worktree: `../PastiCuan-wt/ci-003-efficient-gates`
- Depends on: verified DOC-004 (`93d3086`)
- File ownership: `.github/workflows/{ci,research-daily,test}.yml`, `scripts/ci/check_workflow_policy.py`, `tests/{test_ci_gates,test_workflow_policy}.py`, `docs/specs/ci-cd-contract.md`, `docs/runbooks/ci-cd.md`, `docs/tasks/{CI-003-efficient-gates,CLAIMS,ROADMAP,DOC-004-delivery-lanes}.md`
- Merge policy: autonomous

## Outcome

Run the full PR suite once while preserving all eight required contexts, and do
not dispatch production research for changes limited to documentation, tests,
agent metadata, or CI-only files.

## Non-goals

Do not change required context names or repository rulesets, generated-branch
validation, research schedules/manual dispatch, application behavior, formulas,
publication gates, secrets, migrations, or production evidence.

## Current evidence

PR #33 ran identical full suites in `core-tests/test` and
`pull-request-gates/unit`, each taking about 52 seconds. Its documentation-only
merge also dispatched production `research-daily` run `32753743338`.

## Invariants

- `test`, `unit`, `quality`, `workflow-policy`, `migration`, `container-smoke`,
  `manifest-validate`, and `security` remain exact current-head PR contexts.
- `unit` is the only ordinary PR full-suite producer; `test` fails unless
  `unit` succeeds.
- Runtime research/data/storage/operations changes still trigger main-push
  research; schedule and manual dispatch behavior is unchanged.

## Implementation contract

Move the `test` compatibility context into `ci.yml` as a lightweight dependent
job, remove the legacy duplicate workflow, and teach workflow policy to require
all eight jobs from the primary/generated producers. Add an explicit
`research-daily` main-push ignore list containing only reviewed non-runtime
paths, guarded by policy tests that reject broad/runtime exclusions.

## Acceptance tests

- Red tests prove the existing PR configuration has two full-suite producers
  and lacks the dependent `test` context in `ci.yml`.
- Red tests prove docs/tests/agent/CI-only paths are not excluded from the
  current production push trigger.
- Green tests prove one full-suite producer, all eight stable contexts, failing
  dependency propagation, and an exact safe refresh ignore list.
- Workflow policy, YAML validation, permissions, concurrency, timeouts, failure
  paths, full suite, research release check, and `git diff --check` pass.

## Rollout and rollback

Merge only with all eight current-head PR checks and independent review green.
After merge, verify `verify-main`; then verify a later docs-only merge produces
no `research-daily` run. Revert normally to restore the prior duplicate suite
and broad trigger; no production data or schema rollback is involved.

## Handoff

Record exact red/green commands, final SHA, review, PR/check/merge state,
post-merge workflow behavior, elapsed time, context use, and corrections.
