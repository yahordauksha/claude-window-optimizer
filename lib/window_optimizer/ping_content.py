"""What each scheduled reset actually says.

A reset works by sending *a* message — the content is irrelevant to the
mechanism. So the content should be chosen to cost as little as possible, in
every sense: cheap to run, harmless if it fails, and impossible to weaponise.

Every prompt here is self-contained. None fetches anything, none reads anything,
none needs a tool. That's the point: an earlier design had these routines fetch a
GitHub repo's open issue titles, which meant an unattended agent with network
access read text any stranger could write by opening an issue. See
adr/0010-fixed-safe-prompt-pool.md for why that whole idea was dropped rather
than defended.
"""

import random

# Deliberately fixed and inspectable. Adding one is a code change with review,
# not a runtime input — nothing here is ever assembled from data the user or
# anyone else supplies.
SAFE_PROMPTS = {
    "weather": {
        "title": "Weather",
        "prompt": "Brief weather summary for today, one sentence max.",
    },
    "time": {
        "title": "Time",
        "prompt": "Current local time only.",
    },
    "focus": {
        "title": "Focus reminder",
        "prompt": "Reply with a one-word focus reminder.",
    },
    "breathe": {
        "title": "Breathe",
        "prompt": "Remind me to take a breath. One short sentence.",
    },
    "check": {
        "title": "Check-in",
        "prompt": "Quick check-in. Reply 'here'.",
    },
    "water": {
        "title": "Water",
        "prompt": "Remind me to drink water. One short sentence.",
    },
    "stretch": {
        "title": "Stretch",
        "prompt": "Suggest a quick stretch. Keep it under 10 words.",
    },
    "mood": {
        "title": "Mood",
        "prompt": "How are you? Reply with one word.",
    },
    "day": {
        "title": "Day",
        "prompt": "What day is it today? Reply with just the day name.",
    },
    "note": {
        "title": "Note",
        "prompt": "Leave a short encouraging note. One sentence max.",
    },
    "pause": {
        "title": "Pause",
        "prompt": "Remind me to pause for a second. One short sentence.",
    },
    "posture": {
        "title": "Posture",
        "prompt": "Quick posture check reminder. Under 8 words.",
    },
    "eyes": {
        "title": "Eyes",
        "prompt": "Remind me to rest my eyes. One short sentence.",
    },
    "ok": {
        "title": "OK",
        "prompt": "Reply with just 'ok'.",
    },
    "alive": {
        "title": "Alive",
        "prompt": "Reply with just 'alive'.",
    },
}


def allowed_tools():
    """No prompt in the pool needs a tool, so no routine is granted one."""
    return []


def prompt_for_key(key):
    """Look up one prompt by its stable key. Raises on an unknown key rather than guessing."""
    if key not in SAFE_PROMPTS:
        raise ValueError(f"unknown prompt key: {key!r}")
    entry = SAFE_PROMPTS[key]
    return {"key": key, "title": entry["title"], "prompt": entry["prompt"]}


def pick_prompts(count, rng=None):
    """Pick `count` distinct prompts at random.

    Distinct rather than independent draws so four routines don't end up saying
    the same thing four times a day. `rng` is injectable so tests are deterministic
    without the caller having to seed the global random module.
    """
    if count > len(SAFE_PROMPTS):
        raise ValueError(f"asked for {count} prompts, pool has {len(SAFE_PROMPTS)}")
    rng = rng or random.Random()
    return [prompt_for_key(key) for key in rng.sample(sorted(SAFE_PROMPTS), count)]
