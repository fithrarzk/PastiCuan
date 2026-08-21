# Data lifecycle

## Implemented path

1. A reviewed source or filing manifest identifies canonical sources, issuer, period, publication time, and URL. `discover-idx-xbrl` produces a review draft; it does not import it.
2. `ingest-manifest` or `ingest-idx-xbrl` retrieves and validates artifacts. Valid artifacts are persisted with checksums and availability metadata; malformed or mismatched artifacts are quarantined and reported.
3. Repository queries select facts, prices, corporate actions, and rates only when their `available_at` is no later than the requested `as_of`. A completed session and official calendar determine freshness.
4. Analysis builds a candidate quant snapshot and a full-universe scan. Candidate files are diagnostic and cannot be loaded by the bot.
5. Review, signing, and approval make a `SHADOW` (or separately validated) snapshot eligible for the approved snapshot loader. Scan publication records immutable signals and evidence identity.
6. Delivery resolves approved snapshots and exposes structured `PRIMARY`, `DEGRADED`, or `UNAVAILABLE` states. A failed refresh preserves the last good snapshot.

## Contract and roadmap boundary

The accepted [ingestion contract](../specs/ingestion-contract.md) requires cumulative discovery and durable resumability, but current ingestion is storage-idempotent and can redownload/reparse accepted work after interruption. It is **not runtime-resumable before `ING-003`**. The accepted [snapshot lifecycle](../specs/snapshot-lifecycle.md) requires one atomic release activation; current quant and scan writes are not evidence of that boundary before `REL-001`.

No evidence becomes eligible before its `available_at`; no candidate becomes bot-readable merely because a workflow produced it; and missing, stale, conflicting, or quarantined evidence stays disclosed or unavailable rather than estimated.
