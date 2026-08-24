# Agent Autonomy and Authority

## Default mode

The repository owner delegates routine software delivery to the orchestrator. Within an accepted roadmap task, agents should continue from investigation through implementation, verification, commit, PR, review, green CI, squash merge, deployment, and post-deployment checks without asking for repeated permission.

This authorization is durable repository guidance. It does not override GitHub, host, sandbox, billing, or secret-management controls.

Current-state warning: until roadmap task `ING-003` is verified, IDX filing ingestion is idempotent at storage but not runtime-resumable and may re-download accepted entries. Do not dispatch it as though safe resume already exists. Delivery effort is selected through [risk-tiered lanes](delivery-lanes.md); autonomy never lowers a safety boundary.

## Standing authorization

Agents may autonomously:

- read repository, CI, PR, deployment, and non-secret operational state;
- fetch and create isolated worktrees, branches, commits, and PRs;
- edit code, tests, documentation, workflows, and additive migrations within a task card;
- push task branches, request review, address feedback, and rerun failed deterministic checks;
- squash-merge when branch rules, task policy, independent review, and current-head checks allow it;
- delete merged task branches and remove their worktrees;
- dispatch non-destructive ingestion, research, validation, backup, deployment, and smoke-test workflows;
- deploy reviewed code and activate a research candidate only through its existing publication gates;
- open or update one incident issue and restore an already recorded last-good code or research release.

## Fail-closed boundaries

Agents must not silently:

- print, copy, rotate, or broaden secrets and credentials;
- force-push, delete production data, execute destructive down migrations, or rewrite evidence history;
- lower freshness, coverage, point-in-time, source, validation, or publication gates;
- promote a research model without evidence for the exact immutable calculation digest;
- add paid infrastructure, change billing, or grant/revoke human access;
- bypass required checks, unresolved review, environment protection, or platform approval.

When a boundary is reached, finish every safe prerequisite and provide one exact blocked action. Lack of authentication is not solved by embedding tokens in the repository.

## Change classes

| Class | Examples | Merge | Production action |
|---|---|---|---|
| Routine | docs, tests, bounded fixes, non-production refactor | Fast/Standard lane after root diff review and green required checks | Only relevant smoke checks |
| Research | formula, threshold, factor, range, validation semantics | Autonomous merge only with release revision and independent research review | Shadow only until exact-digest validation |
| Data | manifest, parser, source policy, issuer profile | Autonomous after semantic validation | Resume is allowed only after `ING-003` is verified; publication gates remain closed until ready |
| Platform | workflow, additive migration, deploy configuration | Autonomous after security and migration checks | Protected environment and last-good recovery |
| Restricted | destructive schema/data, secret rotation, safety-gate reduction, access/billing | No standing authorization | Explicit narrowly scoped owner action |

## Authentication bootstrap

The GitHub CLI must have a valid repository-scoped identity. Verify with:

```bash
gh auth status
gh api user --jq .login
gh repo view --json nameWithOwner,defaultBranchRef
```

If this fails, the owner performs the one-time interactive login. Agents never request a token in chat or commit one. After authentication, the orchestrator audits rulesets, required checks, Actions permissions, environments, secrets by name only, auto-merge, and Railway deployment linkage before enabling unattended delivery.

## Accountability

Autonomy increases evidence requirements. Every autonomous task must leave a task card, commits, PR discussion, current-head checks, independent review, deployment/result identifiers, and a structured handoff. Failure retains the last-good release and creates one actionable incident; it never fabricates completion.
