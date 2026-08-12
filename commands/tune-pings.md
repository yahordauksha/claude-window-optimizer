---
description: Weekly tune-up — recomputes when your usage window should reset, based on the last ~4 weeks of your actual activity, and shifts your 4 daily resets to match.
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
- `{"error": "insufficient_log_data", ...}` — not enough to re-anchor on without swinging the schedule around noise. Two floors, and the response says which one failed: `logged_days`/`needed_days` (no habit yet) and `logged_prompts`/`needed_prompts` (too little volume for the answer to be a measurement rather than a tie-break). Say so plainly (name the actual day count), leave the current schedule alone, and stop. Still write the tune-up timestamp (STEP 3) so the reminder doesn't nag daily about a check that correctly declined to act.
- Otherwise: a JSON object with `old_anchor_local_hhmm`, `new_anchor_local_hhmm`, `cron_changed`, `logged_days`, `trailing_days`, and `slots` (4 entries, each with `slot`, `trigger_id`, `old_cron_expression`, `new_cron_expression`, `local_hhmm`, `utc_hhmm`, `kind`, `repo`). `kind`/`repo` describe what each ping *does* (e.g. `github-issues` checking `owner/name`) — this command never changes them, only passes them through unchanged into STEP 3's write.

**Decide whether to apply from `cron_changed`, never from the anchor.** If `cron_changed` is `false`, skip straight to STEP 4 and report nothing changed — still write the tune-up timestamp (STEP 3), so the reminder doesn't keep firing just because the schedule happened to be right already. If `cron_changed` is `true`, apply STEP 2 **even when the anchor is identical**.

Those two conditions come apart, and the case where they do is the one that matters: across a DST transition your habit is unchanged in local time, so the anchor stays put (08:00 → 08:00) while the correct UTC cron shifts by an hour. Keying off the anchor meant the corrected cron was computed and discarded, leaving the schedule an hour wrong until something unrelated moved the anchor — in precisely the situation `schedule.py`'s DST note claimed this command would self-correct.

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

Exactly this shape, nothing more — no preamble, no methodology explanation. Report reset times, not ping times (same rule as `/setup-window-optimizer`: the ping is the mechanism, the reset is what the user gets):

```
First reset: <new_anchor_local_hhmm> (was <old_anchor_local_hhmm>)
All resets: <slot0 local_hhmm>, <slot1 local_hhmm>, <slot2 local_hhmm>, <slot3 local_hhmm>
Based on <logged_days> days logged, last <trailing_days> days
```

If the anchor didn't change: `First reset: <hhmm> (unchanged)` in place of the first line, everything else the same.

## HARD RULES

- Never create or delete a routine from this command — only `update`, on the 4 `trigger_id`s already on file.
- Never proceed past a failed update call to the remaining slots.
- Never pad the output beyond STEP 4's exact format.
- Never report ping/routine times as the headline — report when the window resets. Same rule as `/setup-window-optimizer`.
- Always write the tune-up timestamp on completion, even when the anchor didn't change — the reminder hook's whole point is to track "how long since this was last checked," not "how long since it last changed."
