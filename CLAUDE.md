# Claude Window Optimizer — Development Rules

A Claude Code plugin (not a service, no backend) — see `README.md` for what it does. This file governs work on the plugin's own source; the plugin's *installed* behavior (hooks, commands) is a separate concern from how we build it.

## Tech stack

- Plugin manifest: `.claude-plugin/plugin.json`
- Commands: Markdown slash-commands in `commands/` (plugin-root convention, not this repo's own `.claude/commands/` — see "Two `.claude` surfaces" below)
- Hooks: stdlib-only Python 3 scripts in `hooks/`, registered via `hooks/hooks.json`. **No pip dependencies** — a hook runs inside whatever Python the end user's machine has; requiring a `pip install` for a hook to fire is a real adoption blocker, not a style preference.
- Scheduling: Cloud Routines, created/updated via the `RemoteTrigger` tool (`action: create`/`update`/`list`) — **not** `CronCreate`/`CronList`/`CronDelete`, which is a different, session-scoped, in-memory reminder mechanism (gone when the session ends, 7-day auto-expiry) and cannot back a persistent, account-level Routine. See `adr/0001-cloud-routine-scheduling-constraints.md`. `RemoteTrigger` has no delete action — routines can only be deleted via https://claude.ai/code/routines, which is why the slot count is fixed at 4 forever rather than ever shrinking.
- Tests: `pytest`, dev-only dependency (never required at hook-runtime).
- Lint: `ruff`.

## Two `.claude` surfaces — don't confuse them

- **`.claude/agents/`, `.claude/commands/`** — this repo's own implementation pipeline (core-implementer, test-writer, edge-case-auditor, triage, implement, spec, shape, queue-scout, cleanup), installed from `yahordauksha/agent-ecosystem`. Used to *build* this plugin. Never shipped to end users.
- **`commands/`, `hooks/`, `.claude-plugin/`** — the actual plugin product. What ships when someone installs this plugin.

## Development workflow

Same discipline as this repo's installed `implement` skill: branch/worktree isolation from `main`, GitHub Issues track all work (`gh issue`), a PR only opens once tests + edge-case-audit + `/code-review` all pass. See `.claude/commands/implement.md` for the full cycle — don't hand-roll a different one.

### Design decisions are the Operator's to make

The ping-spacing mechanism and how `/tune-pings` applies a schedule update are resolved — see `adr/0001-cloud-routine-scheduling-constraints.md`, grounded in the real `RemoteTrigger` API, not assumed. For anything that would change those decisions, or any other change that materially reshapes the plugin, stop and ask using a concrete options-based question rather than reopening the ADR's reasoning ad hoc.

## Agent Safety Surface — Never Touch Autonomously

This plugin's whole mechanism is a **live, persistent, account-level Cloud Routine** — not a local file, not something scoped to this repo. A wrong or duplicated Routine keeps firing on its own schedule until someone notices and manually removes it.

- **Creating a new Cloud Routine** (`/setup-window-optimizer`'s core action) always requires a fresh, explicit batch confirmation before executing — never a low-stakes/reversible default, even though the whole "one command, done" pitch makes a silent apply tempting. This is the higher-stakes action: it spins up new persistent infrastructure, and routines can't be deleted via the API if it goes wrong (only disabled/removed manually via https://claude.ai/code/routines) — so a wrong or duplicated Routine keeps firing until a human notices and cleans it up by hand.
- **Updating an existing Routine's schedule** (`/tune-pings`'s core action) is a deliberate, narrower exception, not a gap in the rule above: the plan explicitly specs `/tune-pings` to apply non-interactively with terse, no-preamble output (`New anchor: ... / Pings: ... / Based on N days logged`), and running `/tune-pings` at all is itself the Operator's weekly, conscious act of authorization — a second confirmation prompt inside the command would contradict that spec's own stated intent without a real safety gain (the mutation only ever changes *when* the same fixed, already-approved no-op ping fires; nothing about what it does or who it's attached to). If `/tune-pings` is ever changed to do more than update `cron_expression` on the 4 known routines, that exception no longer applies and this section needs revisiting.
- **Deleting a Routine** isn't possible via the API at all — nothing in this codebase should attempt it; direct the Operator to the web UI instead.

Confirm the exact schedule (times) before creating anything — never silently retry with a rounded/guessed time if the scheduler rejects the requested spacing. On an `update` failure, stop and report immediately — never proceed to the remaining slots or retry with a guessed value.

The local prompt-timestamp log (`UserPromptSubmit` hook) and the tune-up-reminder state (`SessionStart` hook) are not safety-surface — they're local, append-only, contain no message content, and are trivially reversible (delete the file).
