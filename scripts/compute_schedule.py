#!/usr/bin/env python3
"""CLI: compute the 4-slot ping schedule, either from an explicit anchor or from the log.

Used by /setup-window-optimizer. All deterministic math lives in
window_optimizer.schedule — this script is a thin CLI wrapper so the
command can call it via Bash and parse the JSON result, rather than
asking the model to do date/circular-mean arithmetic inline at runtime.

Usage:
  compute_schedule.py --anchor HH:MM     # anchor given directly (e.g. week-one, asked interactively)
  compute_schedule.py --from-log         # weighted anchor computed from the prompt log

Prints one JSON object to stdout:
  {"anchor_local_hhmm": "06:00", "utc_offset_hours": 2.0, "slots": [...]}
  or {"error": "no_log_data"} if --from-log finds nothing in the trailing window.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from window_optimizer.paths import LOG_PATH  # noqa: E402
from window_optimizer.schedule import (  # noqa: E402
    build_schedule,
    compute_weighted_anchor,
    current_utc_offset,
    format_hhmm,
    parse_hhmm,
    parse_log_timestamps,
    utc_now,
)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--anchor", help="explicit local anchor time, HH:MM")
    group.add_argument("--from-log", action="store_true", help="compute a weighted anchor from the prompt log")
    args = parser.parse_args()

    offset = current_utc_offset()

    if args.anchor:
        try:
            anchor_minutes = parse_hhmm(args.anchor)
        except ValueError as e:
            print(json.dumps({"error": "invalid_anchor", "detail": str(e)}))
            sys.exit(1)
    else:
        timestamps = parse_log_timestamps(LOG_PATH)
        anchor_minutes = compute_weighted_anchor(timestamps, utc_now().astimezone())
        if anchor_minutes is None:
            print(json.dumps({"error": "no_log_data"}))
            sys.exit(0)

    slots = build_schedule(anchor_minutes, offset)
    print(
        json.dumps(
            {
                "anchor_local_hhmm": format_hhmm(anchor_minutes),
                "utc_offset_hours": offset.total_seconds() / 3600,
                "slots": slots,
            }
        )
    )


if __name__ == "__main__":
    main()
