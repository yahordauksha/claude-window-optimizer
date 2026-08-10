"""Ping-schedule math: anchor computation and slot/cron generation.

See adr/0001-cloud-routine-scheduling-constraints.md for why these
constants are what they are (fixed 4 slots, 5h10m spacing, no repo
attachment, local-wall-clock anchor converted to UTC at generation time).
"""

import math
from datetime import datetime, timedelta, timezone

# Strictly more than 5h (300min) or a ping can land inside a still-open
# window and do nothing. 5h10m sits in the middle of the plan's 5h05-5h15
# target band, away from either edge.
PING_INTERVAL_MINUTES = 310

# Fixed forever: RemoteTrigger has no delete action, so a design that
# changes slot count over time would strand orphaned routines. 4 slots at
# 310min apart tile a 24h day with every gap (including the overnight
# wrap) at or above the 300min floor: 310, 310, 310, 1440-930=510.
SLOT_COUNT = 4

MINUTES_PER_DAY = 24 * 60

# Only consider a day "logged" if activity fell in this trailing window.
DEFAULT_TRAILING_DAYS = 28

# Below this many same-weekday samples, don't let the weekday-specific
# average dominate — blend it with the all-days average instead.
MIN_WEEKDAY_SAMPLES_FOR_FULL_WEIGHT = 2
SAME_WEEKDAY_WEIGHT = 0.7

# Below this many distinct logged days, don't trust a computed anchor at
# all — a single day's data (e.g. the very first log entry ever written,
# which is /setup-window-optimizer's own invocation, since the
# UserPromptSubmit hook logs it before STEP 2 reads the log back) is not
# a "pattern," it's just whatever time setup happened to be run.
MIN_LOGGED_DAYS_TO_TRUST_ANCHOR = 3


def slot_minutes_from_anchor(anchor_minutes_of_day):
    """4 slot start times (minutes since local midnight), each PING_INTERVAL_MINUTES apart, wrapping at 24h."""
    return [(anchor_minutes_of_day + i * PING_INTERVAL_MINUTES) % MINUTES_PER_DAY for i in range(SLOT_COUNT)]


def local_minutes_to_utc(minutes_of_day, utc_offset):
    """Convert a local wall-clock minute-of-day to a UTC minute-of-day, given a timedelta UTC offset.

    Uses *today's* offset, applied once. DST drift (up to 1h) is an
    accepted, documented limitation for v1 — /tune-pings re-anchors
    weekly, which self-corrects within a week of any DST transition.
    """
    offset_minutes = int(utc_offset.total_seconds() // 60)
    return (minutes_of_day - offset_minutes) % MINUTES_PER_DAY


def cron_for_minute_of_day(minute_of_day):
    """A single fixed-daily-UTC-time 5-field cron expression, e.g. '10 11 * * *'."""
    hour, minute = divmod(minute_of_day, 60)
    return f"{minute} {hour} * * *"


def format_hhmm(minute_of_day):
    hour, minute = divmod(minute_of_day, 60)
    return f"{hour:02d}:{minute:02d}"


def build_schedule(anchor_local_minutes, utc_offset):
    """Return the 4 slots as a list of dicts: local label, UTC cron, minute-of-day (local and UTC).

    This is the one function both /setup-window-optimizer and /tune-pings
    call once they have an anchor — everything past this point is the same
    for both commands.
    """
    slots = []
    for local_minute in slot_minutes_from_anchor(anchor_local_minutes):
        utc_minute = local_minutes_to_utc(local_minute, utc_offset)
        slots.append(
            {
                "local_hhmm": format_hhmm(local_minute),
                "utc_hhmm": format_hhmm(utc_minute),
                "cron_expression": cron_for_minute_of_day(utc_minute),
            }
        )
    return slots


def parse_log_timestamps(log_path):
    """Read the prompt log, return a list of timezone-aware datetimes (local offset as originally recorded).

    Malformed lines are skipped, not fatal — a corrupted or manually-edited
    log line shouldn't take down anchor computation for every other line.
    """
    timestamps = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    timestamps.append(datetime.fromisoformat(line))
                except ValueError:
                    continue
    except FileNotFoundError:
        return []
    return timestamps


def first_prompt_per_day(timestamps):
    """Reduce to one timestamp per local calendar day: the earliest prompt that day.

    That's the actual "start of work" signal the anchor is meant to track —
    every later prompt that same day is not a new day starting.
    """
    earliest_by_day = {}
    for ts in timestamps:
        day = ts.date()
        if day not in earliest_by_day or ts < earliest_by_day[day]:
            earliest_by_day[day] = ts
    return list(earliest_by_day.values())


def _circular_mean_minutes(minutes_of_day_list):
    """Mean time-of-day via vector averaging on the 24h circle.

    A plain arithmetic mean breaks near midnight (23:45 and 00:15 average
    to ~12:00, not ~00:00) — this is the correct general solution, not
    just an edge case fix; it's used for every anchor computation, not
    conditionally applied near midnight.
    """
    if not minutes_of_day_list:
        return None
    angles = [2 * math.pi * m / MINUTES_PER_DAY for m in minutes_of_day_list]
    sin_sum = sum(math.sin(a) for a in angles)
    cos_sum = sum(math.cos(a) for a in angles)
    mean_angle = math.atan2(sin_sum, cos_sum)
    mean_minutes = (mean_angle / (2 * math.pi)) * MINUTES_PER_DAY
    return round(mean_minutes) % MINUTES_PER_DAY


def logged_days_in_window(timestamps, now, trailing_days=DEFAULT_TRAILING_DAYS):
    """Count of distinct calendar days with at least one logged prompt in the trailing window.

    Feeds /tune-pings' required output line ("Based on N days logged, last
    4 weeks") — shares the same cutoff and per-day reduction as
    compute_weighted_anchor so the two numbers stay consistent with each other.
    """
    cutoff = now - timedelta(days=trailing_days)
    recent = [ts for ts in timestamps if ts >= cutoff]
    return len(first_prompt_per_day(recent))


def compute_weighted_anchor(timestamps, now, trailing_days=DEFAULT_TRAILING_DAYS):
    """Day-of-week-weighted anchor (minutes since local midnight), or None if no data in the trailing window.

    Splits first-of-day times into "same weekday as `now`" and "all days,"
    blends them (70/30) once there are enough same-weekday samples to be
    more than noise, otherwise falls back to the all-days average alone.
    """
    cutoff = now - timedelta(days=trailing_days)
    recent = [ts for ts in timestamps if ts >= cutoff]
    if not recent:
        return None

    first_of_day = first_prompt_per_day(recent)
    all_minutes = [ts.hour * 60 + ts.minute for ts in first_of_day]

    today_weekday = now.weekday()
    same_weekday_minutes = [ts.hour * 60 + ts.minute for ts in first_of_day if ts.weekday() == today_weekday]

    all_mean = _circular_mean_minutes(all_minutes)

    if len(same_weekday_minutes) >= MIN_WEEKDAY_SAMPLES_FOR_FULL_WEIGHT:
        weekday_mean = _circular_mean_minutes(same_weekday_minutes)
        # Blend via the vector sum, not a linear average of the two
        # angles — same circular-mean reasoning applies to combining two
        # already-circular means.
        a1 = 2 * math.pi * weekday_mean / MINUTES_PER_DAY
        a2 = 2 * math.pi * all_mean / MINUTES_PER_DAY
        sin_sum = SAME_WEEKDAY_WEIGHT * math.sin(a1) + (1 - SAME_WEEKDAY_WEIGHT) * math.sin(a2)
        cos_sum = SAME_WEEKDAY_WEIGHT * math.cos(a1) + (1 - SAME_WEEKDAY_WEIGHT) * math.cos(a2)
        blended_angle = math.atan2(sin_sum, cos_sum)
        return round((blended_angle / (2 * math.pi)) * MINUTES_PER_DAY) % MINUTES_PER_DAY

    return all_mean


def current_utc_offset(now_local=None):
    """The machine's current local UTC offset, without needing an IANA zone name."""
    if now_local is None:
        now_local = datetime.now().astimezone()
    return now_local.utcoffset()


def parse_hhmm(text):
    """Parse 'HH:MM' into minutes-since-midnight, or raise ValueError with a clear message."""
    parts = text.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"expected HH:MM, got {text!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"HH:MM out of range: {text!r}")
    return hour * 60 + minute


def utc_now():
    return datetime.now(timezone.utc)
