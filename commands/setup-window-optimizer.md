---
description: One-time setup — asks once what hours you work, then schedules 4 daily usage-window resets around them.
allowed-tools: Bash(python3 *:*), Bash(cat *:*), ToolSearch, RemoteTrigger, Skill, AskUserQuestion
---

Creates 4 Cloud Routines spaced 5h10m apart from an anchor time, so the user's 5-hour usage window is fresh when they sit down and never expires mid-workday. See `adr/0001-cloud-routine-scheduling-constraints.md` for why 4 and why that spacing.

> [!important] Output budget — the user is not reading a wall of text
> This whole command should print **at most ~12 lines total** across all steps. One question, one compact proposal, one short result. The detail below is instruction *for you*, not a script to read aloud: don't narrate steps, don't explain the mechanism unprompted, don't restate what you're about to do before doing it. Each step below marks exactly what may be printed. If the user asks how it works, then explain — otherwise don't.

> [!important] Say "window resets," never "pings"
> The ping is the mechanism; the reset is what the user gets. See `adr/0005-speak-in-window-resets-not-pings.md`.

## STEP 1 — Check whether this already ran

```bash
cat ~/.claude/window-optimizer/routines.json 2>/dev/null
```

If it exists with 4 entries under `routines`: print the current reset times in one line, say setup already ran, point at `/tune-pings`, stop. Don't create a second set.

## STEP 2 — Ask for working hours (always — never compute them here)

**Ask about the user's day, not about reset times.** Asking "what time do you want your window to reset" sounds like the right question and produces a measurably bad schedule: used directly as the anchor, it puts one reset at the head of a work block and leaves the whole block riding on a single budget. For a concentrated evening worker that delivered *zero* benefit over not installing the plugin at all. Working hours let the same objective `/tune-pings` uses pick the anchor — which lands a reset partway through the block instead. See `adr/0009-ask-for-working-hours.md`.

**First compute the real schedule for each option you're about to offer.** Pick three plausible working days that produce *distinct* schedules (09:00–17:00 / 10:00–19:00 / 20:00–01:00 is a good default spread — note 08:00–18:00 optimises to the same phase as 09:00–17:00, so don't offer both) and run the script once per candidate:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compute_schedule.py" --hours 09:00-17:00
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compute_schedule.py" --hours 10:00-19:00
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compute_schedule.py" --hours 20:00-01:00
```

(Always `${CLAUDE_PLUGIN_ROOT}`, never a bare relative `scripts/...` path — the working directory is whatever project the user has open. Overnight ranges like `20:00-01:00` are handled; don't split them yourself.)

**Then ask, with each option showing the times it actually produces.** Use `AskUserQuestion`:

> **What hours do you usually work? Rough is fine — this is only a starting point. Once you've built up a week or two of real usage, `/tune-pings` recalculates the schedule from when you actually work.**
>
> | option | description |
> |---|---|
> | `09:00–17:00` | Window resets at 07:50, 13:00, 18:10, 23:20 |
> | `10:00–19:00` | Window resets at 09:20, 14:30, 19:40, 00:50 |
> | `20:00–01:00` | Window resets at 17:20, 22:30, 03:40, 08:50 |

**Say that it's provisional in the question itself**, not afterwards. Without it the user thinks they're making a decision they have to get right, when the real answer is "guess, and it self-corrects." It also explains why they're being asked at all rather than having it measured — there's nothing to measure yet.

Fill each description from that candidate's own `slots[].local_hhmm`, joined with commas — never write the times by hand, and never reuse the illustrative ones above.

**Make sure the options actually differ.** Two nearby ranges can optimise to the same phase and produce identical reset times, which reads as broken — the user sees two different answers to "what hours do you work" giving one schedule and reasonably concludes the input is ignored. If two candidates come back identical, swap one for a range far enough away to differ (e.g. replace `08:00–18:00` with `10:00–19:00` or `06:00–14:00`) before asking. Check this against the computed output, not by eye.

**Never describe an option as "and 3 more times through the day"** or anything else that restates the question instead of answering it. The times themselves are the description.

If the user picks the free-text option, pass their hours through the same `--hours` call. `{"error": "invalid_anchor"}` → ask again, don't guess a correction. If they insist on naming an exact reset time instead of hours, `--anchor HH:MM` still exists and uses it as-is.

Don't explain the derivation unless asked. The reset times shown are the answer; how they were chosen is not what the user is deciding.

**Always ask. Never read the log for this.** On a first run the log is empty or dominated by the last few minutes of installing this plugin, so anything computed from it is noise that reads as "roughly now" (see `adr/0004-setup-always-asks-for-the-anchor.md`). `compute_schedule.py` has no `--from-log` mode — don't reintroduce one.

`{"error": "invalid_anchor"}` → ask again, don't guess a correction. Otherwise you have `anchor_local_hhmm`, `utc_offset_hours`, and `slots` (4 × `local_hhmm`, `utc_hhmm`, `cron_expression`).

## STEP 2b — Pick what the resets will say (print nothing)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_ping_prompt.py" --count 4
```

Returns `{"allowed_tools": ["TodoWrite"], "prompts": [{"key","title","prompt"}, ...]}` — four distinct prompts drawn from a fixed, inspectable pool in `lib/window_optimizer/ping_content.py`. Assign them to slots in order.

Every prompt is self-contained: none fetches anything, none reads anything, none needs a tool. That's deliberate and load-bearing — see `adr/0010-fixed-safe-prompt-pool.md`. Never substitute your own text, never add a prompt that references external data, and never grant a tool because a prompt "might need one." The grant comes from tested code — and note it is `["TodoWrite"]`, not `[]`: an empty list is read as *unset* and replaced with the account's full default tool set (`adr/0011-empty-allowed-tools-means-everything.md`).

## STEP 3 — Resolve the environment (print nothing)

`ToolSearch select:RemoteTrigger`, then `{"action": "list"}`.

- Any existing routine → reuse its `job_config.ccr.environment_id`.
- No routines at all → invoke the `schedule` skill once, asking only which environment(s) exist; let it create nothing. Never hardcode an environment id.

Note whether any pre-existing routine looks like an old ad-hoc keep-alive (e.g. "Start session at ...") — one line about it in STEP 7, not STEP 4.

## STEP 4 — Propose, confirm once

**Print exactly this shape and nothing more:**

```
Your window will reset daily at 07:50, 13:00, 18:10, 23:20 (local).
4 routines in your Cloud Routines list. Each sends one short message:
Water, Stretch, Mood, Check-in. Nothing fetched, no notifications.

Create them?
```

Name the four prompt titles from STEP 2b. Do not add a cron table, a per-slot breakdown, a model name, or a tool-grant list — if the user wants those, they'll ask.

**Wait for explicit confirmation.** Creating routines is never a silent apply.

## STEP 5 — Create the 4 routines (print nothing until STEP 5b passes)

Per slot:

```json
{
  "action": "create",
  "body": {
    "name": "<this slot's prompt title, e.g. Stretch>",
    "cron_expression": "<slots[i].cron_expression>",
    "enabled": true,
    "mcp_connections": [],
    "notifications": { "channel": { "email": false, "push": false, "slack": false } },
    "job_config": {
      "ccr": {
        "environment_id": "<from STEP 3>",
        "session_context": {
          "model": "claude-haiku-4-5-20251001",
          "allowed_tools": "<this slot's allowed_tools from STEP 2b — never [], see below>"
        },
        "events": [
          {
            "data": {
              "uuid": "<fresh lowercase v4 uuid, one per call>",
              "session_id": "",
              "type": "user",
              "parent_tool_use_id": null,
              "message": { "role": "user", "content": "<this slot's prompt text from STEP 2b>" }
            }
          }
        ]
      }
    }
  }
}
```

Two things the server does to this body that you must not paper over:

- `"mcp_connections": []` is **confirmed ignored** — account-default connectors get attached regardless. STEP 5b removes them.
- **Always send `notifications` with all channels false.** Omit it and the account default applies, which pushes a phone notification every time a reset fires — four buzzes a day for a message the user never needs to read. Verified settable on both create and update.
- **Never send `"allowed_tools": []`.** An empty list is read as *unset* and replaced with the account's full default tool set — `Bash`, `Write`, `Edit`, `SendUserFile`, `REPL` and the rest. This was found live: a routine created with `[]` came back granting all of them. A non-empty list is honoured exactly, which is why `allowed_tools()` returns `["TodoWrite"]` — the narrowest grant the API will actually respect. Use whatever STEP 2b returned, verbatim.

Record each returned `trigger_id` against its slot.

## STEP 5b — Verify what was actually created (never trust the create response)

**This step exists because of a real incident**: a create request that specified no connectors came back with five attached (Gmail, Calendar, Microsoft 365, Notion, Claude Code Remote) — the server applied account-level defaults. The command had asserted its own tool grant from the request it sent and never read back what existed, so a routine violating this plugin's own minimal-grant invariant went live and was only caught by eye. See `adr/0006-verify-created-routines.md`.

For **each** created routine, call `{"action": "get", "trigger_id": "<id>"}` and check the returned object:

1. **`mcp_connections` is non-empty** → expect this; it happens on every create. Call `{"action": "update", "trigger_id": "<id>", "body": {"clear_mcp_connections": true}}`, then `get` **again** to confirm it's now `[]`. (Verified working across 4 real routines.) If it's still non-empty after the clear, **stop everything**: report which routine, that it has connectors you couldn't remove, and that it must be deleted manually at https://claude.ai/code/routines. Do not create further routines.
2. **`session_context.allowed_tools` is not exactly what STEP 2b returned** → **stop everything**, report the exact difference, and say the routine must be deleted manually. Never "fix" a tool grant by guessing.
3. **`cron_expression` differs from what was sent** → same: stop and report.
3b. **`notifications` has any channel set to `true`** → send `{"notifications": {"channel": {"email": false, "push": false, "slack": false}}}` via `update`, then `get` again to confirm. Verified working. This one is a nuisance rather than a risk, so fix it and carry on rather than aborting the run.
4. **`enabled` is not `true`** → don't silently re-enable it; the user may have turned it off deliberately. Note it in STEP 7's report as one extra line.

Only once every routine passes may you proceed. Print nothing about this step unless something failed or check 4 tripped — a passing verification is not news.

## STEP 6 — Persist local state (print nothing)

Inline `python3 -c "..."` with `"${CLAUDE_PLUGIN_ROOT}/lib"` on `sys.path`, calling `window_optimizer.state.write_routines_state(installed_at_iso, anchor_local_hhmm, routines)`:

- `installed_at_iso` = `datetime.now().astimezone().isoformat()`
- `anchor_local_hhmm` = STEP 2's value
- `routines` = per slot: `{"slot", "trigger_id", "local_hhmm", "utc_hhmm", "cron_expression", "prompt_key", "title"}`

`/tune-pings` and the `SessionStart` reminder both read this. `/tune-pings` only ever changes `cron_expression`.

## STEP 7 — Report

**Print exactly this shape and nothing more:**

```
Done — your window now resets daily at 08:00, 13:10, 18:20, 23:30.
Run /tune-pings in a week or two to re-anchor from real usage (you'll be reminded).
```

Add **one** extra line only if STEP 3 found an old ad-hoc routine: `You can delete your old "<name>" routine at claude.ai/code/routines.`

## HARD RULES

- Never print more than the shapes STEP 2/4/7 specify. If a step says "print nothing," print nothing.
- Never create routines again if `routines.json` already shows 4 — direct to `/tune-pings`.
- Never create without STEP 4's explicit confirmation.
- Never skip STEP 5b, and never report success on a routine you haven't read back. The create response is not evidence.
- Never strip or "fix" an unexpected tool grant by guessing — clear connectors via `clear_mcp_connections` (the one verified remedy), otherwise stop and hand it to the user.
- Never derive the anchor from the log; always ask (ADR-0004).
- Never ask when *pings* should land, or lead any summary with ping/routine times — talk about window resets (ADR-0005).
- Never offer a schedule choice without showing the times it actually produces. Compute them first and put them in the option. "And 3 more times through the day" describes nothing — it restates the question the user is trying to answer.
- Never write your own prompt text or fetch anything for a reset. Use the pool (STEP 2b) verbatim.
- Never grant a tool or connector to a reset routine at all — the prompt pool needs none (`adr/0010-fixed-safe-prompt-pool.md`). Never hardcode an `environment_id`.
