# Recovery runbook

## Prerequisites

Open or update one incident record, identify last good code/deployment and signed snapshot, and confirm a verified backup before any database repair. Preserve evidence and audit history.

## Procedure

1. Classify the failure as delivery, refresh/publication, ingestion, provider, or database.
2. For delivery, redeploy the last healthy SHA/image and verify `/` and `/ready`.
3. For research, stop failed publication, correct the upstream cause, and rebuild from accepted evidence; retain the prior active pair.
4. For database issues, use a reviewed forward fix or verified restore procedure, then rerun compatibility and freshness checks.
5. Verify snapshot signature, release identity, completed session, and dependent commands before closing the incident.

## Hard boundary

Production restore/recovery is not proven by local tests or a backup artifact. Never execute destructive down migrations automatically, and never claim production recovery until external evidence confirms it. If no verified restore exists, remain fail-closed with the last good snapshot.
