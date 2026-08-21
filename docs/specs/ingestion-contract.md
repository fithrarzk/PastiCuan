# Ingestion Contract

## Outcome

Official IDX filing discovery is cumulative and import work is durably resumable. A timeout, cancellation, or single malformed filing must not repeat accepted work or expose partially refreshed research.

## Filing identity and lifecycle

A stable filing identity contains issuer, filing type, period end, and restatement version. URL and checksum are provenance, not substitutes for the accounting identity.

The durable ledger states are:

- `PENDING`: reviewed entry not attempted;
- `RUNNING`: leased by one active worker;
- `ACCEPTED`: validated evidence committed;
- `QUARANTINED`: terminal validation failure with reason;
- `RETRYABLE`: transient provider, R2, or database failure eligible for bounded retry.

Every transition records attempt count, timestamps, error class, source URL, checksum when available, worker/run ID, and resulting artifact ID. Expired `RUNNING` leases become `RETRYABLE`.

## Discovery

- Merge discoveries into reviewed history by stable filing identity.
- Never remove a reviewed historical entry through ordinary discovery.
- A removal or supersession requires an explicit reviewed record and reason.
- Validate official host, attachment type, period, ticker, timestamps, duplicates, restatements, and unexplained URL changes.
- Maintain one rolling manifest PR; subsequent discovery updates it instead of creating competing PRs.

## Import

- Query the ledger before network access and skip exact accepted entries.
- Commit each entry independently.
- Use deterministic bounded shards by reporting year and ticker slice with conservative concurrency.
- Retry transient failures with bounded exponential backoff; never retry schema or semantic quarantine indefinitely.
- Write progress continuously and emit final counts for attempted, accepted, skipped, quarantined, retryable, and remaining entries.
- Aggregation reads the durable ledger, not only workflow artifacts.

## Downstream gate

Research starts only when all required entries are `ACCEPTED` or have an explicit reviewed waiver. Import failure retains the prior active research release.

## Acceptance scenarios

1. Kill an import halfway; rerun processes only unfinished entries.
2. Rerun any fully accepted reviewed manifest; it performs zero filing downloads.
3. One invalid filing is quarantined without rolling back other accepted entries.
4. One transient failure is retried within policy and remains visible if exhausted.
5. Discovery after a five-year backfill preserves every reviewed historical entry.
