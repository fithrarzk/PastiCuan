# PastiCuan Documentation

Start with the domain glossary in [CONTEXT.md](../CONTEXT.md) and the operating contract in [AGENTS.md](../AGENTS.md).

## Map

- [Task system](tasks/README.md): task cards, dependency rules, and status.
- [Master roadmap](tasks/ROADMAP.md): ordered reliability, analytics, and automation work.
- [Worktrees and model routing](agents/worktrees.md): parallel-agent execution rules.
- [Autonomy and authority](agents/autonomy.md): standing authorization, safety boundaries, and escalation.
- [Handoffs](agents/handoffs.md): the evidence required between agents.
- [Stale snapshot runbook](runbooks/stale-snapshot.md): diagnose `/scan` and dependent-command unavailability.
- [CI/CD contract](specs/ci-cd-contract.md): required checks, merge, deploy, and recovery behavior.
- [Ingestion contract](specs/ingestion-contract.md): cumulative discovery and resumable imports.
- [Snapshot lifecycle](specs/snapshot-lifecycle.md): atomic publication and last-good behavior.

Future specifications belong under `docs/specs/`, operational procedures under `docs/runbooks/`, system explanations under `docs/architecture/`, and difficult-to-reverse decisions under `docs/adr/`.
