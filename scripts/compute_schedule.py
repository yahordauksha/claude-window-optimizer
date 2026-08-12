#!/usr/bin/env python3
"""CLI: compute the 4-slot ping schedule from an explicit anchor time.

Used by /setup-window-optimizer, which always asks the user for their
rough start-of-day rather than computing one. That's deliberate: on a
first run the log is either empty or dominated by the last few minutes
of installing and poking at this plugin, so a "computed" anchor there
is a faithful average of noise — technically correct, practically
useless, and confusing to be shown as if it were a real pattern.

Log-based anchoring lives exclusively in tune_schedule.py (/tune-pings),
where the trailing-4-weeks window is long enough for the data to mean
something. See adr/0004-setup-always-asks-for-the-anchor.md.

Usage:
  compute_schedule.py --hours HH:MM-HH:MM   # preferred: derive the anchor from working hours
  compute_schedule.py --anchor HH:MM        # use an explicit anchor as-is

Prints one JSON object to stdout:
  {"anchor_local_hhmm": "06:00", "utc_offset_hours": 2.0, "slots": [...]}
  or {"error": "invalid_anchor", "detail": "..."} (exit 1) on an unparseable time.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from window_optimizer.schedule import (  # noqa: E402
    anchor_for_working_hours,
    build_schedule,
    current_utc_offset,
    format_hhmm,
    parse_hhmm,
)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--hours", help="working hours, HH:MM-HH:MM (anchor is derived from these)")
    group.add_argument("--anchor", help="local anchor time, HH:MM, used as-is")
    args = parser.parse_args()

    try:
        if args.hours:
            start_text, _, end_text = args.hours.partition("-")
            if not end_text:
                raise ValueError(f"expected HH:MM-HH:MM, got {args.hours!r}")
            anchor_minutes = anchor_for_working_hours(parse_hhmm(start_text), parse_hhmm(end_text))
        else:
            anchor_minutes = parse_hhmm(args.anchor)
    except ValueError as e:
        print(json.dumps({"error": "invalid_anchor", "detail": str(e)}))
        sys.exit(1)

    offset = current_utc_offset()
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
