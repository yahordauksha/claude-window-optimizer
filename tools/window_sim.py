#!/usr/bin/env python3
"""Simulate real usage-window dynamics, so claims about benefit can be checked.

ADR-0007 declined to build this ("the added fidelity only matters in exactly the
case the design is trying to prevent... a gain that's speculative"). Two rounds of
independent review both flagged the consequence: every test in this repo scored the
optimiser against *its own objective*, and nothing anywhere simulated a window
opening or closing. An optimiser proven optimal against an unvalidated target is
exactly as good as its target.

This is the missing piece. It is deliberately NOT in `lib/` — it ships with the
repo, not with the plugin, and nothing at runtime imports it.

The model, stated plainly so it can be argued with:

  * A window opens when a message arrives and no window is currently open.
  * A window lasts WINDOW_MINUTES and cannot be extended or restarted early.
  * Both your prompts and the plugin's scheduled resets are messages. A reset that
    lands inside an open window does nothing at all — that is the whole reason the
    spacing floor exists.
  * Every prompt draws budget from whichever window was open when it arrived.

What it does NOT model: token weight (hooks don't expose it), the weekly cap, or
per-window budget size. So it measures *how work is distributed across windows*,
not whether you personally get blocked. Distribution is the thing the schedule can
actually influence; the rest is not in the plugin's control.
"""

import sys
from dataclasses import dataclass, field

WINDOW_MINUTES = 300
MINUTES_PER_DAY = 1440


@dataclass
class SimResult:
    window_loads: list = field(default_factory=list)
    windows_opened: int = 0
    resets_wasted: int = 0  # scheduled resets that landed inside an open window

    @property
    def peak_load(self):
        return max(self.window_loads) if self.window_loads else 0

    @property
    def total_prompts(self):
        return sum(self.window_loads)


def simulate(prompt_minutes, reset_minutes_of_day, days, window_minutes=WINDOW_MINUTES):
    """Run the window model over `days` days.

    `prompt_minutes` are absolute minutes from t=0. `reset_minutes_of_day` are
    daily local times (or empty for the no-plugin baseline).
    """
    resets = [day * MINUTES_PER_DAY + minute for day in range(days) for minute in sorted(reset_minutes_of_day)]
    events = sorted([(t, "prompt") for t in prompt_minutes] + [(t, "reset") for t in resets])

    window_end = None
    loads = {}
    opened = 0
    wasted = 0
    current = None

    for time, kind in events:
        window_open = window_end is not None and time < window_end
        if not window_open:
            current = time
            window_end = time + window_minutes
            opened += 1
            loads[current] = 0
        elif kind == "reset":
            # Landed inside a live window: a no-op, which is precisely what the
            # >5h spacing floor exists to avoid.
            wasted += 1
        if kind == "prompt":
            loads[current] += 1

    return SimResult(
        window_loads=[v for v in loads.values() if v > 0],
        windows_opened=opened,
        resets_wasted=wasted,
    )


def main():
    import random

    from window_optimizer.schedule import slot_minutes_from_anchor

    profiles = {
        "9-5 steady": [(9 * 60, 17 * 60)],
        "evening 20:00-01:00": [(20 * 60, 25 * 60)],
        "split day": [(8 * 60, 10 * 60), (19 * 60, 25 * 60)],
        "bursty 09-18": [(9 * 60, 11 * 60), (14 * 60, 18 * 60)],
        "long day 08-23": [(8 * 60, 23 * 60)],
    }
    days, per_day = 28, 35
    print(f"{days} days, {per_day} prompts/day, mean of 30 seeds\n")
    print(f"{'profile':22s} {'no plugin':>10} {'with plugin':>12} {'change':>9} {'wasted resets':>14}")
    for name, blocks in profiles.items():
        base, opt, waste = [], [], []
        for seed in range(30):
            rnd = random.Random(seed)
            prompts = []
            for day in range(days):
                for _ in range(per_day):
                    lo, hi = blocks[rnd.randrange(len(blocks))]
                    prompts.append(day * MINUTES_PER_DAY + int(rnd.uniform(lo, hi)) % MINUTES_PER_DAY)
            prompts.sort()
            base.append(simulate(prompts, [], days).peak_load)
            anchor = 8 * 60
            r = simulate(prompts, slot_minutes_from_anchor(anchor), days)
            opt.append(r.peak_load)
            waste.append(r.resets_wasted)
        b, o = sum(base) / len(base), sum(opt) / len(opt)
        pct = (b - o) / b * 100 if b else 0
        print(f"{name:22s} {b:10.1f} {o:12.1f} {pct:8.1f}% {sum(waste) / len(waste):14.1f}")


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/", 2)[0] + "/lib")
    main()
