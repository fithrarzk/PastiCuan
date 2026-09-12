# Backfill runbook

## Prerequisites

Do not apply migrations or perform production data actions without explicit task authorization. Require independent review, clean-database migration/compatibility CI proof, a verified backup, and a task card declaring the rollout. Configure writer/R2 secrets only in GitHub Actions and prepare a reviewed manifest. The writer URL must use a direct or session-pooled PostgreSQL connection because the per-Filing download fence is session-scoped; fail closed with transaction pooling. Confirm official URLs, stable filing identity, periods, publication timestamps, and issuer coverage.

## Procedure

1. Run `discover-idx-xbrl` for the requested period and review its draft; discovery never imports by itself.
2. Merge the reviewed manifest with `python -m data.filing_manifest --baseline ... --discovered ... --output ...`, then preflight migrations 007 and 008 and sync reviewed identities to the filing-work ledger before any download. Run `ingest-idx-xbrl --manifest ... --report ...`. The merge and ledger sync are cumulative and fail closed on duplicate exact identities, removals, restatement regressions, unknown issuers, or provenance conflicts.
3. The import workflow partitions the complete manifest into eight deterministic
   issuer/reporting-year shards. Each shard uses the shared workflow run ID, at
   most three allowlisted transient attempts with bounded exponential backoff,
   and a 20-minute application budget inside a 45-minute job. Inspect each
   redacted per-Filing report for stable identity/state/action/code and run-local
   attempted/downloaded/accepted/skipped/quarantined/retryable/leased/remaining
   counts. Accepted and terminal quarantined work is skipped before provider
   access.
4. The aggregation job validates and synchronizes the complete manifest again,
   then reads manifest-scoped ledger and attempt state for the shared run ID.
   Inspect accepted, skipped accepted, quarantined, retryable, leased elsewhere,
   and remaining totals. Workflow artifacts are diagnostic only. Research refresh
   is requested only when every shard succeeded and the durable aggregate contains
   only accepted or skipped-accepted Filings.
5. Refresh market/evidence history, then run one non-final research refresh. Publish only if all gates pass.

## Verification and stop

Stop on a non-official URL, identity conflict, retry ceiling, shard budget,
incomplete durable aggregate, missing profile, quarantine affecting required
coverage, stale data, failed signing, unavailable scan, or a writer connection
that cannot preserve a session advisory lock. ING-003/ING-004 code makes imports
skip-before-download resumable and durably sharded only where reviewed migrations
007 and 008 are applied with exact identity and grants. Until their protected
production rollout is proven, production import remains unavailable and this
local/CI behavior is not production truth. Cumulative discovery merge is
available under ING-001.

## Last good / rollback

Do not replace the currently published scan when backfill or refresh fails; a quant publication may already have occurred before a later scan failure because pair activation is not atomic before `REL-001`. Quarantine the offending artifact and correct the manifest/provider issue; never delete accepted evidence or use a destructive down migration.
