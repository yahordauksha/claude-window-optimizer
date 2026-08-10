---
description: One-time setup — asks once when you usually start working, auto-detects a repo so pings check real open issues instead of being a no-op (no extra question asked), and creates the 4 Cloud Routines. Explains what's happening as it goes.
allowed-tools: Bash(python3 *:*), Bash(cat *:*), ToolSearch, RemoteTrigger, Skill, AskUserQuestion
---

Run this once. It creates 4 Cloud Routines (see `adr/0001-cloud-routine-scheduling-constraints.md` for why 4, not a variable number) spaced 5h10m apart from an anchor time, so no gap in your active hours is ever short enough to let a usage-window reset land mid-workday, and none is so long it wastes a ping inside a still-open window.

**Explain yourself as you go** — this command's whole job is to be understandable, not just functional. Two things a first-time user won't know without being told, so say them plainly the first time each comes up (STEP 2 and STEP 4 below), not just once in passing:

- **What "anchor" means**: the anchor is the local time each day this system treats as roughly "when you start working." The 4 pings are spaced out from it — not from midnight, not from a fixed schedule — so they land near your actual active hours instead of firing all night for no reason.
- **What these routines actually are**: the 4 things this command is about to create will show up in your Cloud Routines list (https://claude.ai/code/routines) as regular-looking scheduled agents. They're pings — their whole job is to register a message that keeps your usage window fresh. Say this explicitly so it's never a surprise when the user sees them there later.

## STEP 1 — Check whether this has already run

```bash
cat ~/.claude/window-optimizer/routines.json 2>/dev/null
```

If it exists and has 4 entries under `routines`, stop and tell the user setup already ran (show the current schedule) — point them at `/tune-pings` instead of re-running this. Don't create a second set of routines.

## STEP 2 — Ask for the anchor (always — never compute it here)

Explain what an anchor is (see the explanation above), then ask, once: *"What time do you usually start working? (HH:MM, your local time)"* — a plain question or `AskUserQuestion`.

**Always ask. Never read the log for this.** On a first run the log is either empty or dominated by the last few minutes of installing and poking at this plugin, so anything computed from it is a faithful average of noise that reads as "roughly now" — technically correct, practically useless, and actively confusing when presented as a real pattern. Log-based anchoring belongs to `/tune-pings`, which works off a trailing 4-week window where the data actually means something. See `adr/0004-setup-always-asks-for-the-anchor.md`. `compute_schedule.py` has no `--from-log` mode anymore — don't try to reintroduce one here.

With the answer:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compute_schedule.py" --anchor <HH:MM>
```

(`CLAUDE_PLUGIN_ROOT` is the plugin's own install directory — always use it here, never a bare relative `scripts/...` path, since this command can run with the working directory set to whatever project the user has open, not this plugin's own directory.)

If it returns `{"error": "invalid_anchor"}`, the time didn't parse — ask again rather than guessing a correction.

You now have a JSON object with `anchor_local_hhmm`, `utc_offset_hours`, and `slots` (4 entries, each with `local_hhmm`, `utc_hhmm`, `cron_expression`).

Mention in passing (one clause, not a paragraph) that this is a starting point `/tune-pings` will correct from real data after a few weeks — so the answer doesn't need to be precise.

## STEP 2b — Auto-detect a repo for useful pings (no question asked)

Don't ask what to check — infer it. Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_repo.py"
```

This tries the current project's own git remote first, falls back to the account's most recently pushed-to public repo via `gh`, and confirms whatever it finds is actually public before returning it (a private repo would just silently fail the ping's unauthenticated GitHub API call otherwise — see `adr/0002-useful-ping-content.md`/`adr/0003-auto-detect-instead-of-asking.md`). Returns `{"repo": "owner/name"}` or `{"repo": null}`.

- If a repo was found: every slot's ping checks that repo's open issues (STEP 2c) — anyone using this plugin is a Claude Code user, i.e. almost certainly working on *something*, so defaulting useful-over-no-op is the reasonable call, not a wild guess.
- If nothing was found (no git remote, `gh` unavailable/unauthenticated, no public repos): every slot falls back to a plain keep-alive. Mention this plainly in STEP 4's proposal (one line, not an apology) — the user can always ask for a specific repo afterward if they want one.

**v1 only ships one real check kind: GitHub open issues, via the public REST API.** If none was auto-detected, don't ask what else the user might want checked (email, calendar) — those aren't built (see the ADRs above); say so only if the user brings it up themselves, don't volunteer a gap nobody asked about.

## STEP 2c — Assign a content kind to each slot

Deterministic, not a judgment call, given STEP 2b's result:

- **Repo found** → every slot gets `github-issues` for that repo.
- **No repo found** → every slot gets `simple`.

For each slot, run:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_ping_prompt.py" --kind simple
# or, for a github-issues slot:
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_ping_prompt.py" --kind github-issues --repo owner/name
```
Each call returns `{"prompt": "...", "allowed_tools": [...]}` for that slot — hold onto both per slot for STEP 5.

## STEP 3 — Resolve the Cloud environment to run in

Load `RemoteTrigger` via `ToolSearch select:RemoteTrigger`, then call `{"action": "list"}`.

- If the response has at least one existing routine: reuse its `job_config.ccr.environment_id` — this account already has a known-good default environment, no need to ask.
- If the account has zero existing routines: invoke the `schedule` skill once (`Skill` tool) with a request that asks it only to report the available environment(s) and confirms the default — do not let it create anything at this stage. Read the environment id it surfaces. (Do not hardcode any environment id — it is not guaranteed to be the same across every account.)

## STEP 4 — Show the full proposal, get one batch confirmation

Present all of this together, once, before creating anything (per this project's safety surface — Cloud Routine creation is never a silent apply). Lead with the two explanations from the top of this file if you haven't already said them this run — don't assume STEP 2 already covered it thoroughly enough.

- The 4 ping times, in the user's local time (from `slots[].local_hhmm`) and the UTC cron each maps to.
- **What every ping actually does** — either "all 4 check `owner/name`'s open issues" (repo found, STEP 2b) or "all 4 are plain keep-alives (no repo auto-detected)" — one line, not a per-slot repeat, since v1 assigns the same kind to all 4 slots.
- Model: `claude-haiku-4-5-20251001` (cheapest available — even a `github-issues` check is a single small WebFetch + a short summary, not real work).
- Tool grant per slot, from STEP 2c's `allowed_tools` — empty for `simple`, `["WebFetch"]` for `github-issues`. No repo checkout, no MCP connectors, no broader tool access than that (see `adr/0002-useful-ping-content.md`).
- If STEP 3's `list` call surfaced any pre-existing routine that looks like an old ad-hoc ping setup (e.g. named "Start session at ..."), mention it and suggest the user disable/delete it manually at https://claude.ai/code/routines once the new schedule is confirmed working — routines can't be deleted via the API, so this is always a manual step, never something this command does for them.

Wait for explicit confirmation before proceeding to STEP 5.

## STEP 5 — Create the 4 routines

For each of the 4 slots, call `RemoteTrigger` with:

```json
{
  "action": "create",
  "body": {
    "name": "Window Optimizer Ping <slot+1>/4 (<local_hhmm> local) — <kind, e.g. 'keep-alive' or 'owner/name issues'>",
    "cron_expression": "<slots[i].cron_expression>",
    "enabled": true,
    "job_config": {
      "ccr": {
        "environment_id": "<resolved in STEP 3>",
        "session_context": {
          "model": "claude-haiku-4-5-20251001",
          "allowed_tools": "<this slot's allowed_tools from STEP 2c>"
        },
        "events": [
          {
            "data": {
              "uuid": "<fresh lowercase v4 uuid, generate one per call>",
              "session_id": "",
              "type": "user",
              "parent_tool_use_id": null,
              "message": {
                "role": "user",
                "content": "<this slot's prompt from STEP 2c>"
              }
            }
          }
        ]
      }
    }
  }
}
```

Record each call's returned `trigger_id` against its slot index.

## STEP 6 — Persist local state

Run a short inline Python snippet via `Bash` (`python3 -c "..."`, with `"${CLAUDE_PLUGIN_ROOT}/lib"` on `sys.path` the same way the scripts under `scripts/` do it) that calls `window_optimizer.state.write_routines_state(installed_at_iso, anchor_local_hhmm, routines)`, where:

- `installed_at_iso` = the current local timestamp, `datetime.now().astimezone().isoformat()`
- `anchor_local_hhmm` = STEP 2's `anchor_local_hhmm`
- `routines` = `[{"slot": i, "trigger_id": "...", "local_hhmm": "...", "utc_hhmm": "...", "cron_expression": "...", "kind": "simple"|"github-issues", "repo": "owner/name" or null}, ...]` for all 4 slots — the `kind`/`repo` fields are new (STEP 2c), combined with STEP 2's schedule fields and STEP 5's `trigger_id`s by slot index

This is what `/tune-pings` and the `SessionStart` reminder hook both read afterward — don't skip it even though nothing on screen depends on it immediately. `/tune-pings` only ever touches `cron_expression` on update, never `kind`/`repo`/the prompt — those stay fixed once set here.

## STEP 7 — Report back

Concise, no preamble, but say what each ping actually does — this is the last chance to make sure "these are pings, here's what each one does" actually landed:

```
Created 4 ping routines (5h10m apart from a <HH:MM> anchor) — these
will show up in your Cloud Routines list at claude.ai/code/routines.
Each checks <owner/name>'s open issues (or: "is a plain keep-alive —
no repo auto-detected"):
  <HH:MM local> / <HH:MM UTC>
  <HH:MM local> / <HH:MM UTC>
  <HH:MM local> / <HH:MM UTC>
  <HH:MM local> / <HH:MM UTC>

Logging is already active (bundled hook). Run /tune-pings weekly to
re-anchor as your habits drift — you'll get a reminder after 7 days.
```

If an old ad-hoc routine was flagged in STEP 4, repeat the one-line suggestion to clean it up manually.

## HARD RULES

- Never create routines a second time if `routines.json` already shows 4 installed — direct to `/tune-pings` instead.
- Never create or modify a Cloud Routine without STEP 4's explicit batch confirmation first.
- Never derive the anchor from the log here, and never skip STEP 2's question because a log happens to exist — always ask (see ADR-0004). Setup's job is to get a deliberate starting point; `/tune-pings` is what turns it into a data-driven one.
- Never hardcode an `environment_id` — always resolve it per STEP 3.
- Never ask which repo to use, or whether the user wants useful pings — auto-detect (STEP 2b) and default to useful when a repo is found. Never assign `github-issues` to a repo `detect_repo.py` didn't confirm public.
- Never grant a tool or attach a connector beyond what STEP 2c's `allowed_tools_for_kind` actually returns for that slot — the tool grant is derived from tested code, not composed ad hoc.
- Never invent a check kind beyond `simple`/`github-issues` — if the user asks for something this doesn't support (email, calendar, private repos), say so plainly instead of approximating it.
