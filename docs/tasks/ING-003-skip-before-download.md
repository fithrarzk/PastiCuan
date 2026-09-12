# ING-003: Skip-before-download resumable importer

- Status: verified (code delivery; production rollout remains gated)
- Priority: P0
- Owner/model: GPT-6 root writer; Sol independent review
- Delivery lane: High-risk (fenced transactions and point-in-time evidence)
- Reasoning effort: medium implementation, high review
- Context budget: owner reset the execution limit on 2026-09-08 and authorized one bounded review-correction cycle; exact owned files and linked ingestion/backfill contracts only
- Retry ceiling: one final bounded correction cycle after the 2026-09-07 review
- Escalation condition: migration 007 modification; unprovable lease fencing/per-item atomicity; provenance conflict; raw provider diagnostics; production migration, secret, or destructive action
- Parallelism: one writer for serialized `operations/research_cli.py` and `storage/repository.py`; fresh read-only reviewers afterward
- Base SHA: `1b7e06efb1722dc4b335f5fd1da205c9bd51e5fa`
- Branch: `feat/ING-003-resumable-importer`
- Worktree: `../PastiCuan-wt/ing-003-resumable-importer`
- Depends on: verified ING-002 (`25c6f2e`)
- File ownership: new `data/idx_filing_importer.py`, `operations/research_cli.py`, `storage/{database,repository}.py`, additive `storage/migrations/008_filing_artifact_mismatch.{up,down}.sql`, `tests/test_{idx_filing_importer,filing_work_ledger,ci_gates}.py`, `scripts/ci/check_migrations.py`, `docs/runbooks/backfill.md`, this card, and `docs/tasks/CLAIMS.md` (root only)
- Merge policy: autonomous after independent review and green current-head gates; production rollout remains separately gated

## Renewed Standards correction — 2026-09-08

Owner instruction `finish it` renews one bounded correction cycle for the two
remaining Standards findings and completion of review/merge verification.
The repository sync seam now batches issuer validation, ordered inserts and
locked provenance validation in three queries. A real PostgreSQL regression
test observed 302 queries for 100 filings before the correction; afterward the
complete prepare seam uses at most six, including reruns. A conflicting row
rolls back newly inserted rows in the same batch. Concurrent insert conflicts
are checked by a separate statement after ON CONFLICT waits, with deterministic
identity ordering. No migration or grant changed in this correction.

The disposable rollback help now names both migrations and their order.
Verification: 175 tests in 9.623s, OK (two disposable tests exercised separately);
UTF-8 and SQL-ASCII each returned `verified 8 migrations`; compilation,
research-release policy, Ruff, CI-configured mypy and diff check exited zero.
Fresh reviews and CI on the resulting commit remain pending.

## Verified delivery — 2026-09-08

- Base: `1b7e06efb1722dc4b335f5fd1da205c9bd51e5fa`; final reviewed head:
  `c99c4bac60356d418205b449ad9acfe111cbb2c2`; squash merge:
  `6a50ae4ba1149feff010fb67547fe4837ca6cd51` via PR #43.
- Fresh Standards and Spec reviews both passed with zero findings. All eight
  required checks passed in `34196294226`. Main verification `34196669570`
  passed compilation, release integrity and tests. Issue #42 closed and its
  claim label was released; remote and local implementation branches deleted.
  The worktree was retained for this documentation handoff.
- Post-merge research `34196669534` failed closed at preflight: exit 40,
  `INFRASTRUCTURE/REQUIRED_MIGRATION_MISSING`, missing migrations 007 and 008.
  No research recovery, production import or exact-SHA Railway deployment is
  claimed. The failure is the required production gate, not an incomplete
  code-delivery check. Other production workflows were not dispatched.
- Changed files/behavior and exact local results are recorded in ownership and
  the correction sections above. The final correction ran 175 tests in 9.623s,
  with two disposable-only skips separately passing in both database encodings.
  UTF-8 and SQL-ASCII each verified eight migrations. No production MCP query,
  schema apply, secret change, publication or promotion was performed.
- High-risk; GPT-6 root, Sol independent reviews. Renewed correction and merge
  verification took approximately 10 minutes and 9k context tokens, one
  bounded Standards correction; earlier phase usage remains recorded below.
  Roll back by reviewed code revert/forward fix, retaining ledger/evidence;
  production down migrations remain prohibited.
- Next dependency-ready task: ING-004 deterministic shards, bounded retries
  and durable progress, after the dated program handoff is merged. Production
  rollout still requires reviewed authorization, verified backup, protected
  migrator, session-compatible writer and read-only post-apply evidence.

## Outcome

Validate and sync the complete reviewed Filing manifest before provider access; skip exact accepted work with zero downloads; claim unfinished work through fenced leases; commit each Filing independently; and resume after interruption without revisiting accepted entries.

## Non-goals

Do not add deterministic shards, bounded cross-run retry policy, or durable cross-shard aggregation (ING-004). Do not change immutable migration 007, discovery, reviewed manifests, XBRL semantics, formulas, thresholds, or publication gates. Migration 008 may only narrow the terminal checksum-mismatch exception described in the review handoff.

## Current evidence

ING-002 merged the required ledger/API as `25c6f2e`, but migration 007 is not applied in production. The current importer remains storage-idempotent only; it does not consult the ledger before download or commit each Filing through one ledger-fenced transaction.

## Invariants

- Complete manifest validation, migration preflight, issuer resolution, and provenance sync occur before provider access.
- Only a live fenced lease permits download/finalization; accepted and terminal quarantined work never redownloads.
- Each Filing commits independently, and ledger operational timestamps never become evidence `available_at`.
- Stable allowlisted errors replace raw exceptions/provider bodies; existing source, freshness, point-in-time, and publication gates remain unchanged.

## Implementation contract

Public seams for TDD: importer run report with injected provider/storage boundaries;
repository prepare/complete-Filing transaction methods; ingest-idx-xbrl CLI exit
and report. A transaction-bound repository reuses existing artifact/fact/profile
methods without opening or committing a second connection. An initial live-lease
row lock plus final lease check brackets all writes; expiry rolls back everything.
Repository timestamps never supply evidence availability. Task-adjacent ownership
includes the dated handoff and roadmap status update before ING-004.

1. Validate the complete manifest with the ING-001 schema/identity rules.
2. Run `preflight_schema_migrations(["007_filing_work_ledger", "008_filing_artifact_mismatch"])` before sync, claim, or network.
3. Resolve issuers and sync all reviewed provenance in one fail-closed transaction. Any duplicate, unknown issuer, or immutable-provenance conflict causes zero downloads and no partial sync.
4. Bulk-read ledger state. Skip `ACCEPTED` and terminal `QUARANTINED` before claim/network; defer live `RUNNING`; claim only `PENDING`, `RETRYABLE`, or expired work.
5. Acquire a collision-resistant, per-identity session advisory fence before claim, then download/upload/parse only after a successful fenced claim and outside a database transaction. Hold the fence through finalization and require a direct or session-pooled writer connection; transaction pooling is not compatible with this session lock.
6. Complete one Filing per transaction: lock the live lease, register the artifact, import facts/profile outcome, set artifact status, and finalize work plus attempt. A bad row cannot roll back a separately committed accepted row.
7. Persist transient/provider/R2 failures as allowlisted `RETRYABLE`; persist semantic/schema failures with artifact provenance as `QUARANTINED`; never store raw exception/provider text.
8. A stale token cannot finalize. Process death leaves pending work, an expirable running attempt, or a durable accepted result that the next run skips.

## Acceptance tests

Return a structured run ID, per-Filing identity/state/action, stable codes, and run-local counts for manifest, attempted, downloaded, accepted, skipped accepted, quarantined, retryable, and leased elsewhere. Exit zero only when every entry is accepted or skipped accepted; all other states prevent the research refresh.

The structured report contains run ID, normalized per-Filing state/action, stable codes, and counts for manifest, attempted, downloaded, accepted, skipped accepted, quarantined, retryable, and leased elsewhere. Exit zero only when every entry is accepted or skipped accepted. Tests must prove:

- a fully accepted rerun makes zero acquire/R2/parser/claim/artifact-write calls;
- mixed and interrupted runs touch only unfinished work after lease expiry;
- one malformed Filing does not roll back earlier or later independent items;
- provider failure becomes durable retryable without sensitive text and can later accept;
- duplicate/provenance/issuer/host failures occur before all network access;
- concurrent/stale workers cannot both download/finalize;
- PostgreSQL atomically commits artifact, facts/profile outcome, ledger item, and attempt per Filing;
- metrics and CLI exit behavior match the contract.

## Rollout and rollback

Production migration-007 absence does not block code/test/PR work because preflight must fail before network, and a code-only merge does not dispatch the manifest workflow. It **does** block production import rollout and operational resumability proof.

Before first production dispatch: independently reviewed migrations 007 and 008 rollout, verified backup, protected apply, exact migration identity/grants, a direct or session-pooled writer connection, and read-only preflight evidence are mandatory. Roll back code by normal revert/forward-fix while retaining ledger history; never run either down migration in production or delete accepted evidence.

## Handoff

Record base/final SHA, changed files, focused/full and disposable-PostgreSQL results, independent reviews, PR/check/merge state, and explicit production rollout status. Recommend ING-004 only after this card is verified and the dated program handoff is updated.

### Review checkpoint — 2026-09-07

- Base: `1b7e06efb1722dc4b335f5fd1da205c9bd51e5fa`; final commit,
  PR, reviews, checks, merge, and post-merge state remain pending.
- `data/idx_filing_importer.py` validates the complete reviewed manifest and
  migration 007 before sync/provider access, skips accepted and terminal
  quarantined work, defers live leases, claims unfinished work, and emits a
  redacted structured run report. Only accepted/skipped-accepted completion
  exits zero. Sharding and bounded cross-run retry remain ING-004.
- Repository prepare syncs issuer resolution and immutable provenance in one
  transaction. Per-Filing completion locks the live fence and atomically writes
  artifact, facts/profile outcome, ledger item, and attempt. Provider/R2 work
  remains outside transactions. Database timestamps never become `available_at`.
- Ten importer/CLI tests and six ledger tests pass. Disposable PostgreSQL 16
  proves rollback on a malformed later fact, stale-token rejection, independent
  acceptance/quarantine, accepted rerun with zero downloads, and facts invisible
  before `available_at`. Clean migration checks verify all seven migrations.
  The complete suite passes 172 tests in 11.737s; compilation, Ruff, mypy for
  six changed Python files, research-release policy, and whitespace checks pass.
- No migration/schema/grant, formula, gate, manifest, credential, or production
  action occurred. Supabase changelog review found no relevant API/database
  breaking change; MCP was unnecessary because no current production evidence
  or Supabase API behavior was needed. Migration 007 remains unapplied in
  production, so production import and operational resumability remain blocked.
- High-risk; GPT-6 root implementation and Sol/high reviews pending. Approximate
  implementation time 35 minutes, context use 18k tokens, three bounded TDD
  corrections across importer, transaction, and reporting seams. Roll back by
  normal code revert while retaining ledger/evidence history; never run migration
  007 down in production. Next task after verified merge and handoff: ING-004.

### Recoverable review handoff — 2026-09-07

- Checkpoint head before this record: `2ff6b9273d97970574aab17a730797b96325a136`;
  PR #43; issue #42 remains claimed. All eight required checks passed in
  `34141807486`, including the disposable PostgreSQL migration job. The branch
  is intentionally unmerged.
- Standards review of `2ff6b92`: no hard breach; one low naming smell because
  `bound` obscures transaction-bound repository reuse.
- Spec review found three High issues. Valid manifest failures at migration
  preflight or atomic sync omit per-Filing blocked results. Reviewed-checksum
  mismatch is incorrectly durable `RETRYABLE` and loses the acquired artifact
  instead of becoming terminal quarantine evidence. A lease renewed only before
  acquisition does not prevent another worker reclaiming and downloading after
  expiry while the first worker is still in provider/R2/parser work.
- The checksum issue cannot be corrected within migration 007 as merged.
  `enforce_filing_work_acceptance` requires expected checksum equality for both
  `ACCEPTED` and `QUARANTINED`. Do not forge the expected checksum, discard
  provenance, retain a deterministic mismatch as retryable, or modify immutable
  migration 007. The repair requires a separately reviewed additive migration
  that permits a mismatched acquired artifact only for
  `QUARANTINED/ARTIFACT_MISMATCH`, with matching down migration, compatibility,
  grants, trigger tests, and rollout/rollback documentation. Production apply
  remains prohibited without the existing backup/protected-rollout gates.
- Download exclusivity needs a per-identity session advisory fence acquired
  before claim and held through acquire/R2/parse/final completion. It must run
  outside a database transaction, use a deterministic collision-resistant key,
  release on normal exit/disconnect, and have a two-session test proving the
  losing worker makes zero provider calls. This preserves short transactions;
  assess connection-pool impact for ING-004 sharding.
- The final reporting correction initializes `remaining` immediately after
  manifest validation and tests migration-preflight remaining count. It is safe
  but does not resolve the three review blockers.
- Stop reason: task-card 20k context ceiling and explicit escalation conditions
  for schema change and unproven lease fencing. Approximately 55 minutes and
  20k task tokens; three bounded corrections used. Resume with a revised
  decision-complete card/file ownership for the additive migration and advisory
  fence, then TDD the three findings, rerun full/disposable verification, and
  obtain fresh reviews on the new exact head. ING-004 remains blocked.

### Owner-authorized correction — 2026-09-08

- The one bounded correction addresses all three review findings. Valid
  manifests now receive one normalized blocked result per Filing when migration
  preflight or atomic sync fails. A reviewed-checksum mismatch archives the
  acquired artifact and becomes terminal `QUARANTINED/ARTIFACT_MISMATCH`; it is
  never parsed or treated as transient.
- Additive migration 008 narrowly permits an actual/expected checksum mismatch
  only for the exact terminal provenance outcome. Migration 007 remains byte-for-
  byte unchanged. No grants change. Clean PostgreSQL 16 verification applied all
  eight migrations twice, checked catalog and role contracts, proved the
  mismatch preserves both checksums, and passed guarded 008-down/007-down/007-up/
  008-up recovery on a named loopback-only disposable database.
- A deterministic two-key session advisory lock is acquired before the durable
  claim and held through acquisition, archive upload, parsing, and finalization.
  Two real database sessions prove one winner and release/reacquisition; the
  importer test proves the loser makes zero claim or provider calls. The writer
  rejects Supabase transaction-pooler port 6543 and the runbook requires direct
  or session pooling. Official Supabase connection documentation confirms 5432
  for direct/session mode and 6543 for transaction mode.
- Local verification passes: 174 tests (one disposable-only skip, exercised
  separately), compilation, research-release policy, diff check, Ruff, exact CI
  mypy flags for five source files, workflow policy/YAML validation, and the
  eight-migration disposable PostgreSQL check. Fresh exact-head Standards and
  Spec reviews, current-head PR checks, merge, and post-merge verification remain
  pending. No Supabase MCP or production mutation was used; protected migration
  rollout remains separately gated.

### Final review checkpoint — 2026-09-08

- Base: `1b7e06efb1722dc4b335f5fd1da205c9bd51e5fa`; tested and reviewed
  implementation head: `429c1f10c1f79e20218cac1d7ba977d161c1b0b0`.
  PR #43 is open and unmerged; issue #42 remains claimed. All eight required
  checks passed in run `34155429124`. No merge SHA or post-merge workflow exists.
- Fresh Spec review passed with zero findings and closed all three previous
  High findings. Fresh Standards review reported one Medium documented-practice
  breach: `prepare_filing_import` calls the per-item query loop in
  `sync_reviewed_filings` inside a manifest-wide transaction. Batch issuer and
  provenance reads/writes while preserving atomic validation and deterministic
  locking. One Low finding: migration-check help mentions only 007 although
  the guarded disposable rollback also includes 008.
- Files and behavior are listed in ownership and the preceding correction
  record. The final test-only commit corrected SQL-ASCII byte normalization and
  a credential-shaped fixture; no scanner rule was relaxed. Both UTF-8 and
  SQL-ASCII disposable checks returned `verified 8 migrations` (exit 0).
- `python -m compileall -q analysis data storage operations telegram_utils bot.py
  bot_webhook.py`: exit 0. Full unittest discovery: 174 tests, 6.126 seconds,
  OK with one separately exercised disposable skip. Research-release check,
  diff check, Ruff and CI-configured mypy: exit 0. Unrestricted mypy reported
  76 errors in 26 files, including imported modules outside this change;
  the repository's configured CI invocation passed for five source files.
  Current-head required CI independently passed. This resumption rechecked
  clean git status, unchanged main/base, all eight checks, and both reviews.
- No production query or mutation occurred. Migrations 007/008, writer session
  compatibility, backup and protected rollout still need production proof.
  Preserve all user-owned untracked files. Rollback is a reviewed code revert
  or forward fix retaining evidence; never apply production down migrations.
- High-risk; GPT-6 root and Sol independent reviewers. Prior phase recorded
  approximately 55 minutes/20k tokens and three corrections. The continuation
  consumed its one authorized review-correction cycle plus the verified CI
  fixture adjustment; precise cumulative elapsed/context telemetry is not
  available across model/usage interruptions. This resumption used roughly
  5k context tokens. Stop at the task-card correction ceiling with the two
  Standards findings recorded; no further code correction or merge is claimed.
- Next dependency-ready work is completing ING-003 Standards remediation with
  a renewed bounded allowance and fresh reviews. ING-004 remains dependent on
  verified ING-003 merge and the required dated program handoff update.
