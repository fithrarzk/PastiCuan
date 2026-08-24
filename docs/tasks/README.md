# Task Cards

Every concern produces one PR and starts by selecting a
[delivery lane](../agents/delivery-lanes.md). Fast non-roadmap work may use a
compact task note in the PR body; Standard and High-risk work begins from one
task card. The roadmap controls dependency order; task cards control execution.

Required fields:

```md
# <TASK-ID>: <title>

- Status: proposed | ready | active | review | merged | verified | blocked
- Priority: P0 | P1 | P2 | P3
- Owner/model: orchestrator | sol | luna | reviewer | babysit
- Reasoning effort: low | medium | high | xhigh
- Context budget: exact files/specs plus an optional token ceiling
- Retry ceiling: maximum automated attempts and retryable classes
- Escalation condition: exact condition that stops autonomous retries
- Parallelism: maximum agents and any serialized integration owner
- Base SHA: <origin/main sha>
- Branch: <type/TASK-ID-name>
- Worktree: <path>
- Depends on: <task IDs or none>
- File ownership: <exact paths>
- Merge policy: autonomous | human-gated

## Outcome
## Non-goals
## Current evidence
## Invariants
## Implementation contract
## Acceptance tests
## Rollout and rollback
## Handoff
```

Tasks are parallel-ready only when dependencies are verified and file ownership does not overlap another active task. Status `merged` is not `verified` until required post-merge evidence exists.

Fast task notes contain the outcome, non-goals, changed paths, lane
justification, focused validation, and rollback. Their default limit is one
correction cycle; scope growth promotes the work to Standard or High-risk before
further editing.

Only the orchestrator edits [CLAIMS.md](CLAIMS.md) or assigns task issues. Implementation and review agents receive an existing claim; they never choose one themselves.
