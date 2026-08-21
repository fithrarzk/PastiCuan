---
name: babysit-pr
description: Monitor a pull request through review and CI. Use when the user asks to watch, monitor, or babysit a PR.
metadata:
  harness: [claude, codex, opencode]
  platform: [darwin, linux]
  scope: pasticuan
---

# Babysit PR

All the repos we work in have various AI review bots. They're helpful, even if they are not always right.

If your harness offers tools to monitor a PR, use them so you can respond when comments arrive. Otherwise, poll the PR for new comments and checks.

Only act on checks and comments newer than the latest push. Verify every bot finding against the source before changing code. Fix real findings and CI failures, distinguish repository failures from infrastructure flakes, and reply with a written reason when dismissing false positives.

Keep an eye on changes to `main` and synchronize when needed. If an overlapping PR makes this one obsolete, stop monitoring and report it; close it only when the task card or standing authorization covers closure.

If a review bot leaves feedback you believe is not worth addressing, reply and resolve the comment. Format comments left on the founder's behalf as:

```md
[MODEL-SLUG] RESPONDING ON BEHALF OF FOUNDER
-----

[actual reply]
```

Do not let review feedback expand the PR beyond the user's original goal. Address real shortcomings, but avoid scope creep.

If nothing has changed, stay quiet rather than posting filler comments. Stop when the review bots and required checks are green on the latest commit. Merge when the task card says `merge_policy: autonomous` and `AGENTS.md` permits it; otherwise report the exact gate.

## PastiCuan ready gate

A PR is ready only when:

- **Required CI is green** on the current head. Stable gates are defined in `docs/specs/ci-cd-contract.md`.
- **A missing, skipped, cancelled, stale, or unconfigured required gate is not green.** Local success diagnoses CI but cannot satisfy a protected GitHub check.
- **Core local evidence** includes compilation, unit tests, research-release integrity, and `git diff --check` from `AGENTS.md`.
- **Class-specific evidence** exists for workflow, migration, manifest, research, container, or deployment changes.

## How to babysit here

1. **Poll:** `gh pr checks <number>` and `gh pr view <number> --comments` — compare timestamps against `git log --oneline -1` for the latest push.
2. **Verify:** open the flagged file/line, confirm the finding is real (not a stale review on an old commit).
3. **Fix:** make the smallest change that addresses a verified finding; push, then re-poll. If CI fails due to runner infrastructure, run equivalent checks locally to diagnose it, but keep the required remote gate blocked:
   ```bash
   python -m compileall -q analysis data storage operations telegram_utils bot.py bot_webhook.py
   python -m unittest discover -s tests -v
   python -m operations.research_cli check-research-release
   git diff --check
   ```
4. **Waive:** if false positive, reply in the thread with evidence and resolve it through GitHub.
5. **Synchronize:** if `main` moved, fetch and update the task branch according to `AGENTS.md`; rerun checks and push.
6. **Merge:** if the task is autonomous and every gate is green, use `gh pr merge --squash --delete-branch` and verify post-merge workflows.

## Where to look

- CI: `.github/workflows/` and `docs/specs/ci-cd-contract.md`
- Task and authority: `docs/tasks/`, `AGENTS.md`, and `docs/agents/autonomy.md`
- Glossary for any term: `CONTEXT.md`
