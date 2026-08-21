# Reliability boundaries

| Boundary | Current guarantee | Stop condition / limitation |
| --- | --- | --- |
| Evidence | Checksums, source metadata, quarantine reporting, and `available_at <= as_of` queries | Missing or conflicting official evidence yields degraded/unavailable output; fallback is disclosed and does not open action gates |
| Ingestion | Accepted artifacts are storage-idempotent | Not runtime-resumable before `ING-003`; discovery is a review draft, not cumulative production history |
| Candidate/publication | Candidate snapshots are rejected by approved loaders; signatures and checksums are verified | Quant and scan publication are not yet one atomic activation before `REL-001` |
| Analytics | Formula/release identity is persisted; status can remain `SHADOW` | No claim of validated analytics until persisted validation evidence passes all gates |
| Delivery | Snapshot-only bot path, bounded cache, stale guard, and cold-start fail-closed behavior | Cache is not durable production evidence; Railway exact-SHA linkage is unverified before `DEP-001` |
| Recovery | Failed refresh retains prior last-good state; recovery procedures are forward-fix oriented | Production database restore and recovery have not been proven; never run destructive down migrations automatically |

## Operator invariants

Never disable freshness, source-quality, coverage, publication, or risk gates. Never use a candidate as production evidence, enable live provider calculations in snapshot-only commands, or call an unavailable result a successful scan. A Railway deployment being green does not prove it runs the exact `main` SHA.
