# Claude Window Optimizer — Development Rules

A Claude Code plugin (not a service, no backend) — see `README.md` for what it does. This file governs work on the plugin's own source; the plugin's *installed* behavior (hooks, commands) is a separate concern from how we build it.

## Tech stack

- Plugin manifest: `.claude-plugin/plugin.json`
- Commands: Markdown slash-commands in `commands/` (plugin-root convention, not this repo's own `.claude/commands/` — see "Two `.claude` surfaces" below)
- Hooks: stdlib-only Python 3 scripts in `hooks/`, registered via `hooks/hooks.json`. **No pip dependencies** — a hook runs inside whatever Python the end user's machine has; requiring a `pip install` for a hook to fire is a real adoption blocker, not a style preference.
- Scheduling: Cloud Routines, created/updated via the `/schedule` skill (backed by the `CronCreate`/`CronList`/`CronDelete` tools) — never hand-roll cron parsing or a scheduling API call outside that skill.
- Tests: `pytest`, dev-only dependency (never required at hook-runtime).
- Lint: `ruff`.

## Two `.claude` surfaces — don't confuse them

- **`.claude/agents/`, `.claude/commands/`** — this repo's own implementation pipeline (core-implementer, test-writer, edge-case-auditor, triage, implement, spec, shape, queue-scout, cleanup), installed from `yahordauksha/agent-ecosystem`. Used to *build* this plugin. Never shipped to end users.
- **`commands/`, `hooks/`, `.claude-plugin/`** — the actual plugin product. What ships when someone installs this plugin.

## Development workflow

Same discipline as this repo's installed `implement` skill: branch/worktree isolation from `main`, GitHub Issues track all work (`gh issue`), a PR only opens once tests + edge-case-audit + `/code-review` all pass. See `.claude/commands/implement.md` for the full cycle — don't hand-roll a different one.

### Design decisions are the Operator's to make

For anything that materially shapes the plugin — the exact ping-spacing mechanism, how `/tune-pings` applies a schedule update, anything touching a live Cloud Routine — stop and ask, using a concrete options-based question. See the safety surface below; several of the plan's "Open items" are explicitly unresolved until tested against the real scheduler, not assumed.

## Agent Safety Surface — Never Touch Autonomously

This plugin's whole mechanism is a **live, persistent, account-level Cloud Routine** — not a local file, not something scoped to this repo. A wrong or duplicated Routine keeps firing on its own schedule until someone notices and manually removes it.

Agents must propose the change and wait for explicit confirmation before executing — never treat these as low-stakes/reversible defaults:

- **Creating a new Cloud Routine** (`/setup-window-optimizer`'s core action).
- **Modifying an existing Routine's schedule** (`/tune-pings`'s core action) — including the fallback path where the plan calls for printing the exact line to paste rather than applying it non-interactively.
- **Deleting a Routine.**

Confirm the exact schedule (times, repo attachment) before creating or updating anything — never silently retry with a rounded/guessed time if the scheduler rejects the requested spacing.

The local prompt-timestamp log (`UserPromptSubmit` hook) and the tune-up-reminder state (`SessionStart` hook) are not safety-surface — they're local, append-only, contain no message content, and are trivially reversible (delete the file).
