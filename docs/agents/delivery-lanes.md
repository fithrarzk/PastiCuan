# Delivery Lanes and Budgets

Choose one lane before editing. Classification follows the highest-risk file or
behavior in the change; a small diff is not automatically low risk.

| Lane | Use when | Execution | Budget and stop rule |
|---|---|---|---|
| Fast | Documentation, comments, formatting, or a tiny non-behavioral test/config correction with no runtime, workflow, evidence, or contract effect | One root agent, one task worktree and PR, focused validation, self-review, required CI | 20 minutes, 8k context tokens, one correction cycle; stop with a recoverable handoff when exceeded |
| Standard | A bounded application feature, bug fix, or refactor that does not meet any high-risk trigger | One root agent, a short task card, one task worktree and PR, focused TDD, self-review, required CI | 90 minutes, 30k context tokens, two correction cycles; stop with the exact blocker when exceeded |
| High-risk | Migration/schema/grant, financial or statistical semantics, point-in-time behavior, evidence/source policy, release/publication gate, credential/security boundary, production workflow, or destructive/irreversible risk | Decision-complete task card, appropriate Sol design, bounded implementation, fresh independent Standards and Spec review, full verification and guarded rollout | 60k context tokens and a three-hour checkpoint; pause at a safe boundary if it is not merge-ready |

Time spent waiting on an external required check is recorded separately, but a
wait does not authorize unlimited correction loops. Never change lane downward
to avoid a safety control. Escalate upward as soon as the diff touches a
high-risk trigger.

## Efficient execution

- Keep one isolated task worktree. Do not create separate orchestrator and
  implementation worktrees for the same concern.
- Fast and Standard lanes use the root agent directly. Do not spawn an
  implementer, reviewer, or babysitter by default.
- Use sub-agents only for disjoint parallel ownership or mandatory high-risk
  review. Poll short CI directly; use a babysitter only for long-running checks
  or active review discussion.
- During Fast and Standard development, run only focused checks. Let required PR
  CI run the full suite once. High-risk work also runs the complete local
  verification required by its task card.
- Include task-adjacent documentation and the final handoff in the same PR.
  Create a separate documentation task only for a genuinely separate concern.
- Each handoff records elapsed time, approximate context budget used,
  correction cycles, model, commands, and exact outcomes so the next five tasks
  can be compared with these targets.

## Records and review

A Fast task may use the PR body as its task note: outcome, non-goals, changed
paths, focused check, rollback, and lane justification. It needs a `CLAIMS.md`
entry only when it is roadmap work or could collide with another active writer.

Standard and High-risk tasks use task cards. Only High-risk work requires fresh
independent review before autonomous merge. Fast and Standard work still needs
root diff review, green current-head required checks, and all repository safety
boundaries.

Post-merge verification is proportional: verify the merge SHA and only the
workflows or production surfaces the change can affect. An intentionally
non-triggered irrelevant production workflow is `not applicable`, not missing
evidence.
