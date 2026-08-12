#!/usr/bin/env python3
"""UserPromptSubmit hook: append a timestamp-only line to the local prompt log.

Never logs prompt content — only when a prompt happened, which is all
/tune-pings' anchor computation needs. Always exits 0 and always emits
valid JSON on stdout, even on internal error, per the hook contract:
a nonzero exit or a stack trace on stdout would block the prompt / break
the rest of the hook chain for this event.
"""

import json
import os
import sys
from datetime import datetime

_PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PLUGIN_ROOT, "lib"))

from window_optimizer.paths import LOG_PATH, ensure_data_dir  # noqa: E402


def main():
    # Write first, parse second. This hook needs no field from stdin, so letting a
    # malformed/empty payload abort the one thing it exists to do was backwards —
    # the timestamp was silently dropped whenever stdin wasn't valid JSON.
    try:
        ensure_data_dir()
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(timestamp + "\n")
    except Exception as e:
        print(f"window-optimizer log_prompt hook error: {e}", file=sys.stderr)

    try:
        # Drain stdin so the writer never blocks on a full pipe, but nothing here
        # depends on it parsing.
        sys.stdin.read()
    except Exception:
        pass
    finally:
        print(json.dumps({}))
        sys.exit(0)


if __name__ == "__main__":
    main()
