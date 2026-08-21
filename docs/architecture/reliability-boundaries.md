# Reliability boundaries

| Boundary | Current guarantee | Stop condition / limitation |
| --- | --- | --- |
| Evidence | [Repository queries](../../storage/repository.py) enforce checksums, source metadata, quarantine reporting, and `available_at <= as_of` | Missing or conflicting official evidence yields degraded/unavailable output; fallback is disclosed and does not open action gates |
| Ingestion | [CLI ingestion](../../operations/research_cli.py) and [artifact acquisition](../../data/ingestion.py) are storage-idempotent | Not runtime-resumable before `ING-003`; discovery is a review draft, not cumulative production history |
| Candidate/publication | [Snapshot validation](../../analysis/snapshots.py) rejects candidate files for delivery; signatures and checksums are verified | [Snapshot lifecycle](../specs/snapshot-lifecycle.md) requires one atomic activation, which is not implemented before `REL-001`; formal pair retention is planned |
| Analytics | Formula/release identity is persisted; status can remain `SHADOW` | No claim of validated analytics until persisted validation evidence passes all gates |
| Delivery | Snapshot-only bot path, bounded cache, stale guard, and cold-start fail-closed behavior | Cache is not durable production evidence; Railway exact-SHA linkage is unverified before `DEP-001` |
| Recovery | Failed scan builds fail closed without replacing the published scan; [stale guard](../runbooks/stale-snapshot.md) keeps current-use gates closed | Production database restore and recovery have not been proven; never run destructive down migrations automatically |

## Operator invariants

Never disable freshness, source-quality, coverage, publication, or risk gates. Never use a candidate as production evidence, enable live provider calculations in snapshot-only commands, or call an unavailable result a successful scan. A Railway deployment being green does not prove it runs the exact `main` SHA; [the deployment contract](../specs/ci-cd-contract.md) is not proof of current implementation.
