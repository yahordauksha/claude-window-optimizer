---
description: One-time setup — computes a ping schedule from your logged activity (or asks once if there's none yet), optionally makes each ping do something genuinely useful for that time of day, and creates the 4 Cloud Routines. Explains what's happening as it goes.
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

## STEP 2 — Compute the anchor

Before running anything, say plainly what an anchor is (see the explanation above) — do this whether or not a question ends up being asked, since even the "skip straight to a real schedule" path below still means the user should know what number is about to be shown to them.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compute_schedule.py" --from-log
```

(`CLAUDE_PLUGIN_ROOT` is the plugin's own install directory — always use it here, never a bare relative `scripts/...` path, since this command can run with the working directory set to whatever project the user has open, not this plugin's own directory.)

- If this returns a real schedule (not `{"error": "no_log_data"}`): the logging hook already has enough activity to compute a real anchor. Skip to STEP 2b.
- If it returns `{"error": "no_log_data"}`: this is a fresh install with no logged activity yet. Ask the user, once, for a rough start-of-day in their local time (a plain question or `AskUserQuestion` — e.g. "What time do you typically start working? (HH:MM, your local time)"). Then run:
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compute_schedule.py" --anchor <HH:MM>
  ```

Either way, you now have a JSON object with `anchor_local_hhmm`, `utc_offset_hours`, and `slots` (4 entries, each with `local_hhmm`, `utc_hhmm`, `cron_expression`).

## STEP 2b — Ask (once, optional) whether pings should do something useful

Ask directly, in one question: *"Each ping can just be a no-op keep-alive, or it can check something small and useful for that time of day — e.g. if you're usually coding around midday, that ping could show your most recently updated open GitHub issue instead. Want that? If so, roughly describe your day (e.g. 'mornings: email, midday: coding, evenings: wrap-up') and, if coding is part of it, which public GitHub repo to check. Otherwise just say no and every ping stays a simple keep-alive."*

This is genuinely optional — a "no" (or silence on which repo) is a complete, valid answer. Don't press for it.

**v1 only ships one real check kind: GitHub open issues, via the public REST API, for a repo the user names.** If the user's description mentions something this doesn't cover (email, calendar, anything needing an authenticated connector) — say plainly that's not built yet (see `adr/0002-useful-ping-content.md`), not silently ignored. Don't fabricate a check you can't actually run.

## STEP 2c — Assign a content kind to each slot

This is a judgment call, not a script — read the user's description (if given) and each slot's `local_hhmm` from STEP 2, and assign each of the 4 slots one of:

- **`github-issues`** — if the slot's local time plausibly falls in a period the user described as coding/dev work, AND a public repo was named. Needs `owner/name` format; if the user gave something else (a URL, just a name), normalize it.
- **`simple`** — everything else: no rhythm description given, the slot doesn't match any described period, the matching period wasn't "coding," or no repo was named.

Never guess a repo the user didn't name. Never assign `github-issues` to a private repo — the WebFetch call uses the *public*, unauthenticated GitHub API and will just fail for a private one; if the user names a private repo, say so plainly and use `simple` for that slot instead of silently failing later.

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
- **What each slot actually does** — `simple` (keep-alive only) or `github-issues` (which repo) — per slot, from STEP 2c. Don't just say "4 pings"; say what each one does.
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
will show up in your Cloud Routines list at claude.ai/code/routines:
  <HH:MM local> / <HH:MM UTC> — keep-alive
  <HH:MM local> / <HH:MM UTC> — <owner/name> open issues
  <HH:MM local> / <HH:MM UTC> — keep-alive
  <HH:MM local> / <HH:MM UTC> — keep-alive

Logging is already active (bundled hook). Run /tune-pings weekly to
re-anchor as your habits drift — you'll get a reminder after 7 days.
```

If an old ad-hoc routine was flagged in STEP 4, repeat the one-line suggestion to clean it up manually.

## HARD RULES

- Never create routines a second time if `routines.json` already shows 4 installed — direct to `/tune-pings` instead.
- Never create or modify a Cloud Routine without STEP 4's explicit batch confirmation first.
- Never hardcode an `environment_id` — always resolve it per STEP 3.
- Never assign `github-issues` to a repo the user didn't explicitly name, and never to a private repo — fall back to `simple` and say why.
- Never grant a tool or attach a connector beyond what STEP 2c's `allowed_tools_for_kind` actually returns for that slot — the tool grant is derived from tested code, not composed ad hoc.
- Never invent a check kind beyond `simple`/`github-issues` — if the user asks for something this doesn't support (email, calendar, private repos), say so plainly instead of approximating it.
