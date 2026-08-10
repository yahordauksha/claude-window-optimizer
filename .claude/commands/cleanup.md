---
allowed-tools: Bash(git:*), Bash(gh issue:*), Bash(gh pr:*), Read, Grep, Glob
description: End-of-session workspace hygiene sweep. Removes worktrees/branches that are unambiguously safe (merged into main, or remote-deleted/[gone]) after one batch confirmation, reports anything ambiguous (dirty, unmerged, stale) without touching it, and surfaces orphaned in-progress issues and stale draft PRs. Invoke manually at the end of a coding session.
model: sonnet
version: 1.0.0
---

> Version 1.0.0

You are running an end-of-session hygiene sweep for **Claude Window Optimizer**. The goal is that the Operator can run this once before closing out and trust the workspace is clean — no orphaned worktrees, no dead branches, no silently-stuck issues.

**Context provided:** $ARGUMENTS (none needed — always sweeps the full worktree/branch/issue state)

---

## STEP 1 — Refresh remote state (mechanical)

```bash
git fetch --prune origin
git worktree prune -v
```

---

## STEP 2 — Inventory

```bash
git worktree list --porcelain
git branch -vv
```

Build one entry per non-`main` branch. For each, gather:
- **Worktree path**, if any.
- **Dirty vs. clean** — `git -C <path> status --porcelain`.
- **Gone-remote** — `git branch -vv` showing `: gone]`.
- **Merged into main** — `git merge-base --is-ancestor <branch> origin/main`.
- **Associated PR** — `gh pr list --head <branch> --state all --json number,state,isDraft,mergedAt`.
- **Last commit age** — `git log -1 --format=%cI <branch>`.

---

## STEP 3 — Classify

- **SAFE-MERGED** — clean (or worktree-less) AND (merged-into-main OR PR `state: MERGED`). Auto-remove eligible.
- **GONE** — `[gone]` remote marker AND clean (or worktree-less). Auto-remove eligible.
- **DIRTY** — uncommitted changes present. Never auto-touch.
- **ACTIVE** — an open PR exists, OR last commit within 48h. Leave alone.
- **STALE-UNMERGED** — clean, not merged, no open PR, last commit older than 7 days. Flag for individual confirmation.

Dirty always wins the classification.

---

## STEP 4 — Execute safe removals (one batch, one confirmation)

List every SAFE-MERGED and GONE item together and ask the Operator to confirm the whole batch once. On confirmation:

```bash
git worktree remove <path>   # never --force
git branch -d <branch>       # never -D
```

If `git branch -d` refuses despite the merge-base check saying merged, stop, do not force it, report the discrepancy.

---

## STEP 5 — Issue-tracker cross-checks

**a. Orphaned in-progress issues.** `gh issue list --label "in-progress" --json number,title,updatedAt`. For each, check whether any open PR references it. No open PR and no recent activity (>3 days) → **ORPHANED CLAIM**: report it, don't relabel it yourself.

**b. Stale draft PRs.** `gh pr list --state open --json number,title,isDraft,updatedAt`, filtered to `isDraft: true` and not updated in 14+ days.

---

## STEP 6 — Report

Terminal report only, same shape as `queue-scout`.

```
CLEANUP SWEEP — <N> branches/worktrees checked

✅ SAFE-MERGED — removed after confirmation:
  <branch>   [PR #<n> MERGED, worktree clean]  → worktree + branch removed

🗑 GONE — removed after confirmation:
  <branch>   [remote deleted, no worktree] → branch removed

⚠️ DIRTY — left untouched, needs your attention:
  <branch>   [uncommitted changes]

⏳ STALE-UNMERGED — needs individual confirmation:
  <branch>   [no PR, last commit <date>, <N> days ago]

🟢 ACTIVE — left alone:
  <branch>   [open PR #<n>]

❓ ORPHANED CLAIM — in-progress, no visible activity:
  #<issue> <title>   [no open PR]

📝 STALE DRAFT PR — open, no update in 14+ days:
  #<pr> <title>   [updated <date>]

Recommended next action: <e.g. "nothing else needs attention">
```

If a category is empty, omit it.

---

## HARD RULES

- Never `git worktree remove --force` or `git branch -D`.
- Never auto-delete anything classified DIRTY or STALE-UNMERGED.
- Never touch `main`'s own worktree or branch.
- Never edit issue labels, comment on issues, or relabel an ORPHANED CLAIM.

## Related

- [[Principles]]
- [[Templates/Skills/queue-scout]]
