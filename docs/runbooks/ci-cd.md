# CI/CD runbook

## Prerequisites

Use a task branch and pull request. Read [the CI/CD contract](../specs/ci-cd-contract.md), verify the current head, and keep secrets in protected environments. Do not run production writers from a laptop.

## Procedure

1. Run the current core checks locally: compile, unit tests, research-release check, and diff whitespace. Pull requests produce the required `test`, `unit`, `quality`, `workflow-policy`, `migration`, `container-smoke`, `manifest-validate`, and `security` contexts. Generated-branch validation additionally verifies the requested remote head before producing those same stable contexts.
2. Obtain independent spec/standards review and resolve all threads. Missing, cancelled, neutral, or stale checks are not green.
3. Confirm the active ruleset requires all eight stable contexts with strict current-head freshness and no bypass, then squash-merge only after those checks pass. The merge may trigger Railway and research workflows independently.
4. Inspect `research-daily`, `idx-filings`, and backup workflow outcomes; record code SHA, release, snapshot IDs, and last-good state.

## Verification and stop

Stop on any failed gate, unreviewed manifest, missing signing key, unavailable evidence, or unverified deployment SHA. A merge alone is not production recovery. Current workflows do not prove cumulative discovery, runtime-resumable ingestion, atomic publication, or exact-SHA Railway linkage; those remain planned contracts.

## Rollback

Current rollback is fail-closed escalation: keep the currently published snapshot and healthy deployment unchanged, and open an incident when a check or deployment fails. Redeploying a recorded last-good artifact and reactivating a prior signed pair are accepted future procedures under `DEP-002`/`REL-001`, not currently executable guarantees. Database recovery is forward-fix, never an automatic destructive down migration.
