---
description: Weekly tune-up — recomputes the ping anchor from the last ~4 weeks of logged activity and updates the 4 existing Cloud Routines in place.
allowed-tools: Bash(python3 *:*), ToolSearch, RemoteTrigger
---

Run this weekly (or whenever the `SessionStart` reminder hook nudges you). Updates the 4 routines `/setup-window-optimizer` created — never creates or deletes any (see `adr/0001-cloud-routine-scheduling-constraints.md`: routines can't be deleted via the API, so the slot count stays fixed forever and this command only ever updates in place).

## STEP 1 — Compute the diff

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tune_schedule.py"
```

(`CLAUDE_PLUGIN_ROOT` is the plugin's own install directory — always use it here, never a bare relative `scripts/...` path, since this command can run with the working directory set to whatever project the user has open.)

- `{"error": "not_set_up"}` — `/setup-window-optimizer` hasn't run yet. Say so plainly and stop; point at that command instead.
- `{"error": "no_log_data"}` — no logged activity in the trailing 28 days (e.g. the hook was disabled, or this ran right after a fresh install with no usage yet). Say so plainly and stop; nothing to tune from.
- Otherwise: a JSON object with `old_anchor_local_hhmm`, `new_anchor_local_hhmm`, `logged_days`, `trailing_days`, and `slots` (4 entries, each with `slot`, `trigger_id`, `old_cron_expression`, `new_cron_expression`, `local_hhmm`, `utc_hhmm`, `kind`, `repo`). `kind`/`repo` describe what each ping *does* (e.g. `github-issues` checking `owner/name`) — this command never changes them, only passes them through unchanged into STEP 3's write.

If `new_anchor_local_hhmm == old_anchor_local_hhmm` (schedule hasn't drifted enough to change the anchor), skip straight to STEP 4 and report that nothing changed — still write the tune-up timestamp (STEP 3), since a reminder shouldn't keep firing just because the anchor happened to land on the same value this week.

## STEP 2 — Apply the update (one batch, no separate confirmation)

The Operator already authorized `/tune-pings` to update the existing 4 routines' schedules non-interactively as part of this project's setup (see CLAUDE.md's safety surface — this is the one mutation type this command exists to perform automatically, unlike routine *creation* which always needs a fresh confirmation). Load `RemoteTrigger` via `ToolSearch select:RemoteTrigger` if not already loaded, then for each of the 4 slots call:

```json
{"action": "update", "trigger_id": "<slots[i].trigger_id>", "body": {"cron_expression": "<slots[i].new_cron_expression>"}}
```

If any single update call fails (e.g. the API rejects the cron expression, or the trigger_id no longer exists because the user deleted it manually via the web UI): stop immediately, do not proceed to the remaining slots, and report exactly which slot failed and why — do not silently skip a failed slot and continue as if the schedule is now fully consistent, and do not retry a rejected spacing with a rounded/guessed value.

This command **only ever calls `update` with `cron_expression`** — never touches `job_config`, the prompt, or `allowed_tools`. A ping's content (`kind`/`repo`) is set once at `/setup-window-optimizer` time and never changes here, on purpose — re-deriving what each slot "should" check every week is a different, unbuilt feature, not something to improvise into this command's own update call.

## STEP 3 — Persist local state

Update `routines.json` (via `window_optimizer.state.write_routines_state`, same shape as `/setup-window-optimizer` STEP 6 — `anchor_local_hhmm` set to the new anchor, `routines` with each slot's new `cron_expression`/`utc_hhmm` plus its **unchanged** `kind`/`repo` from STEP 1's diff, `installed_at` carried over unchanged) and write the tune-up timestamp via `window_optimizer.state.write_tune_state(datetime.now().astimezone().isoformat())` — this is what the `SessionStart` reminder hook reads to decide whether to nag.

## STEP 4 — Report back

Exactly this shape, nothing more — no preamble, no methodology explanation:

```
New anchor: <new_anchor_local_hhmm> (was <old_anchor_local_hhmm>)
Pings: <slot0 local_hhmm>, <slot1 local_hhmm>, <slot2 local_hhmm>, <slot3 local_hhmm>
Based on <logged_days> days logged, last <trailing_days> days
```

If the anchor didn't change: `New anchor: <hhmm> (unchanged)` in place of the first line, everything else the same.

## HARD RULES

- Never create or delete a routine from this command — only `update`, on the 4 `trigger_id`s already on file.
- Never proceed past a failed update call to the remaining slots.
- Never pad the output beyond STEP 4's exact format.
- Always write the tune-up timestamp on completion, even when the anchor didn't change — the reminder hook's whole point is to track "how long since this was last checked," not "how long since it last changed."
