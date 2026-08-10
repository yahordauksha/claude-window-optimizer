# Claude Window Optimizer

A Claude Code plugin that keeps your rolling 5-hour usage window aligned to when you actually work, instead of resetting on a guessed ping time.

## Problem

Claude Code's usage limit runs on a rolling 5-hour window that starts with your first message. A ping only does something if it lands *after* the current window has already expired — a ping while a window is still open is a no-op. So the spacing floor for a ping schedule is strictly more than 5 hours (target: 5h05m–5h15m), anchored to when you actually tend to start work.

## What this plugin does (v1)

1. **`/setup-window-optimizer`** (run once) — computes an initial ping schedule and creates a Cloud Routine for it.
2. **Logging** — a bundled `UserPromptSubmit` hook timestamps every prompt to a local log, no setup required.
3. **`/tune-pings`** (run weekly) — recomputes the anchor from the trailing ~4 weeks of logged activity and updates the Routine's schedule.
4. **Reminder** — a bundled `SessionStart` hook nudges you to run `/tune-pings` if it's been 7+ days, rate-limited to once a day.

See the full v1 plan and open design questions in the project's issue tracker.

## Status

Early scaffold — commands and hooks are being built out via this repo's own `.claude/` implementation pipeline (`/implement` against the ready-to-build issue queue). Not yet installable/functional.

## Optional: Desktop local scheduled task

For Desktop app users, `/tune-pings` can also be run on a local weekly timer (Desktop's "Local" Routine type, distinct from the Cloud Routine `/setup-window-optimizer` creates) instead of waiting for the reminder hook. This is a manual, one-time toggle in the Routines panel — no CLI/scriptable path exists for it, so the plugin can't set it up on your behalf.

## License

MIT
