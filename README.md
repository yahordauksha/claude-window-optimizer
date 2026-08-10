# Claude Window Optimizer

A Claude Code plugin that keeps your rolling 5-hour usage window aligned to when you actually work, instead of resetting on a guessed ping time.

## Problem

Claude Code's usage limit runs on a rolling 5-hour window that starts with your first message. A ping only does something if it lands *after* the current window has already expired — a ping while a window is still open is a no-op. So the spacing floor for a ping schedule is strictly more than 5 hours (target: 5h05m–5h15m), anchored to when you actually tend to start work.

## What this plugin does (v1)

1. **`/setup-window-optimizer`** (run once) — explains what it's doing as it goes (what an "anchor" is, that the things it creates are pings), asks once when you usually start working, and creates 4 Cloud Routines spaced out from that (see `adr/0001-cloud-routine-scheduling-constraints.md` for why 4, spaced 5h10m apart, never a variable count). It asks rather than guessing from your log on purpose — on a first run the log is just the last few minutes of installing the plugin, so a "computed" anchor there is noise dressed up as a pattern (`adr/0004-setup-always-asks-for-the-anchor.md`). Your answer doesn't need to be precise; `/tune-pings` corrects it from real data later.
2. **Pings that can do something real, not just a no-op** — setup auto-detects a public GitHub repo (your current project's git remote, or your most recently active public repo) with no question asked; if one's found, all 4 pings check its most recently updated open issues instead of just being a keep-alive — still one cheap `WebFetch` call on the `haiku` model, not "real work." See `adr/0002-useful-ping-content.md` for what's supported today and what isn't yet (email/calendar checks aren't built — disclosed, not silently skipped), and `adr/0003-auto-detect-instead-of-asking.md` for why this is inferred rather than asked.
3. **Logging** — a bundled `UserPromptSubmit` hook timestamps every prompt to a local log (`~/.claude/window-optimizer/prompts.log`), no setup required. Timestamps only — never prompt content.
4. **`/tune-pings`** (run weekly) — this is where log data actually gets used: recomputes a day-of-week-weighted anchor from the trailing ~4 weeks of logged activity and updates the 4 routines' schedules in place, correcting whatever you guessed at setup. Declines to re-anchor on fewer than 3 distinct logged days rather than swinging the schedule on noise. Never touches what each ping actually does — only when it fires.
5. **Reminder** — a bundled `SessionStart` hook nudges you to run `/tune-pings` if it's been 7+ days since the last tune-up (or since setup, if you've never run one), rate-limited to once a day.

See `adr/` for the design decisions this was built against, and the closed issues in the tracker for how each piece was scoped.

## How to install

### CLI or Desktop (persistent — recommended)

Works the same way in both: `/plugin` in the CLI and the plugin browser in the Desktop app are two UIs over the same underlying mechanism. Run this once, in either surface:

```
/plugin marketplace add yahordauksha/claude-window-optimizer
/plugin install claude-window-optimizer@claude-window-optimizer
```

(Desktop users: same two steps, just through the plugin browser's UI instead of typing the commands — see [the Desktop docs](https://code.claude.com/docs/en/desktop#install-plugins).)

This is a real, verified install — the plugin registers persistently (`enabledPlugins` in your Claude Code settings) and `/setup-window-optimizer`/`/tune-pings` become available in every future session, no flag needed. Confirmed by actually running the install, checking `claude plugin list`, and opening a completely fresh session with no special flags to see both commands show up.

Once installed, run `/setup-window-optimizer` once — it'll ask roughly when you start your day, show you the full proposed schedule, and wait for your confirmation before creating anything.

### CLI only, session-local (for trying it out without installing)

```bash
git clone https://github.com/yahordauksha/claude-window-optimizer.git
cd claude-window-optimizer
claude --plugin-dir "$(pwd)"
```

Loads the plugin for that one session only — nothing persists, nothing to uninstall afterward. Useful for testing a local change to this repo itself; not what you want for actual day-to-day use (the hooks won't be there in your next normal session).

## Status

v1 built: both hooks, both commands, and the underlying schedule/state library are implemented and tested (`pytest` + `ruff` clean). Install the plugin and run `/setup-window-optimizer` once to get started.

## Optional: Desktop local scheduled task

For Desktop app users, `/tune-pings` can also be run on a local weekly timer (Desktop's "Local" Routine type, distinct from the Cloud Routine `/setup-window-optimizer` creates) instead of waiting for the reminder hook. This is a manual, one-time toggle in the Routines panel — no CLI/scriptable path exists for it, so the plugin can't set it up on your behalf.

## License

MIT
