# CI/CD runbook

## Prerequisites

Use a task branch and pull request. Read [the CI/CD contract](../specs/ci-cd-contract.md), verify the current head, and keep secrets in protected environments. Do not run production writers from a laptop.

## Procedure

1. Run compile, unit, release, whitespace, quality, workflow-policy, migration, container-smoke, manifest, and security checks applicable to the change.
2. Obtain independent spec/standards review and resolve all threads. Missing, cancelled, neutral, or stale checks are not green.
3. Squash-merge only after required current-head checks pass. The merge may trigger Railway and research workflows independently.
4. Inspect `research-daily`, `idx-filings`, and backup workflow outcomes; record code SHA, release, snapshot IDs, and last-good state.

## Verification and stop

Stop on any failed gate, unreviewed manifest, missing signing key, unavailable evidence, or unverified deployment SHA. A merge alone is not production recovery. Current workflows do not prove cumulative discovery, runtime-resumable ingestion, atomic publication, or exact-SHA Railway linkage; those remain planned contracts.

## Rollback

Keep the prior healthy deployment and last good signed pair. Code rollback redeploys the last-good SHA/image; research rollback appends a prior verified activation when available. Database recovery is forward-fix, never an automatic destructive down migration.
