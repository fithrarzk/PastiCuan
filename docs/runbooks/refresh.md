# Refresh runbook

## Prerequisites

Confirm `origin/main`, the active research release, completed session/calendar, accepted evidence coverage, and a usable last good snapshot. Do not refresh merely to hide a stale guard.

## Procedure

1. Run market history refresh and inspect its report.
2. Run `run-daily-research` with the checked-in release; use `--final-attempt` only for the scheduled final attempt.
3. Check candidate readiness, source/freshness/coverage gates, signatures, and quant/scan identities.
4. After publication, wait the configured bot cache interval and verify `/ready`, `/status`, `/scan`, and one dependent ticker command.

## Stop and rollback

Stop on any missing, stale, quarantined, conflicting, unsigned, or unavailable evidence. An `UNAVAILABLE` build must not replace the last good snapshot. Current quant and scan writes do not prove the accepted atomic release boundary before `REL-001`; never describe them as atomic publication.
