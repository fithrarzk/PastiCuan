# CI-002B: SQL-ASCII migration identity decoding

- Status: active
- Priority: P0 prerequisite
- Owner/model: Luna implementation, Sol review
- Reasoning effort: medium implementation, high review
- Context budget: `AGENTS.md`, `CONTEXT.md`, this card, `storage/repository.py`, and the new focused test; maximum 12k tokens
- Retry ceiling: two bounded implementation cycles
- Escalation condition: correct decoding requires a schema/migration change, changes repository API shape, or cannot reject invalid byte sequences without masking evidence
- Parallelism: one writer; independent review starts after implementation
- Base SHA: `a60a561c0c70192979107777843f420b941db67a`
- Branch: `fix/CI-002B-sql-ascii-migration-identity`
- Worktree: `../PastiCuan-wt/ci-002b-sql-ascii-migration-identity`
- Depends on: CI-002A
- Blocks: CI-002
- File ownership: `storage/repository.py`, `tests/test_storage_compatibility.py` (new), this task card, `docs/tasks/ROADMAP.md`, and `docs/tasks/CLAIMS.md` (root orchestrator only)
- Merge policy: autonomous

## Outcome

Make `SnapshotRepository.applied_schema_migrations()` return exact migration identity strings for both normal text and SQL-ASCII byte results, so CI-002 can compare storage evidence without repairing corrupted output in the gate.

## Non-goals

- Change, apply, or roll back any schema migration.
- Change database roles, connection policy, or production data.
- Alter point-in-time queries, research formulas, publication, freshness, coverage, or risk gates.
- Add generic coercion that hides malformed database values.

## Implementation contract

- Preserve already-decoded `str` migration versions exactly.
- Decode `bytes` versions as strict UTF-8 at the repository boundary.
- Propagate an explicit decoding failure for invalid bytes; never return Python byte repr strings.
- Keep the public return type `list[str]`, query, ordering, and connection lifecycle unchanged.
- Add an offline DB-API fake covering text, bytes, mixed ordered values, empty results, and invalid bytes.

## Acceptance tests

- Focused tests fail on the base behavior and pass after the smallest repository change.
- CI-002's strict repository compatibility check rejects byte repr strings and passes a real SQL-ASCII database after synchronization.
- Full compile, unit, research-release, and diff checks pass without production credentials.

## Rollout and rollback

Merge before CI-002, then synchronize and rerun both UTF-8 and SQL-ASCII ephemeral migration gates. Revert this method/test together if any caller incompatibility appears; keep CI-002 blocked rather than weakening exact identity comparison.

## Handoff

Record red/green evidence, exact returned values by type without database URLs, changed files, commands/results, review, PR/check/merge SHA, and post-merge workflow state.
