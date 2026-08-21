# Deployment runbook

## Prerequisites

Merge a reviewed, green current head. Railway must be configured for the repository's `main` branch with webhook secrets and read-only database access only; signing-private-key and writer credentials stay out of Railway.

## Procedure

1. Inspect the Railway deployment and health endpoint `/`.
2. Verify `/ready` reports approved snapshot/scan IDs, release, digest, and freshness state; also inspect GitHub workflow results.
3. Exercise `/status`, `/scan`, and one dependent command after the cache interval.

## Stop and rollback

Stop if health, signature, freshness, release identity, or command checks fail. A successful Railway build does **not** establish exact-SHA linkage before `DEP-001`; do not claim it does. Roll back to the last healthy deployment/image and preserve the last good research snapshot.
