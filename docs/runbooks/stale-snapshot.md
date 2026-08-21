# Stale Snapshot Runbook

Use this when `/scan` reports an old session or `/range`, `/ta`, or `/decision` loses snapshot evidence.

## Meaning

The stale guard intentionally removes current-use candidate rows after the configured completed-session limit. Dependent commands read the same scan snapshot, so their unavailability is normally one incident, not separate command failures.

## Diagnose in order

1. Record `/status` and `/scan`: snapshot ID, session, mode, coverage, and warnings.
2. In GitHub Actions, inspect the latest `research-daily` artifact and its first failed stage.
3. If candidate readiness failed, record verified profiles, business-scored rows, quant-eligible rows, and per-check status.
4. If ingestion preceded the failure, inspect the exact `idx-filings` import run for timeout, cancellation, quarantine, and remaining rows.
5. Confirm the merged workflow and manifest from `origin/main`; do not diagnose production from a feature branch.
6. Confirm the latest completed IDX session and market-provider coverage.

## Recovery boundaries

- Do not disable or extend the stale guard to hide a failed refresh.
- Do not enable live provider calculations in snapshot-only bot commands.
- Do not rerun `research-daily` repeatedly when its required data has not changed.
- Resume or complete the failed upstream import, then run one non-final research refresh.
- Keep the last good snapshot unchanged until a new candidate passes every publication gate.

After successful publication, allow for the configured bot cache interval, then verify `/status`, `/scan`, and one dependent ticker command.
