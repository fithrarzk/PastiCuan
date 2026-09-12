# ING-004: Deterministic shards, bounded retry, and durable progress

- Status: claimed
- Priority: P0
- Owner/model: GPT-5 root writer; Sol independent Standards and Spec reviews
- Delivery lane: High-risk (durable evidence orchestration and production workflow)
- Reasoning effort: high
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests,mocking}.md`, `.agents/skills/{supabase,supabase-postgres-best-practices}/SKILL.md`, this card, `docs/specs/{ingestion-contract,ci-cd-contract}.md`, `docs/runbooks/backfill.md`, and exact owned files; maximum 60k tokens
- Retry ceiling: three bounded correction cycles; retryable Filing attempts are capped by policy and only stable transient classes/codes are eligible
- Escalation condition: schema/migration/grant change; production dispatch or migration apply; unbounded provider work; loss of lease fencing, per-Filing atomicity, or point-in-time causality; raw provider diagnostics; evidence/publication/model change
- Parallelism: one root writer for shared ingestion/repository/workflow contracts; two fresh read-only reviewers only after the final exact head; babysitter only for long CI or active review
- Base SHA: `6b66f6552da5d8dc12aa564b4165ffc5cf00d2ca`
- Branch: `feat/ING-004-deterministic-shards`
- Worktree: `../PastiCuan-wt/ing-004-deterministic-shards`
- Issue: #45
- Depends on: verified ING-003 (`6a50ae4`) and merged handoff (`6b66f65`)
- File ownership: `data/idx_filing_importer.py`, `storage/repository.py`, `operations/research_cli.py`, `.github/workflows/idx-filings.yml`, `scripts/ci/check_workflow_policy.py`, `tests/test_idx_filing_shards.py`, `tests/test_filing_work_ledger.py`, `tests/test_workflow_policy.py`, `tests/test_ci_gates.py`, `tests/test_filing_manifest.py`, `docs/architecture/data-lifecycle.md`, `docs/runbooks/backfill.md`, `docs/reference/command-data-dictionary.md`, this card, `docs/tasks/{CLAIMS,ROADMAP}.md`, and `docs/status/2026-08-24-program-handoff.md`
- Merge policy: autonomous squash merge after full local verification, fresh independent reviews on the exact final head, and all required current-head checks; production rollout remains separately gated

## Outcome

Partition a complete reviewed Filing manifest into deterministic bounded shards, retry only allowlisted transient failures within a durable attempt ceiling and time budget, and aggregate cross-shard progress from the filing-work ledger before any research refresh.

## Non-goals

Do not change migrations 007/008 or add a migration. Do not apply production schema, dispatch production ingestion, alter discovery or reviewed manifests, substitute non-official evidence, change XBRL/accounting semantics, optimize a holdout, revise a formula/gate, publish a candidate, promote a model, or prove Railway exact-SHA deployment.

## Invariants

- Every shard validates, migration-preflights, resolves, and synchronizes the complete reviewed manifest before provider access.
- `ACCEPTED` and terminal `QUARANTINED` Filings are skipped before claim/download; a live fenced lease remains mandatory for network and finalization.
- Shard assignment is a pure reproducible function of reporting year and ticker; all filings for one issuer/reporting-year remain together.
- Only `TRANSIENT`, `PROVIDER`, and `DATABASE` failures with allowlisted stable codes are retryable. Attempts and backoff are bounded; semantic, schema, provenance, and conflict failures never loop.
- Process interruption leaves durable ledger/attempt state. Aggregation reads ledger plus the shared batch run ID, never workflow artifacts alone.
- Durable counts expose manifest, accepted, skipped accepted, quarantined, retryable, leased elsewhere, and remaining. `remaining` is every non-accepted Filing and therefore may overlap a disclosed non-accepted state count.
- An application time budget stops starting new Filings with a conservative reserve before the workflow timeout. Unstarted Filings remain durable and visible.
- No operational timestamp becomes evidence `available_at`. Existing freshness, source, coverage, publication, risk, release, and promotion gates are unchanged.

## Public seams and TDD slices

1. `data.idx_filing_importer.filing_shard`: known identities map reproducibly by ticker/reporting year, with validated shard bounds.
2. `data.idx_filing_importer.import_filings`: a shard touches only assigned unfinished work, preserves terminal skip-before-download, applies bounded allowlisted retry/backoff, and stops before its time budget.
3. `SnapshotRepository.aggregate_filing_progress`: one set-based, manifest-scoped durable read classifies final ledger state and shared-run accepted/skipped counts without provider details.
4. `operations.research_cli main`: explicit shard/batch/retry/budget options and aggregation-only mode emit strict JSON and fail closed while incomplete.
5. `.github/workflows/idx-filings.yml`: a conservative shard matrix shares one batch ID; aggregation always runs after shards; research refresh runs only from a complete durable aggregate.

Each slice follows red then the smallest green implementation. Tests use literals for known shard assignments, fake time/sleep only at the boundary, a disposable PostgreSQL integration for durable aggregation, and workflow policy assertions for timeout/concurrency/failure paths.

## Acceptance tests

- Reordering or adding unrelated manifest rows does not move an existing issuer/year group; invalid shard parameters fail before sync or network.
- Accepted and terminal quarantined rows in any shard make zero acquire/R2/parser/claim/artifact-write calls.
- Retryable allowlisted failures use bounded exponential backoff and never exceed the durable maximum attempt count or application budget; disallowed classes/codes are deferred without claim.
- Killing one shard after accepted work leaves that work skipped on restart; other shards continue independently.
- Aggregation over the shared batch ID distinguishes accepted this batch from accepted skips and reports quarantined, retryable, live leased, and remaining from ledger state.
- Shard reports and aggregate reports are stable/redacted. Missing migrations, invalid manifest, sync conflict, database failure, incomplete progress, or any failed shard prevents the research refresh.
- Workflow jobs have explicit conservative timeouts and application budgets; syntax, least privilege, concurrency, recursion, and failure-path policy tests pass.
- Existing ING-003 tests continue proving point-in-time availability, stale-fence exclusion, checksum quarantine, per-Filing atomicity, and zero-download accepted reruns.

## Implementation evidence — 2026-09-12

- Red/green slices cover stable issuer/reporting-year assignments, full-manifest
  sync before shard selection, terminal skip-before-download, durable allowlist
  and attempt ceiling, restart backoff, application budget, set-based durable
  aggregation, CLI policy arguments, and workflow refresh gating.
- Focused importer/repository/CLI tests passed 26 tests. Workflow/CI/manifest
  policy passed 42 tests. A full local run passed 186 tests after activating the
  pinned environment; the preceding run's only two errors were the unactivated
  `python` subprocess path and its one real workflow-permission finding was
  corrected with an exact least-privilege allowlist.
- The reviewed 124-Filing manifest distributes across eight shards as
  `17/16/13/17/19/15/16/11`; the largest shard has 19 Filings, or 570 seconds
  at the acquisition boundary's 30-second timeout before retry. The 1,200-second
  application budget and 45-minute job timeout retain a 25-minute outer margin;
  retries stop at the application budget instead of approaching job timeout.
- Disposable PostgreSQL 16 UTF-8 and SQL-ASCII databases each returned
  `verified 8 migrations`, including durable aggregation, attempt-ceiling,
  per-Filing atomicity, stale-fence, and point-in-time integration tests.
- Supabase's current changelog was checked for relevant database/pooling changes.
  No applicable API/schema breaking change was found. The set-based query follows
  the repository primary-key/attempt indexes and holds no locks across provider
  work. No Supabase MCP/production query or mutation was performed.
- Final full verification, exact-head independent reviews, current-head CI, PR,
  merge, cleanup, and post-merge evidence remain pending.

## Rollout and rollback

This task authorizes code/test/docs/workflow delivery only. Migrations 007/008 remain unapplied in production and block import at preflight. First production import still requires explicit reviewed rollout authorization, verified backup, protected migrator, exact migration/grant verification, session-compatible writer, and narrow read-only post-apply proof.

Roll back through a reviewed code/workflow revert or forward fix while retaining ledger and evidence history. Never run a production down migration or delete accepted/quarantined evidence. A failed shard/aggregate retains the prior active research release.

## Handoff

Record task/lane/model, base and final SHA, branch/worktree/files, behavior, red-green cycles, exact focused/full/disposable-PostgreSQL/workflow results, final-head Standards and Spec reviews, PR/check/merge/cleanup/post-merge state, Supabase evidence or `not applicable`, limitations, rollback, elapsed/context/corrections, and the next dependency-ready task. Do not begin OBS-001 until ING-004 is merged, documented, and verified.
