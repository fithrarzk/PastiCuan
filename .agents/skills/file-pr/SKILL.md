---
name: file-pr
description: File a pull request the right way. Use when the user asks to open, file, or create a PR.
metadata:
  harness: [claude, codex, opencode]
  platform: [darwin, linux]
  scope: ganesa-space
---

# File PR

Before filing, check whether a PR for this branch already exists. Review the diff locally against `origin/development` (or `origin/main` if that's the base) to make sure its contents match the goal.

```bash
git fetch origin
git diff origin/development...HEAD --stat
git diff origin/development...HEAD | head -100
gh pr view --json url 2>&1 | head -5  # already exists?
```

PR titles usually become commit messages, so follow the repository's title conventions. Look at recently merged PRs and Git history for examples. Prefer a concise, human-readable title that explains why the change matters:

BAD
> ❌ perf(server): negotiate permessage-deflate on the websocket

GOOD
> ✅ perf(server): cut websocket frame size by 70%+ with gzipping

For Ganesa Space, use Conventional Commits and plain language (`fix(menfess):`, `docs:`, `feat(auth):`). Body is: problem in 1–2 sentences, then how you fixed it.

**HARNESS IS FORBIDDEN TO INCLUDE ITSELF AS AUTHOR — FOR ALL HARNESSES.** Never add a `Co-authored-by`, `Authored-by`, `Generated-by`, or `Signed-off-by` trailer naming the harness (Muse, Codex, OpenCode, Cursor, Grok, or any agent) to any commit message, commit trailer, or PR body/description. The founder/human is the author; the harness is tooling, not a co-author. This applies to every harness, no exceptions.

Examples from this repo:

BAD
> ❌ Removed implicit workspace carry-over from every "new thread" entry point (cmd+n / cmd+shift+o, sidebar v1/v2 buttons, command palette). New threads inherit only the project from context; branch, worktree, and env mode always come from the configured defaults. Deleted buildContextualThreadOptions, startNewThreadInProjectFromContext, and the v1 sidebar's seed-context machinery.

GOOD
> ✅ My "new worktree" default was ignored when starting new threads on existing worktrees. Super unintuitive. Now your preferences always apply.

Keep it to the why and the how — not the diff dump.

## Ganesa Space checklist before filing

- **Contract drift is not a bare regenerate.** `git add -A && make generate && git diff --quiet` — not `make verify-contract` on an unstaged tree. Generated `packages/api-client/` files are never hand-edited.
- **Docs walk still works.** `node scripts/check-docs.mjs` passes; every new term is in `docs/reference/glossary.md`.
- **One concern per PR.** If the description says "also", split it.
- **UI changes need evidence.** Legacy screenshot `docs/audits/gs-001/screenshots/` vs new, for the same state — not just a new screenshot.

Open a real PR rather than a draft so review bots run.

```bash
gh pr create --title "type(scope): human-readable why" --base development --head <branch> --body "## Outcome ...

## Why ...

[no Co-authored-by trailer — harness forbidden as author]"
```

Always squash-merge — never merge-commit or rebase. Use `gh pr merge --squash` (or GitHub UI: Squash and merge).

Never append the harness as author; the PR body must not contain `Co-authored-by: Muse` / `Co-authored-by: Codex` / `Co-authored-by: OpenCode` or any equivalent for any harness.

If the user also asked to babysit it, continue with the `babysit-pr` skill.

If a PR for this branch already exists, update that one — don't file a duplicate. Review its diff first.

If `gh` is not available, fall back to the GitHub web UI but still follow the title and body conventions.

## Where to look

- Title/style examples: `git log --oneline -20`, `gh pr list --limit 20`
- PR workflow: `AGENTS.md:Pull requests`, `docs/internals/pull-requests.md`
- Glossary for any term: `docs/reference/glossary.md`
