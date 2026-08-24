# PastiCuan Documentation

Start with the domain glossary in [CONTEXT.md](../CONTEXT.md) and the operating contract in [AGENTS.md](../AGENTS.md).

The root [README](../README.md) describes the product. [DEPLOY_FREE](../DEPLOY_FREE.md) is the operator setup guide; when an incident note or roadmap explicitly marks a capability as not yet implemented, that current-state evidence takes precedence over aspirational deployment text.

## Map

- [Current program handoff](status/2026-08-24-program-handoff.md): verified delivery, production blockers, shutdown state, and next task.
- [Task system](tasks/README.md): task cards, dependency rules, and status.
- [Master roadmap](tasks/ROADMAP.md): ordered reliability, analytics, and automation work.
- [Task claims](tasks/CLAIMS.md): the single orchestrator-owned assignment registry.
- [Worktrees and model routing](agents/worktrees.md): parallel-agent execution rules.
- [Delivery lanes and budgets](agents/delivery-lanes.md): risk classification, time/token limits, review, and stop rules.
- [Autonomy and authority](agents/autonomy.md): standing authorization, safety boundaries, and escalation.
- [Handoffs](agents/handoffs.md): the evidence required between agents.
- [Stale snapshot runbook](runbooks/stale-snapshot.md): diagnose `/scan` and dependent-command unavailability.
- [CI/CD contract](specs/ci-cd-contract.md): required checks, merge, deploy, and recovery behavior.
- [Ingestion contract](specs/ingestion-contract.md): cumulative discovery and resumable imports.
- [Snapshot lifecycle](specs/snapshot-lifecycle.md): atomic publication and last-good behavior.

## Architecture

- [System map](architecture/system-map.md): services, owners, stores, and source-of-truth boundaries.
- [Data lifecycle](architecture/data-lifecycle.md): filing-to-snapshot evidence flow and point-in-time rules.
- [Reliability boundaries](architecture/reliability-boundaries.md): fail-closed guarantees and known gaps.

## Reference

- [Command and data dictionary](reference/command-data-dictionary.md): interfaces, evidence identity, and test seams.
- [Model-card index](models/README.md): current formula identities and validation status.

## Runbooks

- [CI/CD](runbooks/ci-cd.md) · [Backfill](runbooks/backfill.md) · [Refresh](runbooks/refresh.md)
- [Deployment](runbooks/deployment.md) · [Recovery](runbooks/recovery.md) · [Incident response](runbooks/incident-response.md)

Future specifications belong under `docs/specs/`, operational procedures under `docs/runbooks/`, system explanations under `docs/architecture/`, and difficult-to-reverse decisions under `docs/adr/`.
