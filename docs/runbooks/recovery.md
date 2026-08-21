# Recovery runbook

## Prerequisites

Open or update one incident record, identify the currently published snapshot and observed healthy deployment, and confirm a verified backup. Any production restore or recovery requires narrowly scoped explicit authorization; preserve evidence and audit history.

## Procedure

1. Classify the failure as delivery, refresh/publication, ingestion, provider, or database.
2. For delivery, keep the current service fail-closed and escalate; a last-good redeploy is a future `DEP-002` procedure requiring explicit authorization and verification.
3. For research, stop failed publication, correct the upstream cause, and rebuild from accepted evidence; retaining/reactivating a prior pair is a future `REL-001` capability, not a current operation.
4. For database issues, use a reviewed forward fix. A restore procedure requires narrow explicit authorization, verified backup evidence, independent review, and compatibility/freshness checks.
5. Verify snapshot signature, release identity, completed session, and dependent commands before closing the incident.

## Hard boundary

Production restore/recovery is not proven by local tests or a backup artifact. Never execute destructive down migrations automatically, and never claim production recovery until external evidence confirms it. If no verified restore exists, remain fail-closed with currently published data and escalate; do not claim a production restore.
