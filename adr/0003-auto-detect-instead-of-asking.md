# ADR-0003: Auto-detect the ping repo instead of asking

Supersedes part of [ADR-0002](0002-useful-ping-content.md) — not the whole thing, just its "never guess a repo the user didn't name" stance. ADR-0002's other decisions (kind set, WebFetch-only, `/tune-pings` never touches content) stand unchanged.

## Context

ADR-0002 shipped a setup flow that asked the user, in one optional question, whether they wanted useful pings and which repo to check. Direct Operator feedback on seeing that question in practice: *"you shouldn't ask that. Just make shit up. you would already know the user a little bit."*

This is a real, deliberate correction to a design choice ADR-0002 made explicitly ("never guess a repo the user didn't name" was a named hard rule) — not a bug. Per this project's own established discipline (see the `agent-ecosystem` vault's "surface conflicts, don't average them"), the right move is to pick one stance clearly and record why, not blend "ask a little less" into the old design.

## Decision

**`/setup-window-optimizer` no longer asks anything about ping content.** STEP 2b now runs `scripts/detect_repo.py`, which tries (in order):

1. The current project's own git remote (`git remote get-url origin`, parsed for a GitHub URL) — the strongest available signal, since it's literally "what's open right now."
2. The account's most recently pushed-to **public** repo, via `gh repo list`.

Whichever candidate is found is confirmed public via `gh repo view` before being trusted (a private repo would silently fail the ping's own unauthenticated GitHub API call otherwise).

**If a repo is found, every one of the 4 slots gets the `github-issues` kind for it** — not just slots that seem like "coding hours." Reasoning: anyone installing a Claude Code plugin is, by strong prior, doing development work; there's no reliable per-slot "this is your coding time" signal without asking (which is exactly what's being removed), so defaulting *all* slots to the one well-grounded useful check is more honest than fabricating a time-of-day split with no real basis.

**If nothing is found, every slot falls back to `simple`** — still no fabrication, just an honest "couldn't infer anything, so no-op" rather than an invented default.

The detection result is *stated*, not *asked about*, in STEP 4's existing batch-confirmation proposal — the user still sees and confirms it before anything is created, same safety-surface discipline as before. What changed is there's no separate question turn before that point.

## Alternatives considered

- **Keep asking, but default the answer to "yes"** — rejected: still an interruption, and the Operator's feedback was about the interruption itself, not the default's polarity.
- **Infer a rhythm split per slot from typical work patterns** (e.g. "9-to-5 coding, evenings off") — rejected: no real signal grounds *which* slot maps to what for an unknown user; assigning the same well-grounded check to all 4 slots is more honest than a fabricated time-of-day guess.
- **Use the conversation's own context to personalize** (something the Operator's feedback implied — "you would already know the user a little bit") — not generalizable: this command has to work for anyone who installs the plugin, not just inside a session that happens to already know the Operator. Auto-detection from real, inspectable signals (git remote, `gh` account state) is the generalizable version of "already know the user a little" — it doesn't require conversational memory to work correctly for a stranger.

## Consequences

- Setup is now genuinely closer to "one command, done" — the original plan's whole pitch — with zero required or optional questions when log data already exists.
- The auto-detected repo could occasionally be "wrong" (e.g. cwd happens to be a fork, or the most-recently-pushed repo isn't the one the user cares about most) — STEP 4's confirmation is the safety net; the user can course-correct there or just re-run with a different cwd.
- `scripts/detect_repo.py` and `lib/window_optimizer/repo_detect.py` are new, tested surface area: URL parsing is pure and unit-tested; the `gh`-dependent paths are tested via mocked subprocess output; the cwd-git-remote path additionally has a real end-to-end test that runs the actual script against this repo's own real origin.
