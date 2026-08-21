# Task Cards

Every implementation begins from one task card and produces one PR. The roadmap controls dependency order; task cards control execution.

Required fields:

```md
# <TASK-ID>: <title>

- Status: proposed | ready | active | review | merged | verified | blocked
- Priority: P0 | P1 | P2 | P3
- Owner/model: orchestrator | sol | luna | reviewer | babysit
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
