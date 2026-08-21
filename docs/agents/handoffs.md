# Agent Handoff

Use this template at every task or PR boundary.

```md
# <TASK-ID>: <outcome>

- Status: complete | blocked | failed
- Base: <sha>
- Final: <sha>
- Branch/worktree: <name/path>
- PR: <url or not filed>
- Merge policy: autonomous | human-gated

## Changed

- <file>: <behavioral outcome>

## Evidence

- `<command>`: <result>
- CI/review: <current-head result>
- Production/workflow: <result or not applicable>

## Safety and compatibility

- Invariants preserved: <list>
- Migration/rollback: <steps or not applicable>

## Remaining

- Limitations: <list>
- Unresolved decisions: <list>
- Recommended next task: <TASK-ID>
```

Do not mark a task complete when the PR is merely open, CI is stale, a required gate is absent, or post-merge production verification is still pending.
