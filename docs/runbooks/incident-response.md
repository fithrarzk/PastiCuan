# Incident response runbook

## Prerequisites

Have read-only access to production health endpoints and workflow logs, an incident record, the current `origin/main` SHA, and the relevant runbook/spec. Do not request or copy credentials, provider bodies, private URLs, or secret values. Any production restore or destructive data action requires narrowly scoped explicit authorization.

## Detect and triage

Use `/ready`, `/status`, `/scan`, GitHub Actions run logs, and the relevant ingestion report. Record timestamp, code SHA, deployment ID if available, release/snapshot IDs, session, mode, coverage, warnings, and first failed stage. Diagnose production from `origin/main`, not a feature branch.

## Contain

Keep the stale guard and snapshot-only behavior enabled. Do not enable live provider calculations, bypass source/freshness/publication gates, repeatedly rerun an unchanged failed job, or expose credentials/provider bodies. Preserve the last good snapshot and open/update one incident issue.

## Recover and verify

Classified transient stages may retry within bounded policy. Complete required ingestion before refresh; then verify signatures, release identity, freshness, and `/ready` plus dependent commands. If evidence remains incomplete, report `DEGRADED` or `UNAVAILABLE` explicitly.

## Closeout

Document impact, timeline, root cause, evidence, rollback, and follow-up task. Current limitations include non-resumable runtime ingestion, non-atomic quant/scan publication, unverified Railway exact-SHA linkage, and unproven production database recovery. Do not mark any of these resolved without task evidence.
