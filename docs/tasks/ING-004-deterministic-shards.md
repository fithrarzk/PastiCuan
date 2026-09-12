# ING-004: Deterministic shards, bounded retry, and durable progress

- Status: verified
- Priority: P0
- Owner/model: GPT-5 root writer; Sol independent Standards and Spec reviews
- Delivery lane: High-risk (durable evidence orchestration and production workflow)
- Reasoning effort: high
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests,mocking}.md`, `.agents/skills/{supabase,supabase-postgres-best-practices}/SKILL.md`, this card, `docs/specs/{ingestion-contract,ci-cd-contract}.md`, `docs/runbooks/backfill.md`, and exact owned files; maximum 60k tokens
- Retry ceiling: three bounded correction cycles; retryable Filing attempts are capped by policy and only stable transient classes/codes are eligible
- Escalation condition: schema/migration/grant change; production dispatch or migration apply; unbounded provider work; loss of lease fencing, per-Filing atomicity, or point-in-time causality; raw provider diagnostics; evidence/publication/model change
- Parallelism: one root writer for shared ingestion/repository/workflow contracts; two fresh read-only reviewers only after the final exact head; babysitter only for long CI or active review
- Base SHA: `6b66f6552da5d8dc12aa564b4165ffc5cf00d2ca`
- Final reviewed SHA: `d2348493b7f6a9e4bcae57cd7f0166e94cbc1149`
- Merge SHA: `9aeb54f9ab526a4c4ab4c514ae76b5bf6a76aa22`
- Branch/worktree: `feat/ING-004-deterministic-shards` / `../PastiCuan-wt/ing-004-deterministic-shards` (deleted after merge)
- Issue: #45 (closed)
- Depends on: verified ING-003 (`6a50ae4`) and merged handoff (`6b66f65`)
- File ownership: `data/{filing_work_policy,idx_filing_importer}.py`, `storage/repository.py`, `operations/research_cli.py`, `.github/workflows/idx-filings.yml`, `scripts/ci/check_workflow_policy.py`, `tests/test_idx_filing_shards.py`, `tests/test_filing_work_ledger.py`, `tests/test_workflow_policy.py`, `tests/test_ci_gates.py`, `tests/test_filing_manifest.py`, `docs/architecture/data-lifecycle.md`, `docs/runbooks/backfill.md`, `docs/reference/command-data-dictionary.md`, this card, `docs/tasks/{CLAIMS,ROADMAP}.md`, and `docs/status/2026-08-24-program-handoff.md`
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
- Focused importer/repository/CLI tests passed 26 tests before review; 30
  policy/importer/ledger tests passed after policy consolidation, and the final
  importer/shard boundary set passed 22 tests. Workflow/CI/manifest
  policy passed 42 tests. The final corrected full local run passed 188 tests after activating the
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
- Corrected full verification passed compilation, 188 tests (`OK`, three
  disposable-PostgreSQL tests skipped in that run and exercised separately),
  research-release validation, workflow policy, tracked-source secret scan,
  workflow YAML validation, Ruff format/check, CI-configured mypy for the four
  changed source files, and diff checks. UTF-8 and SQL-ASCII disposable
  PostgreSQL 14 databases each returned `verified 8 migrations` after a clean
  down/re-up exercise.
- The first exact-head Spec review passed with zero findings. The simultaneous
  Standards review found duplicated retry allowlists and a repeated internal
  policy bundle. Correction cycle two moved the allowlist predicate and immutable,
  validated shard/retry/budget policy into `data.filing_work_policy`; CLI flags
  remain unchanged and both importer and repository now consume the shared policy.
- Correction cycles: three. Before the fresh reviews concluded, root added a
  red/green boundary test and corrected a falsey non-policy object that otherwise
  selected the default policy; invalid policy objects now fail before sync or
  network. The initial full run identified the workflow policy's
  legacy monolithic-job permission allowlist; the exact least-privilege split and
  its negative policy fixture were corrected before final verification. The two
  simultaneous CLI subprocess errors were environment setup only and passed with
  the pinned environment on `PATH`.
- Fresh final-head Standards and Spec reviews on `d2348493` each passed with zero
  findings. PR #46 had all eight applicable checks pass in run `34710446087` and
  squash-merged as `9aeb54f`; issue #45 closed, and local/remote branches plus the
  implementation worktree were deleted. Main verification `34710537290` passed.
- Post-merge research run `34710537324` failed closed at preflight with exit 40,
  `REQUIRED_MIGRATION_MISSING` for 007/008. No publication, production migration,
  production Supabase query/mutation, promotion, or exact-SHA Railway proof was
  performed or claimed. OBS-001 is the next dependency-ready task.

## Verification commands and exact results

```bash
python -m compileall -q analysis data storage operations telegram_utils bot.py bot_webhook.py
python -m unittest discover -s tests -v
python -m operations.research_cli check-research-release
python scripts/ci/check_workflow_policy.py
python scripts/ci/check_security.py
ruff format --check data/filing_work_policy.py data/idx_filing_importer.py storage/repository.py operations/research_cli.py tests/test_idx_filing_shards.py
ruff check data/filing_work_policy.py data/idx_filing_importer.py storage/repository.py operations/research_cli.py tests/test_idx_filing_shards.py
mypy --follow-imports=skip --ignore-missing-imports --disable-error-code=import-untyped -- data/filing_work_policy.py data/idx_filing_importer.py storage/repository.py operations/research_cli.py
git diff --check
```

The final sequence returned exit 0: compilation was quiet; unittest reported
`Ran 188 tests` and `OK (skipped=3)`; research-release validation returned digest
`188c66c3df19bb92d0ba934b4886112752159f1a7eb7b3fb165ee036670765e3`,
revision 2 and SHADOW model `lq45-factor-v2-shadow`; workflow policy reported
`passed for 2 workflow(s)`; security reported `tracked-source secret scan passed`;
Ruff reported five files formatted and no violations; mypy reported no issues in
four source files; YAML parsing reported `.github/workflows/idx-filings.yml:
valid`; and the diff check was quiet.

```bash
python scripts/ci/check_migrations.py --database-url "$ING004_UTF8_DATABASE_URL" --base-ref origin/main --verify-disposable-down-reup
python scripts/ci/check_migrations.py --database-url "$ING004_ASCII_DATABASE_URL" --base-ref origin/main --verify-disposable-down-reup
```

Both task-scoped variables referred only to clean loopback disposable databases;
each command returned exactly `verified 8 migrations`.

## Rollout and rollback

This task authorizes code/test/docs/workflow delivery only. Migrations 007/008 remain unapplied in production and block import at preflight. First production import still requires explicit reviewed rollout authorization, verified backup, protected migrator, exact migration/grant verification, session-compatible writer, and narrow read-only post-apply proof.

Roll back through a reviewed code/workflow revert or forward fix while retaining ledger and evidence history. Never run a production down migration or delete accepted/quarantined evidence. A failed shard/aggregate retains the prior active research release.

## Handoff

Record task/lane/model, base and final SHA, branch/worktree/files, behavior, red-green cycles, exact focused/full/disposable-PostgreSQL/workflow results, final-head Standards and Spec reviews, PR/check/merge/cleanup/post-merge state, Supabase evidence or `not applicable`, limitations, rollback, elapsed/context/corrections, and the next dependency-ready task. Do not begin OBS-001 until ING-004 is merged, documented, and verified.
