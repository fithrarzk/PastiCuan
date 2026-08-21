---
name: file-pr
description: File a pull request the right way. Use when the user asks to open, file, or create a PR.
metadata:
  harness: [claude, codex, opencode]
  platform: [darwin, linux]
  scope: pasticuan
---

# File PR

Before filing, check whether a PR for this branch already exists. Review the diff locally against `origin/main` to make sure its contents match the task card.

```bash
git fetch origin
git diff origin/main...HEAD --stat
git diff origin/main...HEAD | head -100
gh pr view --json url 2>&1 | head -5  # already exists?
```

PR titles usually become commit messages, so follow the repository's title conventions. Look at recently merged PRs and Git history for examples. Prefer a concise, human-readable title that explains why the change matters:

BAD
> ❌ perf(server): negotiate permessage-deflate on the websocket

GOOD
> ✅ perf(server): cut websocket frame size by 70%+ with gzipping

For PastiCuan, use Conventional Commits and plain language. The body states the outcome, why it matters, verification, and operational impact.

**HARNESS IS FORBIDDEN TO INCLUDE ITSELF AS AUTHOR — FOR ALL HARNESSES.** Never add a `Co-authored-by`, `Authored-by`, `Generated-by`, or `Signed-off-by` trailer naming the harness (Muse, Codex, OpenCode, Cursor, Grok, or any agent) to any commit message, commit trailer, or PR body/description. The founder/human is the author; the harness is tooling, not a co-author. This applies to every harness, no exceptions.

Keep it to the why and the how — not the diff dump.

## PastiCuan checklist before filing

- **Core gates pass.** Run the focused task checks and the full commands in `AGENTS.md`.
- **Research release is coherent.** Calculation changes update `data/research_release.json`; unrelated changes do not.
- **Point-in-time and fail-closed behavior remain intact.** Missing or stale evidence is not replaced with an estimate.
- **Workflow changes are safe.** Review permissions, concurrency, timeouts, recursion, secret names, and failure paths.
- **Docs use repository vocabulary.** New domain terms are defined in glossary-only `CONTEXT.md`.
- **One concern per PR.** If the description says "also", split it.
- **Task evidence exists.** Include acceptance-test results and the handoff fields from `docs/agents/handoffs.md`.

Open a real PR rather than a draft so review bots run.

```bash
gh pr create --title "type(scope): human-readable why" --base main --head <branch> --body "## Outcome ...

## Why ...

[no Co-authored-by trailer — harness forbidden as author]"
```

Always squash-merge — never merge-commit or rebase. Use `gh pr merge --squash` (or GitHub UI: Squash and merge).

Never append the harness as author; the PR body must not contain `Co-authored-by: Muse` / `Co-authored-by: Codex` / `Co-authored-by: OpenCode` or any equivalent for any harness.

If the user also asked to babysit it, continue with the `babysit-pr` skill.

If a PR for this branch already exists, update that one — don't file a duplicate. Review its diff first.

If `gh` is unavailable or unauthenticated, push the task branch and report authentication as the single blocked action. Never ask for or embed a token in chat or the repository.

## Where to look

- Title/style examples: `git log --oneline -20`, `gh pr list --limit 20`
- PR workflow: `AGENTS.md`, `docs/agents/autonomy.md`, and `docs/specs/ci-cd-contract.md`
- Glossary for any term: `CONTEXT.md`
