# Data lifecycle

## Implemented path

1. A reviewed source manifest identifies each canonical provider, source class, artifact type, and URL, with `published_at` when available. A reviewed filing manifest separately identifies the issuer, filing period, publication time, and official attachment URL. `discover-idx-xbrl` produces a filing-manifest review draft; it does not import it.
2. `ingest-manifest` or `ingest-idx-xbrl` retrieves and validates artifacts. Valid artifacts are persisted with checksums and availability metadata; malformed or mismatched artifacts are quarantined and reported.
3. Repository queries select facts, prices, corporate actions, and rates only when their `available_at` is no later than the requested `as_of`. A completed session and official calendar determine freshness.
4. Analysis builds a candidate quant snapshot and a full-universe scan. Candidate files are diagnostic and cannot be loaded by the bot.
5. Review, signing, and publication make a `SHADOW` (or separately validated) snapshot eligible for the published-snapshot loader. Scan publication records immutable signals and evidence identity.
6. Delivery resolves published snapshots and exposes structured `PRIMARY`, `DEGRADED`, or `UNAVAILABLE` states. A failed scan stays fail-closed; existing published data is not replaced by an unavailable result.

## Contract and roadmap boundary

The accepted [ingestion contract](../specs/ingestion-contract.md) describes cumulative discovery and durable resumability, but current ingestion is storage-idempotent and can redownload/reparse accepted work after interruption. Cumulative manifest discovery/merge is planned under `ING-001`; durable retryable/remaining progress totals and sharding are planned under `ING-004`. It is **not runtime-resumable before `ING-003`**. The accepted [snapshot lifecycle](../specs/snapshot-lifecycle.md) requires one atomic release activation; current quant and scan writes are not evidence of that boundary before `REL-001`. Formal last-good pair reactivation/recovery is planned under `DEP-002`.

No evidence becomes eligible before its `available_at`; no candidate becomes bot-readable merely because a workflow produced it; and missing, stale, conflicting, or quarantined evidence stays disclosed or unavailable rather than estimated.
