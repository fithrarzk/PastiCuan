# OPS-002: Serialize import and research orchestration

- Status: review
- Priority: P0
- Owner/model: Codex ticket agent; Sol/high
- Delivery lane: High-risk (production workflow and database-lock contract)
- Reasoning effort: high
- Context budget: `AGENTS.md`, `CONTEXT.md`, TDD/Supabase/Postgres skills,
  this card, `docs/specs/{ci-cd,ingestion}-contract.md`,
  `docs/runbooks/{backfill,refresh}.md`, and exact owned files; maximum 60k
  tokens
- Retry ceiling: three correction cycles
- Escalation: any migration/schema/grant, production database access, secret or
  environment change, destructive action, weakened evidence/readiness/publication
  gate, or lock design that requires serializing the accepted Filing shards
- Parallelism: one ticket agent; OBS-001 remains the sole owner of
  `operations/research_cli.py`, `storage/repository.py`, readiness code/tests,
  and its runbooks; two fresh read-only reviewers only on the final exact head
- Base SHA: `02475e6f8d6a712d883ef49ec4415639c1609012`
- Branch/worktree: `feat/OPS-002-serialize-orchestration` /
  `../PastiCuan-wt/ops-002-serialize-orchestration`
- Issue: #51
- Depends on: verified ING-004 (`9aeb54f`), documented on current `origin/main`
- File ownership: `operations/production_db_lock.py` (new),
  `tests/test_production_db_lock.py` (new),
  `.github/workflows/{idx-filings,research-daily,research-validation,backup}.yml`,
  `scripts/ci/check_workflow_policy.py`, `tests/test_workflow_policy.py`, and
  this card. Final status documentation is a separate post-merge documentation
  PR after OBS-001 releases its overlapping `docs/tasks/CLAIMS.md` ownership.
- Public seams: `python -m operations.production_db_lock --mode <mode> -- <command>`
  and the four production workflow definitions above
- Merge policy: autonomous squash merge only after complete local verification,
  fresh independent zero-finding Standards and Spec reviews on the final exact
  head, and all required current-head checks

## Outcome and boundary

Make the reviewed manifest path execute in causal order: validate the checked-in
manifests, import with the existing durable shard contract, confirm durable
aggregate readiness, then request exactly one research refresh. Coordinate every
workflow that carries the production writer credential through one stable
PostgreSQL advisory-lock namespace. Filing shards use the shared mode so their
accepted bounded parallelism remains intact; research, validation, backup,
source ingestion, and aggregate readiness use the exclusive mode.

This task changes orchestration only. It does not change evidence eligibility,
freshness, source quality, point-in-time selection, readiness thresholds,
coverage, publication, risk, release, promotion, formulas, provider policy,
accepted/quarantined evidence, or database schema. Migrations 007 and 008 remain
unapplied and production import remains fail-closed until its separately reviewed
rollout gates pass.

## Accepted design

1. A bounded command wrapper opens a direct or session-compatible writer
   connection, enables autocommit, acquires a fixed two-key session advisory lock,
   runs one child command, and always releases/closes. Shared and exclusive modes
   use matching acquire/unlock functions. A timeout exits with a stable diagnostic
   without running the child; child exits are propagated unchanged.
2. Every workflow exposing `SUPABASE_WRITER_DATABASE_URL`, including backup,
   invokes database work through the wrapper. Import shards use shared mode;
   every other production database command uses exclusive mode. Existing workflow
   concurrency, permissions, pinned actions, timeouts, and fail-closed exits stay
   intact.
3. `idx-filings` validates both checked-in manifests before source ingestion or
   Filing import, preserves the eight deterministic shards, treats successful
   aggregate-only durable progress as import readiness, and contains one guarded
   `research-daily.yml` dispatch. Pure manifest pushes are ignored by the direct
   research push trigger so they cannot create a duplicate concurrent refresh.
4. Workflow policy rejects an unwrapped production database command, an unsafe
   lock mode, duplicate refresh dispatch, missing validation/readiness ordering,
   or a research trigger that no longer excludes pure manifest updates.

## Implementation evidence — 2026-09-14

- TDD slices cover exclusive/shared acquisition, bounded polling and timeout,
  stable exit `75`, child exit propagation, child/unlock failures with
  unconditional session close, autocommit, CLI argument forwarding, and a
  disposable-PostgreSQL shared-vs-exclusive seam (skipped without the task
  database URL).
- Workflow tests cover source/Filing validation ordering, shared Filing shards,
  exclusive aggregate/research/validation/backup writers, one guarded refresh,
  manifest push suppression, and rejection of unwrapped writer commands.
- Complete verification passed with Python 3.12-compatible pinned requirements:
  200 unit tests `OK` with four pre-existing disposable-DB skips; compileall;
  research-release check (revision 2 and unchanged calculation digest);
  workflow policy; tracked-source security scan; YAML parsing; Ruff; mypy; and
  `git diff --check`.
- No Supabase MCP or production database query/mutation occurred. Migrations
  007 and 008 remain unapplied; research remains SHADOW and no publication,
  activation, promotion, or deployment is claimed.
- Correction cycles: one. Self-review found and fixed an unlock-error path that
  could otherwise skip connection close; no scope expansion occurred.

## Delivery gate — 2026-09-14

PR #52 is open at exact head `1d0ce24`; all required current-head CI contexts
are green and no review findings are present. The mandatory independent
Standards and Spec reviewer service failed before execution on every attempted
route with an external account usage-limit error. Merge, branch cleanup,
post-merge verification, and the separate status/roadmap/claims documentation
PR are intentionally pending that review evidence.

## TDD acceptance

- Red/green tests prove exclusive mutual exclusion, concurrent shared holders,
  exclusive-vs-shared exclusion, release after child success/failure, timeout
  without child execution, stable diagnostics, autocommit, and exit propagation.
- A disposable PostgreSQL test exercises the real advisory-lock functions when a
  test database is available; the default unit suite skips only that external seam.
- Workflow tests prove validate -> import -> durable readiness -> one refresh,
  shared import shards, exclusive other writers, unchanged shard/time budgets,
  and fail-closed research exit handling.
- Syntax, least privilege, immutable actions, concurrency, timeout, recursion,
  security, release integrity, and full High-risk verification all pass.

## Verification and rollback

Run focused tests per slice, then the complete High-risk commands from `AGENTS.md`
plus explicit workflow-policy, YAML, Ruff, mypy, and disposable PostgreSQL lock
checks where available. Roll back with a normal code/workflow revert or forward
fix. Never unlock by killing production sessions, apply a down migration, delete
accepted evidence, or replace the last good snapshot. Production dispatch and
production lock observation are not part of this ticket.
