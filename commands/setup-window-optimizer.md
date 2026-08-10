---
description: One-time setup — computes a ping schedule from your logged activity (or asks once if there's none yet) and creates the 4 Cloud Routines that keep your usage window aligned to when you actually work.
allowed-tools: Bash(python3 *:*), Bash(cat *:*), ToolSearch, RemoteTrigger, Skill, AskUserQuestion
---

Run this once. It creates 4 Cloud Routines (see `adr/0001-cloud-routine-scheduling-constraints.md` for why 4, not a variable number) — each a daily-recurring, no-op "keep-alive" ping spaced 5h10m apart from an anchor time, so no gap in your active hours is ever short enough to let a usage-window reset land mid-workday, and none is so long it wastes a ping inside a still-open window.

## STEP 1 — Check whether this has already run

```bash
cat ~/.claude/window-optimizer/routines.json 2>/dev/null
```

If it exists and has 4 entries under `routines`, stop and tell the user setup already ran (show the current schedule) — point them at `/tune-pings` instead of re-running this. Don't create a second set of routines.

## STEP 2 — Compute the anchor

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compute_schedule.py" --from-log
```

(`CLAUDE_PLUGIN_ROOT` is the plugin's own install directory — always use it here, never a bare relative `scripts/...` path, since this command can run with the working directory set to whatever project the user has open, not this plugin's own directory.)

- If this returns a real schedule (not `{"error": "no_log_data"}`): the logging hook already has enough activity to compute a real anchor. Skip to STEP 3.
- If it returns `{"error": "no_log_data"}`: this is a fresh install with no logged activity yet. Ask the user, once, for a rough start-of-day in their local time (a plain question or `AskUserQuestion` — e.g. "What time do you typically start working? (HH:MM, your local time)"). Then run:
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compute_schedule.py" --anchor <HH:MM>
  ```

Either way, you now have a JSON object with `anchor_local_hhmm`, `utc_offset_hours`, and `slots` (4 entries, each with `local_hhmm`, `utc_hhmm`, `cron_expression`).

## STEP 3 — Resolve the Cloud environment to run in

Load `RemoteTrigger` via `ToolSearch select:RemoteTrigger`, then call `{"action": "list"}`.

- If the response has at least one existing routine: reuse its `job_config.ccr.environment_id` — this account already has a known-good default environment, no need to ask.
- If the account has zero existing routines: invoke the `schedule` skill once (`Skill` tool) with a request that asks it only to report the available environment(s) and confirms the default — do not let it create anything at this stage. Read the environment id it surfaces. (Do not hardcode any environment id — it is not guaranteed to be the same across every account.)

## STEP 4 — Show the full proposal, get one batch confirmation

Present all of this together, once, before creating anything (per this project's safety surface — Cloud Routine creation is never a silent apply):

- The 4 ping times, in the user's local time (from `slots[].local_hhmm`) and the UTC cron each maps to.
- Model: `claude-haiku-4-5-20251001` (cheapest available — the ping only needs to register as a message, not do real work).
- No repo attached, no tools granted, no MCP connectors (see ADR-0001 — none of this is required, and the ping does nothing that would need them).
- The exact prompt text each ping will send (see STEP 5).
- If STEP 3's `list` call surfaced any pre-existing routine that looks like an old ad-hoc ping setup (e.g. named "Start session at ..."), mention it and suggest the user disable/delete it manually at https://claude.ai/code/routines once the new schedule is confirmed working — routines can't be deleted via the API, so this is always a manual step, never something this command does for them.

Wait for explicit confirmation before proceeding to STEP 5.

## STEP 5 — Create the 4 routines

For each of the 4 slots, call `RemoteTrigger` with:

```json
{
  "action": "create",
  "body": {
    "name": "Window Optimizer Ping <slot+1>/4 (<local_hhmm> local)",
    "cron_expression": "<slots[i].cron_expression>",
    "enabled": true,
    "job_config": {
      "ccr": {
        "environment_id": "<resolved in STEP 3>",
        "session_context": {
          "model": "claude-haiku-4-5-20251001",
          "allowed_tools": []
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
                "content": "This is an automated keep-alive ping from the Claude Window Optimizer plugin (https://github.com/yahordauksha/claude-window-optimizer). It exists only to keep your Claude Code usage window aligned to your work hours — no action is needed. Reply with a short acknowledgement."
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
- `routines` = `[{"slot": i, "trigger_id": "...", "local_hhmm": "...", "utc_hhmm": "...", "cron_expression": "..."}, ...]` for all 4 slots, combining STEP 2's per-slot schedule fields with STEP 5's returned `trigger_id`s by slot index

This is what `/tune-pings` and the `SessionStart` reminder hook both read afterward — don't skip it even though nothing on screen depends on it immediately.

## STEP 7 — Report back

Concise, no preamble:

```
Created 4 ping routines (5h10m apart from a <HH:MM> anchor):
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
- Never hardcode an `environment_id` — always resolve it per STEP 3.
- Never attach a repo, grant tools, or attach an MCP connector to a ping routine — none is needed (see ADR-0001).
