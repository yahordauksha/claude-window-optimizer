# Claude Window Optimizer — Development Rules

A Claude Code plugin (not a service, no backend) — see `README.md` for what it does. This file governs work on the plugin's own source; the plugin's *installed* behavior (hooks, commands) is a separate concern from how we build it.

## Tech stack

- Plugin manifest: `.claude-plugin/plugin.json`
- Commands: Markdown slash-commands in `commands/` (plugin-root convention, not this repo's own `.claude/commands/` — see "Two `.claude` surfaces" below)
- Hooks: stdlib-only Python 3 scripts in `hooks/`, registered via `hooks/hooks.json`. **No pip dependencies** — a hook runs inside whatever Python the end user's machine has; requiring a `pip install` for a hook to fire is a real adoption blocker, not a style preference.
- Scheduling: Cloud Routines, created/updated via the `RemoteTrigger` tool (`action: create`/`update`/`list`) — **not** `CronCreate`/`CronList`/`CronDelete`, which is a different, session-scoped, in-memory reminder mechanism (gone when the session ends, 7-day auto-expiry) and cannot back a persistent, account-level Routine. See `adr/0001-cloud-routine-scheduling-constraints.md`. `RemoteTrigger` has no delete action — routines can only be deleted via https://claude.ai/code/routines, which is why the slot count is fixed at 4 forever rather than ever shrinking.
- Tests: `pytest`, dev-only dependency (never required at hook-runtime).
- Lint: `ruff`.

## Releasing: bump `version` or nobody gets the change

`.claude-plugin/plugin.json`'s `version` is the **only** update signal. The plugin
cache is keyed by that string, not by commit, so pushing a fix without bumping it
means installed copies never receive it — not late, never. Demonstrated: with the
repo one commit ahead and the version unchanged, `plugin marketplace update`
followed by `plugin update` reported *"already at the latest version (1.0.0)"* and
the cached build did not contain the new commit.

So: **bump `version` in the same commit as any change that ships**, however small.

Two related facts worth knowing:
- Updating needs *both* `claude plugin marketplace update <name>` (re-pull the
  catalogue clone) and `claude plugin update <plugin>@<marketplace>` (install it).
  The first alone changes nothing installed; the second alone re-reads a stale clone.
- Auto-update is **off** by default for third-party marketplaces like this one —
  only Anthropic's official marketplace defaults to on. Assume users will not
  update unless told to.

## Two `.claude` surfaces — don't confuse them

- **`.claude/agents/`, `.claude/commands/`** — this repo's own implementation pipeline (core-implementer, test-writer, edge-case-auditor, triage, implement, spec, shape, queue-scout, cleanup), installed from `yahordauksha/agent-ecosystem`. Used to *build* this plugin. Never shipped to end users.
- **`commands/`, `hooks/`, `.claude-plugin/`** — the actual plugin product. What ships when someone installs this plugin.

## Development workflow

Same discipline as this repo's installed `implement` skill: branch/worktree isolation from `main`, GitHub Issues track all work (`gh issue`), a PR only opens once tests + edge-case-audit + `/code-review` all pass. See `.claude/commands/implement.md` for the full cycle — don't hand-roll a different one.

### Design decisions are the Operator's to make

The ping-spacing mechanism, how `/tune-pings` applies a schedule update, what a reset is allowed to say, and how the anchor is chosen are resolved — see `adr/0001-cloud-routine-scheduling-constraints.md` through `adr/0011-empty-allowed-tools-means-everything.md`, all grounded in real, verified behavior. For anything that would change those decisions, or any other change that materially reshapes the plugin, stop and ask using a concrete options-based question rather than reopening any ADR's reasoning ad hoc.

Two of those decisions look contradictory and aren't. Reset **content** is never asked about — it's drawn at random from a fixed pool (ADR-0010). The **anchor** is always asked about, via working hours, and never derived from the log at setup (ADR-0004, ADR-0009). The difference is whether a signal exists at setup time: the pool is fixed in code and needs no input, while a usage pattern doesn't exist yet on day one because the only thing in the log is the user installing this plugin. Don't make either "consistent" with the other.

### A UX simplification that changes what the system trusts is a security decision

ADR-0003 removed a setup question on the Operator's instruction ("just make shit up"). That was right about the UX. It also, unremarked at the time, changed *whose text* this plugin feeds to an unattended agent — from "a repo you named" to "whatever `git remote origin` says in the current directory," i.e. any public repo and therefore any stranger's issue titles. Two review rounds and two ADRs went into narrowing that before ADR-0010 removed the fetch entirely. The repo-detection code is gone; the lesson isn't.

When a change makes something automatic that used to be asked, state explicitly what the automatic version is now trusting, and whether that set is larger than before. "Fewer questions" and "wider trust" are easy to ship as one change and hard to separate afterward.

### Two vocabularies, on purpose

Code, ADRs, and variable names describe the **mechanism** (pings, routines, anchors, cron). Everything the user reads describes the **outcome** (when their usage window resets). See `adr/0005-speak-in-window-resets-not-pings.md`. When editing a command file's user-facing copy, don't let the surrounding implementation vocabulary leak into it — that's exactly how this drifted the first time.

## Agent Safety Surface — Never Touch Autonomously

This plugin's whole mechanism is a **live, persistent, account-level Cloud Routine** — not a local file, not something scoped to this repo. A wrong or duplicated Routine keeps firing on its own schedule until someone notices and manually removes it.

- **Creating a new Cloud Routine** (`/setup-window-optimizer`'s core action) always requires a fresh, explicit batch confirmation before executing — never a low-stakes/reversible default, even though the whole "one command, done" pitch makes a silent apply tempting. This is the higher-stakes action: it spins up new persistent infrastructure, and routines can't be deleted via the API if it goes wrong (only disabled/removed manually via https://claude.ai/code/routines) — so a wrong or duplicated Routine keeps firing until a human notices and cleans it up by hand.
- **Updating an existing Routine's schedule** (`/tune-pings`'s core action) is a deliberate, narrower exception, not a gap in the rule above: the plan explicitly specs `/tune-pings` to apply non-interactively with terse, no-preamble output (`New anchor: ... / Pings: ... / Based on N days logged`), and running `/tune-pings` at all is itself the Operator's weekly, conscious act of authorization — a second confirmation prompt inside the command would contradict that spec's own stated intent without a real safety gain. This exception is load-bearing on one hard rule staying true: `/tune-pings` only ever calls `update` with `cron_expression` — it never touches `job_config`, the prompt, or `allowed_tools` (see `adr/0002-useful-ping-content.md`; a ping's content is fixed once at setup, not re-derived weekly). If `/tune-pings` is ever changed to touch anything beyond `cron_expression` on the 4 known routines, this exception no longer applies and this section needs revisiting.
- **A reset routine gets the narrowest grant the API will honour — and that is not `[]`.** An empty `allowed_tools` is read as *unset* and replaced with the account's full default set (`Bash`, `Write`, `Edit`, `SendUserFile`, `REPL`...). Confirmed live; see `adr/0011-empty-allowed-tools-means-everything.md`. The grant comes from `window_optimizer.ping_content.allowed_tools()` (`["TodoWrite"]`), never composed ad hoc in a command file, and must never be loosened to `[]`. Every prompt in the pool is self-contained — nothing fetches, reads, or reaches outside itself (`adr/0010-fixed-safe-prompt-pool.md`). Never grant `Bash`, `WebFetch`, a repo checkout, or an MCP connector to a reset routine, and never add a prompt that would need one, without a new ADR superseding that one.
- **The grant you requested is not the grant you got.** A real create request specifying no connectors came back with five attached, applied as account-level server defaults — and the command reported success because it trusted its own request (see `adr/0006-verify-created-routines.md`). Every created routine must be read back with `get` and diffed against what was sent before setup claims success. Unexpected connectors are cleared with `clear_mcp_connections` (verified to work) and re-checked; an unexpected `allowed_tools` or `cron_expression` stops the run outright. Never treat an API response to a write as evidence of state.
- **Deleting a Routine** isn't possible via the API at all — nothing in this codebase should attempt it; direct the Operator to the web UI instead.

Confirm the exact schedule (times) before creating anything — never silently retry with a rounded/guessed time if the scheduler rejects the requested spacing. On an `update` failure, stop and report immediately — never proceed to the remaining slots or retry with a guessed value.

The local prompt-timestamp log (`UserPromptSubmit` hook) and the tune-up-reminder state (`SessionStart` hook) are not safety-surface — they're local, append-only, contain no message content, and are trivially reversible (delete the file).
