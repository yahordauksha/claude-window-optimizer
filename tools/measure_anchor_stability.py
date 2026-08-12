#!/usr/bin/env python3
"""Measure how well-determined the computed anchor is at a given usage volume.

Exists because ADR-0007 originally published a stability table with no
generating profile, noise model, or trial count. An independent reviewer tried
to reproduce it and got materially different numbers — which made the threshold
it justified (MIN_PROMPTS_TO_TRUST_ANCHOR) unfalsifiable as written. This script
is the missing method: fixed seed, stated profile, stated noise, runnable.

    python3 tools/measure_anchor_stability.py

Method: draw `trials` independent logs from the *same* underlying habit, differing
only in noise, and measure how far apart the chosen anchors land (max circular
distance between any two). A well-determined estimate should barely move; a
poorly-determined one wanders, and any schedule derived from it is a coin flip
wearing a measurement's clothes.

Reported spread is a worst-case (max over all pairs), not a standard deviation —
so it is deliberately pessimistic and comparable across rows.
"""

import argparse
import os
import random
import statistics
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from window_optimizer.schedule import MINUTES_PER_DAY, compute_balanced_anchor  # noqa: E402

# One fixed, stated habit so rows differ only by volume: a working day roughly
# 09:00-17:00, each prompt jittered by a normal draw. Nothing about the result
# should depend on this being realistic — only on it being *the same* across rows.
WORKDAY_START_MIN = 9 * 60
WORKDAY_END_MIN = 17 * 60
JITTER_STDDEV_MIN = 25

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
BASE = datetime(2026, 8, 10, tzinfo=timezone.utc)


def draw_log(rnd, total_prompts, days):
    per_day = max(1, total_prompts // days)
    stamps = []
    for day in range(1, days + 1):
        for _ in range(per_day):
            minute = rnd.uniform(WORKDAY_START_MIN, WORKDAY_END_MIN) + rnd.gauss(0, JITTER_STDDEV_MIN)
            stamps.append(BASE - timedelta(days=day) + timedelta(minutes=minute % MINUTES_PER_DAY))
    return stamps


def circular_distance(a, b):
    return min((a - b) % MINUTES_PER_DAY, (b - a) % MINUTES_PER_DAY)


def measure(total_prompts, days, trials, seed):
    rnd = random.Random(seed)
    anchors = []
    for _ in range(trials):
        anchor = compute_balanced_anchor(draw_log(rnd, total_prompts, days), NOW)
        if anchor is not None:
            anchors.append(anchor)
    if len(anchors) < 2:
        return None, None
    spread = max(circular_distance(a, b) for a in anchors for b in anchors)
    pairwise = [circular_distance(a, b) for i, a in enumerate(anchors) for b in anchors[i + 1 :]]
    return spread, statistics.median(pairwise)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--trials", type=int, default=15)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    print(f"habit: {WORKDAY_START_MIN // 60:02d}:00-{WORKDAY_END_MIN // 60:02d}:00, ", end="")
    print(f"jitter sd={JITTER_STDDEV_MIN}min, days={args.days}, trials={args.trials}, seed={args.seed}")
    print()
    print(f"{'prompts':>8} {'worst spread':>13} {'median spread':>14}")
    for total in (20, 40, 60, 80, 100, 120, 150, 200, 300, 500):
        worst, median = measure(total, args.days, args.trials, args.seed)
        if worst is None:
            print(f"{total:>8} {'n/a':>13} {'n/a':>14}")
            continue
        print(f"{total:>8} {worst:>10} min {median:>11} min")


if __name__ == "__main__":
    main()
