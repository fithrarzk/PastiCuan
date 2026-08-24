# ING-003: Skip-before-download resumable importer

- Status: ready
- Priority: P0
- Owner/model: Luna implementation; Sol independent review
- Reasoning effort: medium implementation, high review
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests,mocking}.md`, this card, `docs/specs/ingestion-contract.md`, `docs/runbooks/backfill.md`, and exact owned files; maximum 20k tokens
- Retry ceiling: three bounded red-green-refactor cycles per seam
- Escalation condition: migration/schema/grant change; migration 007 modification; unprovable lease fencing/per-item atomicity; provenance conflict; raw provider diagnostics; production migration, secret, or destructive action
- Parallelism: one writer for serialized `operations/research_cli.py` and `storage/repository.py`; fresh read-only reviewers afterward
- Base SHA: `25c6f2e691e8757b54c76787fe57ff0d5da0f629` (refresh to current `origin/main` when claimed)
- Branch: `feat/ING-003-resumable-importer`
- Worktree: `../PastiCuan-wt/ing-003-resumable-importer`
- Depends on: verified ING-002 (`25c6f2e`)
- File ownership: new `data/idx_filing_importer.py`, `operations/research_cli.py`, `storage/repository.py`, new `tests/test_idx_filing_importer.py`, `tests/test_filing_work_ledger.py`, `scripts/ci/check_migrations.py`, `docs/runbooks/backfill.md`, this card, and `docs/tasks/CLAIMS.md` (root only)
- Merge policy: autonomous after independent review and green current-head gates; production rollout remains separately gated

## Outcome

Validate and sync the complete reviewed Filing manifest before provider access; skip exact accepted work with zero downloads; claim unfinished work through fenced leases; commit each Filing independently; and resume after interruption without revisiting accepted entries.

## Non-goals

Do not add deterministic shards, bounded cross-run retry policy, or durable cross-shard aggregation (ING-004). Do not change migration 007, discovery, reviewed manifests, XBRL semantics, formulas, thresholds, or publication gates.

## Current evidence

ING-002 merged the required ledger/API as `25c6f2e`, but migration 007 is not applied in production. The current importer remains storage-idempotent only; it does not consult the ledger before download or commit each Filing through one ledger-fenced transaction.

## Invariants

- Complete manifest validation, migration preflight, issuer resolution, and provenance sync occur before provider access.
- Only a live fenced lease permits download/finalization; accepted and terminal quarantined work never redownloads.
- Each Filing commits independently, and ledger operational timestamps never become evidence `available_at`.
- Stable allowlisted errors replace raw exceptions/provider bodies; existing source, freshness, point-in-time, and publication gates remain unchanged.

## Implementation contract

1. Validate the complete manifest with the ING-001 schema/identity rules.
2. Run `preflight_schema_migrations(["007_filing_work_ledger"])` before sync, claim, or network.
3. Resolve issuers and sync all reviewed provenance in one fail-closed transaction. Any duplicate, unknown issuer, or immutable-provenance conflict causes zero downloads and no partial sync.
4. Bulk-read ledger state. Skip `ACCEPTED` and terminal `QUARANTINED` before claim/network; defer live `RUNNING`; claim only `PENDING`, `RETRYABLE`, or expired work.
5. Download/upload/parse only after a successful fenced claim and outside a database transaction.
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

Before first production dispatch: independently reviewed migration rollout, verified backup, protected apply, exact migration identity/grants, and read-only preflight evidence are mandatory. Roll back code by normal revert/forward-fix while retaining ledger history; never run migration 007 down or delete accepted evidence.

## Handoff

Record base/final SHA, changed files, focused/full and disposable-PostgreSQL results, independent reviews, PR/check/merge state, and explicit production rollout status. Recommend ING-004 only after this card is verified and the dated program handoff is updated.
