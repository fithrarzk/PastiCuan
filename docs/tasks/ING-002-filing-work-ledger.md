# ING-002: Durable filing-work ledger migration and repository API

- Status: active
- Priority: P0
- Owner/model: Sol schema design; Luna implementation; Sol independent review
- Reasoning effort: high implementation and review
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests,mocking}.md`, this card, `docs/specs/{ingestion-contract,ci-cd-contract}.md`, `docs/runbooks/backfill.md`, and exact owned files; maximum 24k tokens
- Retry ceiling: three deterministic red-green cycles per failed seam; never retry semantic, migration, provenance, fencing, or privilege conflicts automatically
- Escalation condition: an existing migration or accepted evidence must change; exact-identity provenance conflicts; concurrent fencing cannot be proven; or production down migration, secret, gate change, or broader grant is required
- Parallelism: one Luna writer under the serialized migration/`storage/repository.py` owner; fresh read-only reviewers after implementation
- Base SHA: `64296432c30c51f9987206de1c27a45bddf6d85f`
- Branch/worktree: `feat/ING-002-filing-work-ledger` / `../PastiCuan-wt/ing-002-filing-work-ledger`
- Issue: #28
- Depends on: ING-001, verified as `5d8817f`
- File ownership: `storage/migrations/007_filing_work_ledger.{up,down}.sql` (new), `storage/repository.py`, `storage/supabase_roles.sql`, `scripts/ci/check_migrations.py`, `tests/test_filing_work_ledger.py` (new), `tests/test_ci_gates.py`, `docs/runbooks/backfill.md`, this card, and `docs/tasks/CLAIMS.md` (root only)
- Merge policy: autonomous with migration gates

## Outcome and non-goals

Persist the operational lifecycle of each reviewed Filing before network access. The ledger distinguishes a reviewed Filing from its retrieved Accepted or Quarantined artifact and records fenced leases, durable attempts, stable redacted errors, checksums, and artifact identity.

This task adds persistence and its repository seam only. It does not make `ingest-idx-xbrl` resumable, dispatch ingestion, edit reviewed manifests, change formulas/publication gates, apply production migrations, rewrite evidence, or touch `operations/research_cli.py`; runtime skip-before-download remains ING-003.

## Schema and API contract

Migration 007 adds `filing_work_items` and append-only `filing_work_attempts`. Work identity is `(issuer_id, canonical filing_type, period_end, positive restatement_version)`. Immutable reviewed provenance includes source URL, publication time, audit status, and optional expected checksum. States are `PENDING`, `RUNNING`, `ACCEPTED`, `QUARANTINED`, and `RETRYABLE`.

The database enforces legal transitions, database-clock timestamps, exactly one attempt per acquired lease, complete lease fields only while running, terminal accepted/quarantined states, and acceptance only with a matching accepted `source_artifacts` URL/checksum. Expired or superseded lease tokens cannot finish work. The down migration removes only migration-007 objects and is disposable-test-only, never an automatic production rollback.

Add repository methods to atomically sync reviewed work, bulk-read statuses, claim/renew/finalize fenced leases, expire leases in bounded `FOR UPDATE SKIP LOCKED` batches, read attempt history, and aggregate counts. Unknown issuers or changed exact-identity provenance fail before mutation. State-changing calls own one transaction and accept only allowlisted error class/summary fields, never raw exceptions or provider bodies.

## Invariants

- Ledger timestamps are operational metadata, not `available_at`; existing Filing/StatementFact point-in-time queries remain unchanged.
- Exact accepted work is skippable only when identity, reviewed provenance, accepted artifact, URL, and checksum agree.
- Re-syncing accepted work performs no transition and creates no attempt; stale workers cannot finalize after expiry/reclaim.
- One failed item transaction cannot roll back another committed item; no accepted evidence, reviewed history, or artifact is deleted or rewritten.
- `pasticuan_ingest` receives only required ledger read/write privileges, `pasticuan_validator` read-only access, and `pasticuan_bot` no ledger access; no role receives delete.

## Acceptance tests

Use TDD through the public API and disposable PostgreSQL 16:

1. Clean apply/reapply and disposable down/re-up create exact migration identity, constraints, indexes, and roles under UTF-8 and SQL-ASCII.
2. Idempotent sync leaves one pending item and zero attempts; any immutable-provenance conflict fails without mutation.
3. Two concurrent claimers yield one lease/attempt; renewal is live-token-only; expiry becomes durable retryable; stale tokens cannot finalize after reclamation.
4. Acceptance requires the matching accepted artifact, URL, and checksum. Transient and semantic failures persist retryable/quarantined stable errors, while attempt history survives later acceptance.
5. Independent items commit independently; bulk statuses/counts are deterministic; ledger time cannot expose evidence before existing `available_at`.
6. Role checks prove least privilege and no delete. Migration gate count advances from six to seven without weakening SQL-ASCII or compatibility checks.
7. Focused tests, compilation, full suite, release check, migration checks, and `git diff --check` pass.

## Rollout, rollback, and handoff

Before production apply: independent migration/security review, green current-head migration CI, clean apply/reapply compatibility proof, verified backup, explicit rollout declaration, and serialized database writer. ING-002 itself does not apply production migration 007 or seed work. Production rollback is application revert/forward-fix while leaving the additive empty ledger; destructive production down migration requires separate authorization.

Handoff records base/final SHA, migration checksum, changed files, exact test results, reviews, PR/checks/merge, backup/migration/deploy identifiers if later applied, read-only post-apply evidence, limitations, and ING-003 as next task. Do not claim resumability from this task alone.
