# Claude Window Optimizer

A Claude Code plugin that makes your 5-hour usage window reset on *your* schedule instead of whenever you happened to send your first message.

## Problem

Claude Code's usage limit runs on a 5-hour window that starts with your first message — so if you fire off one question at 7am, your window is already half-spent by the time you actually sit down. You can reset it earlier by sending a message once the previous window has expired, but that only works if it lands *after* expiry: a message sent while a window is still open is a no-op. That means the spacing floor for a reset schedule is strictly more than 5 hours (target: 5h05m–5h15m), starting from the time you actually want your day's first fresh window.

### Where that claim comes from

Anthropic documents that the window exists and resets on a schedule — including the in-product message `You've hit your session limit · resets 3:45pm`. A single named reset time implies a fixed window boundary rather than a continuously sliding one.

What Anthropic does **not** document is the part this plugin depends on: that a scheduled message opens a fresh window. That comes from operational use. Before this plugin existed, its author ran two hand-made Cloud Routines — "Start session at 7:30" and "Start session at 13:00", each sending a one-word message — for weeks, and observed windows starting at those ping times rather than at the first real message of the day. The annoyance that motivated building this at all (a 7am ping opening a window that then expires mid-workday) *is* that mechanic working, just badly timed.

This is recorded here because it's the load-bearing assumption under everything else, and it previously lived only in the author's head — an outside reviewer correctly flagged the README for asserting it with no basis. If you're evaluating this plugin, satisfy yourself about this claim first. It's directly checkable in about five hours: send one message, note the reset time, send another after the window expires, and check whether the new reset time tracks the second message.

## What this plugin does (v1)

1. **`/setup-window-optimizer`** (run once) — asks one question: what time you want your window to reset each day. From that it schedules 4 daily resets, 5h10m apart, so your window is fresh when you sit down and never expires mid-afternoon (see `adr/0001-cloud-routine-scheduling-constraints.md` for why 4 and why that spacing). It asks rather than guessing from your log on purpose — on a first run the log is just the last few minutes of installing the plugin, so a "computed" answer there is noise dressed up as a pattern (`adr/0004-setup-always-asks-for-the-anchor.md`). Your answer doesn't need to be precise; `/tune-pings` corrects it from real data later.
2. **The scheduled messages do something real, not just a no-op** — the resets work by sending a small message on a schedule; setup auto-detects a public GitHub repo **that you own** (your current project's git remote, or your most recently active public repo) with no question asked — it will not wire your scheduled agents to someone else's issue tracker just because that's the directory you happened to be standing in (`adr/0008-only-auto-detect-repos-you-own.md`), and if one's found, each message reports that repo's most recently updated open issues instead of just saying "hello." Still one cheap `WebFetch` call on the `haiku` model, not "real work." See `adr/0002-useful-ping-content.md` for what's supported today and what isn't yet (email/calendar checks aren't built — disclosed, not silently skipped), and `adr/0003-auto-detect-instead-of-asking.md` for why this is inferred rather than asked.
3. **Logging** — a bundled `UserPromptSubmit` hook timestamps every prompt to a local log (`~/.claude/window-optimizer/prompts.log`), no setup required. Timestamps only — never prompt content.
4. **`/tune-pings`** (run weekly) — this is where log data actually gets used: recomputes your reset times from the trailing ~4 weeks of *all* logged activity, picking the schedule that spreads your real usage most evenly across the four windows so no single window runs dry first (`adr/0007-balance-window-load-not-start-of-day.md`), correcting whatever you guessed at setup. Declines to re-anchor on fewer than 3 logged days or 200 logged prompts rather than swinging your schedule on noise — the volume floor is measured, reproduce it with `python3 tools/measure_anchor_stability.py`. Only changes *when* the resets happen, never what the scheduled message does.
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

Once installed, run `/setup-window-optimizer` once — it'll ask what time you want your window to reset, show you the full proposed schedule, and wait for your confirmation before creating anything.

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
