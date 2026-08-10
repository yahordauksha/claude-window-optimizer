#!/usr/bin/env python3
"""CLI: print the exact ping prompt + allowed_tools for a given content kind.

Used by /setup-window-optimizer STEP 5 so the prompt text and tool grant
come from tested code, not composed ad hoc per invocation.

Usage:
  build_ping_prompt.py --kind simple
  build_ping_prompt.py --kind github-issues --repo owner/name

Prints one JSON object: {"prompt": "...", "allowed_tools": [...]}
or {"error": "..."} on bad input.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from window_optimizer.ping_content import KNOWN_KINDS, allowed_tools_for_kind, prompt_for_kind  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True, choices=KNOWN_KINDS)
    parser.add_argument("--repo", help="'owner/name', required for github-issues")
    args = parser.parse_args()

    try:
        prompt = prompt_for_kind(args.kind, repo=args.repo)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    print(json.dumps({"prompt": prompt, "allowed_tools": allowed_tools_for_kind(args.kind)}))


if __name__ == "__main__":
    main()
