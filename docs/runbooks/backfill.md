# Backfill runbook

## Prerequisites

Do not apply migrations or perform production data actions without explicit task authorization. Require independent review, clean-database migration/compatibility CI proof, a verified backup, and a task card declaring the rollout. Configure writer/R2 secrets only in GitHub Actions and prepare a reviewed manifest. Confirm official URLs, stable filing identity, periods, publication timestamps, and issuer coverage.

## Procedure

1. Run `discover-idx-xbrl` for the requested period and review its draft; discovery never imports by itself.
2. Merge the reviewed manifest with `python -m data.filing_manifest --baseline ... --discovered ... --output ...`, then sync reviewed identities to the migration-007 filing-work ledger before any download and run `ingest-idx-xbrl --manifest ... --report ...`. The merge and ledger sync are cumulative and fail closed on duplicate exact identities, removals, restatement regressions, unknown issuers, or provenance conflicts.
3. Inspect the redacted per-Filing report: run ID, stable identity/state/action/code,
   and run-local attempted/downloaded/accepted/skipped/quarantined/retryable/
   leased/remaining counts. Accepted and terminal quarantined work is skipped
   before provider access; only a report containing entirely accepted or
   skipped-accepted entries permits the research refresh. Deterministic sharding,
   bounded cross-run retries, and durable cross-shard aggregation remain ING-004.
4. Refresh market/evidence history, then run one non-final research refresh. Publish only if all gates pass.

## Verification and stop

Stop on a non-official URL, identity conflict, missing profile, quarantine affecting required coverage, stale data, failed signing, or unavailable scan. ING-003 code makes imports skip-before-download resumable only where reviewed migration 007 is applied with exact identity and grants. Until its protected production rollout is proven, production import remains unavailable and this local/CI behavior is not production truth. Cumulative discovery merge is available under ING-001.

## Last good / rollback

Do not replace the currently published scan when backfill or refresh fails; a quant publication may already have occurred before a later scan failure because pair activation is not atomic before `REL-001`. Quarantine the offending artifact and correct the manifest/provider issue; never delete accepted evidence or use a destructive down migration.
