#!/usr/bin/env python3
"""SessionStart hook: nudge toward /tune-pings if it's been 7+ days, at most once/day.

Reference point for "days since": the last /tune-pings completion if one
has ever happened, otherwise setup time (/setup-window-optimizer's
install timestamp) as a fallback so a fresh install doesn't go silent
forever just because /tune-pings hasn't run yet. If neither exists, the
plugin hasn't been set up at all — say nothing; nagging about a tune-up
for a mechanism that doesn't exist yet would be confusing, not helpful.

Always exits 0, always emits valid JSON, per the hook contract.
"""

import json
import os
import sys
from datetime import datetime

_PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PLUGIN_ROOT, "lib"))

from window_optimizer.state import (  # noqa: E402
    read_reminder_state,
    read_routines_state,
    read_tune_state,
    write_reminder_state,
)

REMINDER_THRESHOLD_DAYS = 7


def build_context(now):
    tune_state = read_tune_state()
    if tune_state and tune_state.get("last_tune_up"):
        reference = datetime.fromisoformat(tune_state["last_tune_up"])
        message_kind = "tuned"
    else:
        routines_state = read_routines_state()
        if routines_state and routines_state.get("installed_at"):
            reference = datetime.fromisoformat(routines_state["installed_at"])
            message_kind = "never_tuned"
        else:
            return None  # not set up yet — nothing to remind about

    days_since = (now - reference).days
    if days_since < REMINDER_THRESHOLD_DAYS:
        return None

    today = now.date().isoformat()
    reminder_state = read_reminder_state()
    if reminder_state and reminder_state.get("last_shown_date") == today:
        return None  # already shown once today

    write_reminder_state(today)

    if message_kind == "tuned":
        return f"{days_since} days since the last tune-up, worth running /tune-pings."
    return f"{days_since} days since setup with no tune-up run yet, worth running /tune-pings."


def main():
    try:
        json.load(sys.stdin)
        now = datetime.now().astimezone()
        context = build_context(now)
    except Exception as e:
        print(f"window-optimizer session_start_reminder hook error: {e}", file=sys.stderr)
        context = None

    if context:
        output = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    else:
        output = {}
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
