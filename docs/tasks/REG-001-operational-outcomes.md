# REG-001: Stable research-job outcomes and production regression locks

- Status: active
- Priority: P0
- Owner/model: Luna implementation from Sol design; Sol independent review
- Reasoning effort: high implementation, high review
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests,mocking}.md`, this card, `docs/runbooks/incident-response.md`, `docs/specs/ci-cd-contract.md`, and exact owned files; maximum 22k tokens
- Retry ceiling: three bounded red-green-refactor cycles; retry only deterministic unit/workflow failures
- Escalation condition: a schema migration, new production grant, formula/publication-gate change, or external consumer beyond `research-daily` becomes necessary
- Parallelism: one Luna writer under the serialized `operations/research_cli.py`/`storage/repository.py` integration owner; later read-only reviewers only
- Base SHA: `491e5154690ab7d2e78c81239140d92a66b6613a`
- Branch: `fix/REG-001-operational-outcomes`
- Worktree: `../PastiCuan-wt/reg-001-operational-outcomes`
- Depends on: CI-002
- File ownership: `operations/job_outcomes.py` (new), `operations/research_cli.py`, `analysis/contracts.py`, `storage/repository.py`, `.github/workflows/research-daily.yml`, `tests/test_reg_001.py` (new), `tests/test_workflow_policy.py`, this task card, and `docs/tasks/CLAIMS.md` (root orchestrator only)
- Merge policy: autonomous

## Outcome

Give research automation a stable, machine-readable, redacted outcome/exit contract; prove non-finite values cannot escape snapshot, report, stdout, or JSONB boundaries; and fail preflight explicitly when the scheduled-job role cannot read the migration ledger.

## Non-goals

- Apply migrations or grants; change formulas, thresholds, freshness, source quality, risk, or publication policy; promote/publish a model; redesign provider retry or durable ingestion; or retrofit every legacy CLI subcommand.
- Claim production recovery from tests or merge.

## Current evidence

The CLI currently collapses expected unavailability, policy rejection, privilege/configuration failures, and unexpected infrastructure errors into coarse `FAILED`/exit 2 behavior, and copies raw exception text into reports. Migration preflight queries the ledger without first distinguishing absence from missing privileges. Snapshot sanitization is tested only at one quant seam; reports and repository JSONB boundaries are not locked.

## Invariants

- Last-good snapshots remain active for every non-success. `WAITING`, `UNAVAILABLE`, and `POLICY_GATE` publish nothing.
- Missing/non-finite numeric evidence becomes JSON `null`, never zero, text, or an estimate, and cannot become eligible through sanitization.
- Infrastructure failure never masquerades as evidence unavailability. Unknown exception text, credentials, provider bodies, and connection details never enter reports/stdout/metrics.
- Preflight is read-only and applies no migration or grant. Existing database status constraints and research/publication semantics remain unchanged.

## Implementation contract

Add typed stable outcomes `SUCCEEDED`, `NOOP`, `WAITING`, `UNAVAILABLE`, `POLICY_GATE`, and `INFRASTRUCTURE` with exits `0`, `0`, `10`, `20`, `30`, and `40`; argparse retains exit 2. Map them to existing persisted statuses (`SUCCEEDED`; `DEGRADED` for waiting/unavailable; `FAILED` for policy/infrastructure) and store allowlisted stable code/stage/retryability/summary/action/details only. Use explicit branches or typed failures, never message matching. Early current-session timing is `WAITING`; final missing/stale evidence is `UNAVAILABLE`; readiness/non-PRIMARY publication rejection is `POLICY_GATE`; configuration, ledger, database/filesystem/dependency, and unknown failures are `INFRASTRUCTURE`. The workflow normalizes only exit 10 to a visible successful scheduled attempt.

Add a read-only repository migration preflight that distinguishes ledger absence, missing schema/table privileges, and required-version absence without exposing identity or connection data. Add one strict JSON encoder that recursively sanitizes non-finite Python/NumPy values and uses `allow_nan=False` at reports, CLI summaries, and repository JSONB boundaries.

## Acceptance tests

- Exhaustive outcome-to-exit/persisted-status tests, including success and idempotent no-op.
- Early market delay returns exit 10/DEGRADED and performs no build/publish; the final condition is exit 20, not generic failure.
- Empty point-in-time inputs or unavailable evidence return 20; readiness or non-PRIMARY publication gates return 30 without gate bypass.
- Ledger privilege denial, ledger absence, missing versions, timeout, and unknown failures have distinct stable infrastructure codes and exit 40 before provider/build/publication calls.
- Injected URL/password/private-key/provider-body markers appear nowhere in report, stdout, workflow summary, or recorded metrics.
- Nested Python/NumPy NaN and infinities become JSON null at quant, scan, report, and JSONB seams; checksum/readiness semantics remain unchanged.
- Only exit 10 is normalized by workflow policy; 20/30/40 fail. Existing SQL-ASCII tests remain green.
- Focused tests plus compilation, full suite, release check, workflow policy, security scan, and diff check pass.

## Rollout and rollback

Land through the reviewed PR; do not dispatch production research as part of rollout. Roll back with a normal revert. No schema, data, grant, formula, or published evidence changes require rollback. Production verification observes the merge-SHA workflow and its redacted summary without claiming research recovery.

## Handoff

Record commits, exact files, focused/full commands and results, independent reviews, PR/current-head checks, merge/post-merge evidence, limitations, and the next dependency-ready task.
