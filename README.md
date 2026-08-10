# Claude Window Optimizer

A Claude Code plugin that keeps your rolling 5-hour usage window aligned to when you actually work, instead of resetting on a guessed ping time.

## Problem

Claude Code's usage limit runs on a rolling 5-hour window that starts with your first message. A ping only does something if it lands *after* the current window has already expired — a ping while a window is still open is a no-op. So the spacing floor for a ping schedule is strictly more than 5 hours (target: 5h05m–5h15m), anchored to when you actually tend to start work.

## What this plugin does (v1)

1. **`/setup-window-optimizer`** (run once) — explains what it's doing as it goes (what an "anchor" is, that the things it creates are pings), computes an initial ping schedule, and creates 4 Cloud Routines for it (see `adr/0001-cloud-routine-scheduling-constraints.md` for why 4, spaced 5h10m apart, never a variable count).
2. **Pings that can do something real, not just a no-op** — setup auto-detects a public GitHub repo (your current project's git remote, or your most recently active public repo) with no question asked; if one's found, all 4 pings check its most recently updated open issues instead of just being a keep-alive — still one cheap `WebFetch` call on the `haiku` model, not "real work." See `adr/0002-useful-ping-content.md` for what's supported today and what isn't yet (email/calendar checks aren't built — disclosed, not silently skipped), and `adr/0003-auto-detect-instead-of-asking.md` for why this is inferred rather than asked.
3. **Logging** — a bundled `UserPromptSubmit` hook timestamps every prompt to a local log (`~/.claude/window-optimizer/prompts.log`), no setup required. Timestamps only — never prompt content.
4. **`/tune-pings`** (run weekly) — recomputes a day-of-week-weighted anchor from the trailing ~4 weeks of logged activity and updates the 4 routines' schedules in place. Never touches what each ping actually does — only when it fires.
5. **Reminder** — a bundled `SessionStart` hook nudges you to run `/tune-pings` if it's been 7+ days since the last tune-up (or since setup, if you've never run one), rate-limited to once a day.

See `adr/` for the design decisions this was built against, and the closed issues in the tracker for how each piece was scoped.

## How to install

Clone the repo, then load it as a plugin for your session:

```bash
git clone https://github.com/yahordauksha/claude-window-optimizer.git
cd claude-window-optimizer
claude --plugin-dir "$(pwd)"
```

Inside that session, run `/setup-window-optimizer` once — it'll ask for a rough start-of-day if there's no logged activity yet, show you the full proposed schedule, and wait for your confirmation before creating anything.

`--plugin-dir` loads the plugin for that session only (this is what's actually been tested end-to-end so far). A persistent install (so it's always available without the flag) is expected to work via Claude Code's normal plugin-install mechanism, but hasn't been verified yet — treat that path as untested until this section says otherwise.

## Status

v1 built: both hooks, both commands, and the underlying schedule/state library are implemented and tested (`pytest` + `ruff` clean). Install the plugin and run `/setup-window-optimizer` once to get started.

## Optional: Desktop local scheduled task

For Desktop app users, `/tune-pings` can also be run on a local weekly timer (Desktop's "Local" Routine type, distinct from the Cloud Routine `/setup-window-optimizer` creates) instead of waiting for the reminder hook. This is a manual, one-time toggle in the Routines panel — no CLI/scriptable path exists for it, so the plugin can't set it up on your behalf.

## License

MIT
