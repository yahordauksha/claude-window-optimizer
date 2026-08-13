"""Ping-schedule math: anchor computation and slot/cron generation.

See adr/0001-cloud-routine-scheduling-constraints.md for why these
constants are what they are (fixed 4 slots, 5h10m spacing, no repo
attachment, local-wall-clock anchor converted to UTC at generation time).
"""

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

# The usage window each reset opens. The whole anchor computation is
# about where the *uncovered* remainder of the day lands (see
# uncovered_offsets below), so this length is load-bearing, not trivia.
WINDOW_MINUTES = 300

# Only consider a day "logged" if activity fell in this trailing window.
DEFAULT_TRAILING_DAYS = 28

# Below this many distinct logged days, don't trust a computed anchor at
# all — a single day's data (e.g. the very first log entry ever written,
# which is /setup-window-optimizer's own invocation, since the
# UserPromptSubmit hook logs it before STEP 2 reads the log back) is not
# a "pattern," it's just whatever time setup happened to be run.
MIN_LOGGED_DAYS_TO_TRUST_ANCHOR = 3

# ...and days alone are not enough: the optimiser's answer is only as
# well-determined as the volume behind it. Reproduce with:
#
#     python3 tools/measure_anchor_stability.py
#
# Read the *quality* column, not the anchor column. Repeated draws from one
# fixed habit give:
#
#     prompts   anchor p90   quality spread
#          20      172 min          4.99 pp
#          60      277 min          1.52 pp
#          80       69 min          0.52 pp
#         200       47 min          0.20 pp
#         500      293 min          0.13 pp
#
# The anchor position wanders — sometimes badly, and not monotonically — because
# a flat habit has many phases that score identically, so the choice drifts
# between equally good options. Schedule *quality* converges cleanly and is what
# actually matters. 200 is a deliberately conservative floor: quality is already
# settled by ~80, and at 200 prompts over 28 days (~7/day) almost any real user
# qualifies, so the cost of the margin is close to zero.
#
# Two earlier revisions of this comment got this wrong and both were caught by
# reviewers. The first cited a table with no reproduction method. The second
# reported the *maximum* pairwise spread, which grows with trial count by
# construction and therefore cannot converge — at 500 prompts, 10 trials gave
# 27 min and 20 trials gave 321 min from the same generator. Any threshold
# defended by that number was defended by sampling noise. If you change this
# constant, re-run the script and read the quality column.
MIN_PROMPTS_TO_TRUST_ANCHOR = 200


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


def usage_histogram(timestamps, now, trailing_days=DEFAULT_TRAILING_DAYS):
    """Count of logged prompts per minute-of-day across the trailing window.

    Uses *every* prompt, not one per day. The thing being estimated is how
    much budget each window absorbs, and that's a function of total volume
    in that window — throwing away all but the first prompt of each day
    would discard almost all of the signal.
    """
    cutoff = now - timedelta(days=trailing_days)
    counts = [0] * MINUTES_PER_DAY
    for ts in timestamps:
        if ts >= cutoff:
            counts[ts.hour * 60 + ts.minute] += 1
    return counts


def _doubled_prefix(counts):
    """Prefix sums over counts+counts, so any wrapping range is an O(1) subtraction."""
    doubled = counts + counts
    pre = [0] * (len(doubled) + 1)
    for i, c in enumerate(doubled):
        pre[i + 1] = pre[i] + c
    return pre


def segment_lengths():
    """Minutes each reset is 'responsible for', partitioning the full 24h.

    Deliberately a partition, not the union of the 5h windows themselves.
    Windows cover 300 of each 310-minute stretch, and only 300 of the final
    510-minute overnight stretch — but the leftover minutes are *not* free:
    a prompt there opens a window itself, at an uncontrolled time. Scoring
    them as unowned created a degenerate optimum where the best-scoring
    schedule was the one that hid all of your usage in the gaps.
    """
    head = [PING_INTERVAL_MINUTES] * (SLOT_COUNT - 1)
    return head + [MINUTES_PER_DAY - sum(head)]


def segment_loads(counts, anchor_minutes):
    """Prompts riding on each reset's budget, for a given anchor. Every prompt counted once."""
    pre = _doubled_prefix(counts)
    loads = []
    start = anchor_minutes % MINUTES_PER_DAY
    for length in segment_lengths():
        loads.append(pre[start + length] - pre[start])
        start = (start + length) % MINUTES_PER_DAY
    return loads


def _center_of_longest_run(phis):
    """Middle of the longest circular run in a sorted list of candidate minutes.

    Ties are common with sparse data (many phases score identically). Picking
    the centre of the widest tied band puts the schedule in the middle of the
    plateau rather than teetering on its edge, where one new prompt next week
    would flip it.
    """
    present = set(phis)
    if len(present) == MINUTES_PER_DAY:
        return 0
    runs = []
    for start in (p for p in phis if (p - 1) % MINUTES_PER_DAY not in present):
        length = 0
        while (start + length) % MINUTES_PER_DAY in present:
            length += 1
        runs.append((length, start))
    if not runs:
        return phis[0]
    longest = max(r[0] for r in runs)
    candidates = sorted(start for length, start in runs if length == longest)
    # With several equally-wide bands (at realistic volume they're usually all
    # width 1) picking the numerically smallest start would bias every tie toward
    # midnight. Take the median band instead, so the choice doesn't systematically
    # favour one end of the clock.
    best_start = candidates[len(candidates) // 2]
    return (best_start + longest // 2) % MINUTES_PER_DAY


def compute_balanced_anchor(timestamps, now, trailing_days=DEFAULT_TRAILING_DAYS):
    """Anchor (minutes since local midnight) that spreads real usage most evenly across windows.

    You get blocked when a single window absorbs more work than its budget
    allows, then wait for it to expire. So the anchor to pick is the one that
    minimises the busiest window's share of your actual prompts — that
    maximises how much you could do before any window runs dry, and it puts a
    reset partway through a long working block instead of leaving the whole
    block riding on one budget.

    Ranked by (peak segment load, load on the long overnight segment). The
    second term breaks ties toward leaving the 510-minute stretch — the one
    with the least window coverage — over the quietest hours.

    Returns None if nothing is logged in the trailing window.
    """
    counts = usage_histogram(timestamps, now, trailing_days)
    if sum(counts) == 0:
        return None
    return best_anchor_for_histogram(counts)


def best_anchor_for_histogram(counts):
    """The phase minimising (peak segment load, long-segment load) for any usage histogram.

    Split out from compute_balanced_anchor so setup can run the *same* objective
    against a synthetic day built from the user's stated working hours, instead of
    inventing a second, weaker rule for the no-data case.
    """
    best_key = None
    best_phis = []
    for phi in range(MINUTES_PER_DAY):
        loads = segment_loads(counts, phi)
        key = (max(loads), loads[-1])
        if best_key is None or key < best_key:
            best_key, best_phis = key, [phi]
        elif key == best_key:
            best_phis.append(phi)

    return _center_of_longest_run(best_phis)


def anchor_for_working_hours(start_minutes, end_minutes):
    """Best anchor for someone who works `start`-`end` daily, before any log exists.

    Setup can't measure a habit yet, so it asks for one — working hours — and
    optimises against a flat synthetic block covering them. Crucially it uses the
    same objective /tune-pings will later use on real data, so the initial schedule
    is a coarse version of the eventual answer rather than a different idea.

    Measured against the previous behaviour (using a stated start time directly as
    the anchor), on simulated window dynamics over 5 usage profiles: this closes
    74-88% of the achievable gap for contiguous working days and is never worse.
    The case it fixes most is a concentrated evening block, where a start-time
    anchor delivered *literally zero* benefit over not installing the plugin —
    one reset at the head of the block leaves the entire block on one budget.

    Multi-block days (a morning and a late evening, with a long gap) are not
    captured by a flat block; for those this is no better than before, and no
    worse. /tune-pings fixes them once there's real data.
    """
    span = (end_minutes - start_minutes) % MINUTES_PER_DAY or MINUTES_PER_DAY
    counts = [0] * MINUTES_PER_DAY
    for offset in range(span):
        counts[(start_minutes + offset) % MINUTES_PER_DAY] = 1
    return best_anchor_for_histogram(counts)


def logged_days_in_window(timestamps, now, trailing_days=DEFAULT_TRAILING_DAYS):
    """Count of distinct calendar days with at least one logged prompt in the trailing window.

    Feeds /tune-pings' required output line ("Based on N days logged, last
    4 weeks") — shares the same trailing-window cutoff as the anchor
    computation so the two numbers stay consistent with each other.
    """
    cutoff = now - timedelta(days=trailing_days)
    recent = [ts for ts in timestamps if ts >= cutoff]
    return len(first_prompt_per_day(recent))


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
