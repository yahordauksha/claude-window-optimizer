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
              "new_cron_expression": "...", "local_hhmm": "...", "utc_hhmm": "..."}, ...]}
  or {"error": "not_set_up"} if /setup-window-optimizer hasn't run yet
  or {"error": "no_log_data"} if the trailing window has nothing logged
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from window_optimizer.paths import LOG_PATH  # noqa: E402
from window_optimizer.schedule import (  # noqa: E402
    build_schedule,
    compute_weighted_anchor,
    current_utc_offset,
    logged_days_in_window,
    parse_log_timestamps,
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
    new_anchor_minutes = compute_weighted_anchor(timestamps, now_local)
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
            }
        )

    print(
        json.dumps(
            {
                "old_anchor_local_hhmm": routines_state.get("anchor_local_hhmm"),
                "new_anchor_local_hhmm": f"{new_anchor_minutes // 60:02d}:{new_anchor_minutes % 60:02d}",
                "logged_days": logged_days_in_window(timestamps, now_local),
                "trailing_days": 28,
                "slots": slots,
            }
        )
    )


if __name__ == "__main__":
    main()
