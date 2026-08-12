---
description: One-time setup — asks once when you want your usage window to reset each day, then schedules 4 daily resets. Auto-detects a repo so each scheduled message reports real open issues instead of being a no-op (no extra question asked).
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

## STEP 2 — Ask for the reset time (always — never compute it here)

**Print exactly one question, nothing before it:**

```
What time do you want your usage window to reset each day? It'll reset then
and 3 more times through the day. (HH:MM, local — rough is fine, /tune-pings
corrects it from real usage later.)
```

Use `AskUserQuestion` or a plain question. No preamble, no anchor lecture — the question carries its own meaning.

**Always ask. Never read the log for this.** On a first run the log is empty or dominated by the last few minutes of installing this plugin, so anything computed from it is noise that reads as "roughly now" (see `adr/0004-setup-always-asks-for-the-anchor.md`). `compute_schedule.py` has no `--from-log` mode — don't reintroduce one.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compute_schedule.py" --anchor <HH:MM>
```

(Always `${CLAUDE_PLUGIN_ROOT}`, never a bare relative `scripts/...` path — the working directory is whatever project the user has open.)

`{"error": "invalid_anchor"}` → ask again, don't guess a correction. Otherwise you have `anchor_local_hhmm`, `utc_offset_hours`, and `slots` (4 × `local_hhmm`, `utc_hhmm`, `cron_expression`).

## STEP 2b — Auto-detect a repo (silent, no question, print nothing)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_repo.py"
```

Tries the current project's git remote, falls back to the account's most recently pushed public repo via `gh`, confirms public before returning. Returns `{"repo": "owner/name"}` or `{"repo": null}`.

- Repo found → all 4 slots use `github-issues` for it.
- Nothing found → all 4 use `simple`. One clause in STEP 4's proposal, not an apology.

Never ask which repo. Never use a repo `detect_repo.py` didn't confirm public. v1 has no other check kinds — don't volunteer that email/calendar aren't built unless the user raises it.

## STEP 2c — Build the prompt + tool grant (print nothing)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_ping_prompt.py" --kind simple
# or:
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_ping_prompt.py" --kind github-issues --repo owner/name
```

Returns `{"prompt": "...", "allowed_tools": [...]}`. Hold both for STEP 5 and STEP 5b's check. The tool grant comes from this script — never compose one by hand.

## STEP 3 — Resolve the environment (print nothing)

`ToolSearch select:RemoteTrigger`, then `{"action": "list"}`.

- Any existing routine → reuse its `job_config.ccr.environment_id`.
- No routines at all → invoke the `schedule` skill once, asking only which environment(s) exist; let it create nothing. Never hardcode an environment id.

Note whether any pre-existing routine looks like an old ad-hoc keep-alive (e.g. "Start session at ...") — one line about it in STEP 7, not STEP 4.

## STEP 4 — Propose, confirm once

**Print exactly this shape and nothing more:**

```
Your window will reset daily at 08:00, 13:10, 18:20, 23:30 (local).
4 routines in your Cloud Routines list, each checks <owner/name>'s open
issues when it fires. Nothing else is granted.

Create them?
```

If no repo was detected, the second line is `4 routines in your Cloud Routines list, each sends a short keep-alive message.` Do not add a cron table, a per-slot breakdown, a model name, or a tool-grant list — if the user wants those, they'll ask.

**Wait for explicit confirmation.** Creating routines is never a silent apply.

## STEP 5 — Create the 4 routines (print nothing until STEP 5b passes)

Per slot:

```json
{
  "action": "create",
  "body": {
    "name": "Window reset <slot+1>/4 — <local_hhmm> local",
    "cron_expression": "<slots[i].cron_expression>",
    "enabled": true,
    "mcp_connections": [],
    "job_config": {
      "ccr": {
        "environment_id": "<from STEP 3>",
        "session_context": {
          "model": "claude-haiku-4-5-20251001",
          "allowed_tools": "<this slot's allowed_tools from STEP 2c>"
        },
        "events": [
          {
            "data": {
              "uuid": "<fresh lowercase v4 uuid, one per call>",
              "session_id": "",
              "type": "user",
              "parent_tool_use_id": null,
              "message": { "role": "user", "content": "<this slot's prompt from STEP 2c>" }
            }
          }
        ]
      }
    }
  }
}
```

`"mcp_connections": []` is sent to make intent legible, but it is **confirmed ignored** — the server attaches account-default connectors regardless. STEP 5b is what actually removes them. Don't mistake this field for the fix.

Record each returned `trigger_id` against its slot.

## STEP 5b — Verify what was actually created (never trust the create response)

**This step exists because of a real incident**: a create request that specified no connectors came back with five attached (Gmail, Calendar, Microsoft 365, Notion, Claude Code Remote) — the server applied account-level defaults. The command had asserted its own tool grant from the request it sent and never read back what existed, so a routine violating this plugin's own minimal-grant invariant went live and was only caught by eye. See `adr/0006-verify-created-routines.md`.

For **each** created routine, call `{"action": "get", "trigger_id": "<id>"}` and check the returned object:

1. **`mcp_connections` is non-empty** → expect this; it happens on every create. Call `{"action": "update", "trigger_id": "<id>", "body": {"clear_mcp_connections": true}}`, then `get` **again** to confirm it's now `[]`. (Verified working across 4 real routines.) If it's still non-empty after the clear, **stop everything**: report which routine, that it has connectors you couldn't remove, and that it must be deleted manually at https://claude.ai/code/routines. Do not create further routines.
2. **`session_context.allowed_tools` differs from what STEP 2c returned for that slot** → **stop everything**, report the exact difference, and say the routine must be deleted manually. Never "fix" a tool grant by guessing.
3. **`cron_expression` differs from what was sent** → same: stop and report.
4. **`enabled` is not `true`** → don't silently re-enable it; the user may have turned it off deliberately. Note it in STEP 7's report as one extra line.

Only once every routine passes may you proceed. Print nothing about this step unless something failed or check 4 tripped — a passing verification is not news.

## STEP 6 — Persist local state (print nothing)

Inline `python3 -c "..."` with `"${CLAUDE_PLUGIN_ROOT}/lib"` on `sys.path`, calling `window_optimizer.state.write_routines_state(installed_at_iso, anchor_local_hhmm, routines)`:

- `installed_at_iso` = `datetime.now().astimezone().isoformat()`
- `anchor_local_hhmm` = STEP 2's value
- `routines` = per slot: `{"slot", "trigger_id", "local_hhmm", "utc_hhmm", "cron_expression", "kind", "repo"}`

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
- Never ask which repo to use; auto-detect (ADR-0003). Never use a repo not confirmed public.
- Never grant a tool or connector beyond what `allowed_tools_for_kind` returns, and never hardcode an `environment_id`.
