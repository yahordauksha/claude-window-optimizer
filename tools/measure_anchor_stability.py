#!/usr/bin/env python3
"""Measure how well-determined the computed anchor is at a given usage volume.

Exists because ADR-0007 originally published a stability table with no
generating profile, noise model, or trial count. An independent reviewer tried
to reproduce it and got materially different numbers — which made the threshold
it justified (MIN_PROMPTS_TO_TRUST_ANCHOR) unfalsifiable as written. This script
is the missing method: fixed seed, stated profile, stated noise, runnable.

    python3 tools/measure_anchor_stability.py

Method: draw `trials` independent logs from the *same* underlying habit, differing
only in noise, and measure how far apart the chosen anchors land. A well-determined
estimate barely moves; a poorly-determined one wanders, and any schedule derived
from it is a coin flip wearing a measurement's clothes.

Reports two things, and the second is the one that matters:

  * how far the chosen anchor moves (median / p90 pairwise circular distance)
  * how much the resulting schedule's quality moves (spread in peak segment load)

A wandering anchor is only a problem if the schedules it picks are worse. On a
flat habit many phases score identically, so the anchor drifts between equally
good options — position spread stays high while quality spread goes to zero.
Gating on position alone would withhold a perfectly good tune-up.

An earlier version of this script reported the *maximum* pairwise distance,
described as "deliberately pessimistic". That was a mistake, and a third reviewer
caught it: a maximum over pairs grows monotonically with the number of trials, so
it cannot converge and is not an estimator of anything. Measured directly — at 500
prompts, 10 trials gave 27 min and 20 trials gave 321 min from the same generator.
Percentiles converge; maxima do not. Any threshold justified by the old numbers was
justified by sampling noise.
"""

import argparse
import os
import random
import statistics
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from window_optimizer.schedule import (  # noqa: E402
    MINUTES_PER_DAY,
    compute_balanced_anchor,
    segment_loads,
    usage_histogram,
)

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
    anchors, qualities = [], []
    for _ in range(trials):
        log = draw_log(rnd, total_prompts, days)
        anchor = compute_balanced_anchor(log, NOW)
        if anchor is None:
            continue
        anchors.append(anchor)
        counts = usage_histogram(log, NOW)
        total = max(1, sum(counts))
        qualities.append(max(segment_loads(counts, anchor)) / total)
    if len(anchors) < 2:
        return None, None, None
    pairwise = sorted(circular_distance(a, b) for i, a in enumerate(anchors) for b in anchors[i + 1 :])
    p90 = pairwise[min(len(pairwise) - 1, int(0.9 * len(pairwise)))]
    return statistics.median(pairwise), p90, statistics.pstdev(qualities) * 100


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--trials", type=int, default=25)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    print(f"habit: {WORKDAY_START_MIN // 60:02d}:00-{WORKDAY_END_MIN // 60:02d}:00, ", end="")
    print(f"jitter sd={JITTER_STDDEV_MIN}min, days={args.days}, trials={args.trials}, seed={args.seed}")
    print()
    print(f"{'prompts':>8} {'anchor median':>14} {'anchor p90':>12} {'quality spread':>16}")
    for total in (20, 40, 60, 80, 100, 150, 200, 300, 500):
        median, p90, quality = measure(total, args.days, args.trials, args.seed)
        if median is None:
            print(f"{total:>8} {'n/a':>14} {'n/a':>12} {'n/a':>16}")
            continue
        print(f"{total:>8} {median:>11.0f} min {p90:>9.0f} min {quality:>13.2f} pp")


if __name__ == "__main__":
    main()
