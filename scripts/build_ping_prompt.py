#!/usr/bin/env python3
"""CLI: pick the prompts the scheduled resets will send.

Used by /setup-window-optimizer so the text and tool grant come from tested code
rather than being composed per invocation.

Usage:
  build_ping_prompt.py --count 4        # pick 4 distinct prompts at random
  build_ping_prompt.py --key water      # look up one specific prompt
  build_ping_prompt.py --list           # show the whole pool

Prints JSON: {"allowed_tools": [], "prompts": [{"key","title","prompt"}, ...]}
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from window_optimizer.ping_content import (  # noqa: E402
    SAFE_PROMPTS,
    allowed_tools,
    pick_prompts,
    prompt_for_key,
)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--count", type=int, help="pick this many distinct prompts at random")
    group.add_argument("--key", help="look up one prompt by key")
    group.add_argument("--list", action="store_true", help="print the whole pool")
    parser.add_argument("--seed", type=int, help="seed the picker, for reproducible output")
    args = parser.parse_args()

    try:
        if args.list:
            prompts = [prompt_for_key(k) for k in sorted(SAFE_PROMPTS)]
        elif args.key:
            prompts = [prompt_for_key(args.key)]
        else:
            import random

            prompts = pick_prompts(args.count, rng=random.Random(args.seed) if args.seed is not None else None)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    print(json.dumps({"allowed_tools": allowed_tools(), "prompts": prompts}))


if __name__ == "__main__":
    main()
