#!/usr/bin/env python3
"""CLI: recompute the weighted anchor from the log and diff it against the currently-installed routines.

Used by /tune-pings. Never touches a live Cloud Routine itself — that's
the command's own job via the RemoteTrigger tool (this script has no
network access and no auth). This script only computes what *should*
change; the command shows the diff, confirms, then applies it.

Prints one JSON object to stdout:
  {"old_anchor_local_hhmm": "06:45", "new_anchor_local_hhmm": "06:00",
   "logged_days": 23, "trailing_days": 28,
   "slots": [{"slot": 0, "trigger_id": "trig_...", "old_cron_expression": "...",
              "new_cron_expression": "...", "local_hhmm": "...", "utc_hhmm": "...",
              "prompt_key": "water", "title": "Water"}, ...]}
  or {"error": "not_set_up"} if /setup-window-optimizer hasn't run yet
  or {"error": "no_log_data"} if the trailing window has nothing logged
  or {"error": "insufficient_log_data", "logged_days": N, "needed_days": M} if there's
    some data but too few distinct days to re-anchor on without swinging the schedule
    around noise — keep the current anchor and try again later

Prompt identity is passed through unchanged — /tune-pings only ever
re-anchors timing, never what the resets say.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from window_optimizer.paths import LOG_PATH  # noqa: E402
from window_optimizer.schedule import (  # noqa: E402
    MIN_LOGGED_DAYS_TO_TRUST_ANCHOR,
    MIN_PROMPTS_TO_TRUST_ANCHOR,
    build_schedule,
    compute_balanced_anchor,
    current_utc_offset,
    logged_days_in_window,
    parse_log_timestamps,
    usage_histogram,
    utc_now,
)
from window_optimizer.state import read_routines_state  # noqa: E402


def main():
    routines_state = read_routines_state()
    if not routines_state or not routines_state.get("routines"):
        print(json.dumps({"error": "not_set_up"}))
        sys.exit(0)

    now_local = utc_now().astimezone()
    timestamps = parse_log_timestamps(LOG_PATH)
    days_logged = logged_days_in_window(timestamps, now_local)
    if days_logged == 0:
        print(json.dumps({"error": "no_log_data"}))
        sys.exit(0)
    prompts_logged = sum(usage_histogram(timestamps, now_local))
    if days_logged < MIN_LOGGED_DAYS_TO_TRUST_ANCHOR or prompts_logged < MIN_PROMPTS_TO_TRUST_ANCHOR:
        # Both floors matter and they catch different things: too few days
        # means no habit yet, too few prompts means the optimiser's answer is
        # a tie-break rather than a measurement (see MIN_PROMPTS_TO_TRUST_ANCHOR
        # for the measured swing). Keep the current schedule and say why.
        print(
            json.dumps(
                {
                    "error": "insufficient_log_data",
                    "logged_days": days_logged,
                    "needed_days": MIN_LOGGED_DAYS_TO_TRUST_ANCHOR,
                    "logged_prompts": prompts_logged,
                    "needed_prompts": MIN_PROMPTS_TO_TRUST_ANCHOR,
                }
            )
        )
        sys.exit(0)
    new_anchor_minutes = compute_balanced_anchor(timestamps, now_local)
    if new_anchor_minutes is None:
        print(json.dumps({"error": "no_log_data"}))
        sys.exit(0)

    offset = current_utc_offset(now_local)
    new_slots = build_schedule(new_anchor_minutes, offset)
    old_routines = sorted(routines_state["routines"], key=lambda r: r["slot"])

    if len(old_routines) != len(new_slots):
        # Should be structurally impossible (slot count is fixed at 4 everywhere),
        # but fail loud rather than silently zipping mismatched lists together.
        print(json.dumps({"error": "slot_count_mismatch", "expected": len(new_slots), "found": len(old_routines)}))
        sys.exit(1)

    slots = []
    for old, new in zip(old_routines, new_slots):
        slots.append(
            {
                "slot": old["slot"],
                "trigger_id": old["trigger_id"],
                "old_cron_expression": old["cron_expression"],
                "new_cron_expression": new["cron_expression"],
                "local_hhmm": new["local_hhmm"],
                "utc_hhmm": new["utc_hhmm"],
                "prompt_key": old.get("prompt_key"),
                "title": old.get("title"),
            }
        )

    # Whether anything actually needs pushing to the API is a question about the
    # *cron expressions*, not about the anchor. Those come apart across a DST
    # transition: the habit is in local wall-clock time, so the anchor is
    # unchanged (08:00 -> 08:00) while the correct UTC cron shifts an hour
    # (0 7 * * * -> 0 6 * * *). Keying the decision off the anchor meant the
    # corrected cron was computed and then thrown away in exactly the case the
    # DST note in schedule.py claimed /tune-pings would self-correct.
    cron_changed = any(s["old_cron_expression"] != s["new_cron_expression"] for s in slots)

    print(
        json.dumps(
            {
                "old_anchor_local_hhmm": routines_state.get("anchor_local_hhmm"),
                "new_anchor_local_hhmm": f"{new_anchor_minutes // 60:02d}:{new_anchor_minutes % 60:02d}",
                "cron_changed": cron_changed,
                "logged_days": logged_days_in_window(timestamps, now_local),
                "logged_prompts": prompts_logged,
                "trailing_days": 28,
                "slots": slots,
            }
        )
    )


if __name__ == "__main__":
    main()
