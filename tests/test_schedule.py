import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from window_optimizer.schedule import (
    PING_INTERVAL_MINUTES,
    WINDOW_MINUTES,
    build_schedule,
    compute_balanced_anchor,
    cron_for_minute_of_day,
    first_prompt_per_day,
    local_minutes_to_utc,
    logged_days_in_window,
    parse_hhmm,
    parse_log_timestamps,
    segment_lengths,
    segment_loads,
    slot_minutes_from_anchor,
    usage_histogram,
)

# ---- Spacing invariant: this is the whole point of the plugin ----


def test_all_gaps_are_strictly_over_five_hours():
    """Every gap between consecutive slots, including the overnight wrap, must exceed 300 minutes.

    A ping that lands inside a still-open window is a no-op — the plan's
    entire mechanism depends on every gap clearing the 5h floor, every day.
    """
    for anchor in [0, 1, 300, 359, 719, 1000, 1439]:
        slots = sorted(slot_minutes_from_anchor(anchor))
        gaps = [b - a for a, b in zip(slots, slots[1:])]
        gaps.append(1440 - slots[-1] + slots[0])  # overnight wrap
        assert sum(gaps) == 1440
        for gap in gaps:
            assert gap > 300, f"anchor={anchor} produced a gap of {gap}min, at or under the 5h floor"


def test_ping_interval_strictly_exceeds_the_window_length():
    """A reset at exactly the window length would land as the window expires, which risks a
    no-op ping (the previous window may still be open). The plan calls for strictly more
    than 5h; assert that against the real constants, not against a literal."""
    assert PING_INTERVAL_MINUTES > WINDOW_MINUTES
    # ...and that the overnight segment, the only gap not equal to the interval, clears it too.
    assert segment_lengths()[-1] > WINDOW_MINUTES


def test_slot_count_is_always_four():
    for anchor in [0, 600, 1439]:
        assert len(slot_minutes_from_anchor(anchor)) == 4


# ---- UTC conversion ----


def test_local_to_utc_positive_offset():
    # 6:00 local, UTC+2 -> 4:00 UTC
    assert local_minutes_to_utc(6 * 60, timedelta(hours=2)) == 4 * 60


def test_local_to_utc_negative_offset_wraps():
    # 1:00 local, UTC-5 -> 6:00 UTC (no wrap needed) and check a case that does wrap
    assert local_minutes_to_utc(1 * 60, timedelta(hours=-5)) == 6 * 60
    # 22:00 local, UTC+3 -> 19:00 UTC... use a case that wraps past midnight instead
    assert local_minutes_to_utc(1 * 60, timedelta(hours=5)) == (1 * 60 - 5 * 60) % 1440


def test_cron_for_minute_of_day():
    assert cron_for_minute_of_day(6 * 60 + 5) == "5 6 * * *"
    assert cron_for_minute_of_day(0) == "0 0 * * *"


def test_build_schedule_shape():
    slots = build_schedule(6 * 60, timedelta(hours=2))
    assert len(slots) == 4
    assert slots[0]["local_hhmm"] == "06:00"
    assert slots[0]["utc_hhmm"] == "04:00"
    assert slots[0]["cron_expression"] == "0 4 * * *"


# ---- parse_hhmm ----


def test_parse_hhmm_valid():
    assert parse_hhmm("06:05") == 6 * 60 + 5
    assert parse_hhmm("23:59") == 23 * 60 + 59
    assert parse_hhmm("0:0") == 0


def test_parse_hhmm_rejects_bad_input():
    import pytest

    for bad in ["25:00", "12:60", "not-a-time", "12", "12:00:00"]:
        with pytest.raises(ValueError):
            parse_hhmm(bad)


# ---- Log parsing ----


def test_parse_log_timestamps_skips_malformed_lines(tmp_path):
    log = tmp_path / "prompts.log"
    log.write_text("2026-08-01T06:15:00+02:00\nnot-a-timestamp\n\n2026-08-02T06:20:00+02:00\n")
    timestamps = parse_log_timestamps(str(log))
    assert len(timestamps) == 2


def test_parse_log_timestamps_missing_file_returns_empty():
    assert parse_log_timestamps("/nonexistent/path/prompts.log") == []


def test_first_prompt_per_day_takes_earliest():
    tz = timezone(timedelta(hours=2))
    a = datetime(2026, 8, 1, 6, 30, tzinfo=tz)
    b = datetime(2026, 8, 1, 9, 0, tzinfo=tz)  # same day, later
    c = datetime(2026, 8, 2, 6, 45, tzinfo=tz)
    result = first_prompt_per_day([b, a, c])
    assert sorted(t.hour * 60 + t.minute for t in result) == [6 * 60 + 30, 6 * 60 + 45]


# ---- Weighted anchor computation ----


def test_logged_days_in_window_counts_distinct_days_not_lines():
    tz = timezone.utc
    now = datetime(2026, 8, 10, 12, 0, tzinfo=tz)
    timestamps = [
        datetime(2026, 8, 1, 6, 0, tzinfo=tz),
        datetime(2026, 8, 1, 14, 0, tzinfo=tz),  # same day as above
        datetime(2026, 8, 2, 6, 0, tzinfo=tz),
    ]
    assert logged_days_in_window(timestamps, now) == 2


def test_logged_days_in_window_excludes_data_outside_trailing_window():
    tz = timezone.utc
    now = datetime(2026, 8, 10, 12, 0, tzinfo=tz)
    timestamps = [datetime(2026, 1, 1, 6, 0, tzinfo=tz)]
    assert logged_days_in_window(timestamps, now) == 0


# ---- Balanced-anchor estimator ----


def _prompts(spec, base=None):
    """spec: [(days_ago, [(h, m), ...]), ...] -> flat timestamp list."""
    base = base or datetime(2026, 8, 10, tzinfo=timezone.utc)
    return [base - timedelta(days=d) + timedelta(hours=h, minutes=m) for d, mins in spec for (h, m) in mins]


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def test_segment_lengths_partition_the_whole_day():
    lengths = segment_lengths()
    assert len(lengths) == 4
    assert sum(lengths) == 1440
    assert lengths[:3] == [310, 310, 310]
    assert lengths[3] == 510


def test_usage_histogram_counts_every_prompt_not_one_per_day():
    ts = _prompts([(1, [(9, 0), (9, 30), (10, 0)]), (2, [(9, 0)])])
    counts = usage_histogram(ts, NOW)
    assert sum(counts) == 4  # not 2 — every prompt counts, not one per day
    assert counts[9 * 60] == 2


def test_usage_histogram_excludes_data_outside_trailing_window():
    ts = _prompts([(200, [(9, 0), (9, 30)])])
    assert sum(usage_histogram(ts, NOW)) == 0


def test_segment_loads_account_for_every_prompt():
    """Segments partition the day, so nothing can hide between them."""
    ts = _prompts([(d, [(h, 0) for h in range(0, 24)]) for d in range(1, 4)])
    counts = usage_histogram(ts, NOW)
    for anchor in (0, 137, 800, 1439):
        assert sum(segment_loads(counts, anchor)) == sum(counts)


def test_balanced_anchor_none_without_data():
    assert compute_balanced_anchor([], NOW) is None


def test_balanced_anchor_splits_a_long_working_block():
    """The whole point: a reset should land inside a heavy block so it doesn't ride on one budget."""
    block = [(9, 0), (9, 30), (10, 0), (10, 30), (11, 0), (11, 30), (12, 0), (12, 30)]
    ts = _prompts([(d, block) for d in range(1, 21)])
    anchor = compute_balanced_anchor(ts, NOW)
    loads = segment_loads(usage_histogram(ts, NOW), anchor)
    # 160 prompts total; leaving them on one budget would peak at 160
    assert sum(loads) == 160
    assert max(loads) <= 80


def test_balanced_anchor_never_hides_usage_in_uncovered_gaps():
    """Regression: an earlier objective scored 'usage in the gaps' as free, so the
    best-scoring schedule for a night owl was all-zero load — i.e. every prompt
    landing when no window was open. Segments partition the day precisely so that
    degenerate optimum is unrepresentable."""
    ts = _prompts([(d, [(22, 0), (22, 30), (23, 0), (23, 30), (0, 30)]) for d in range(1, 21)])
    anchor = compute_balanced_anchor(ts, NOW)
    counts = usage_histogram(ts, NOW)
    loads = segment_loads(counts, anchor)
    assert sum(loads) == 100
    # `max(loads) > 0` cannot fail — segments partition the day, so any non-empty
    # histogram always lands somewhere. Assert the thing that actually distinguishes
    # this objective from the rejected gap-based one: most of the usage must sit
    # inside a *covered* window, not in the uncovered tail of a segment.
    covered = 0
    for i, start in enumerate(slot_minutes_from_anchor(anchor)):
        covered += sum(counts[(start + k) % 1440] for k in range(WINDOW_MINUTES))
    assert covered >= 0.75 * sum(loads), f"only {covered}/{sum(loads)} prompts fall inside an open window"


def test_balanced_anchor_is_robust_to_stray_early_prompts():
    """The old first-prompt-per-day mean moved 71 minutes on 3 outliers; this must barely move."""
    clean = [(d, [(9, 0), (9, 30), (10, 0), (10, 30), (11, 0), (11, 30), (12, 0), (12, 30)]) for d in range(1, 21)]
    noisy = [(d, ([(6, 0)] if d in (3, 8, 14) else []) + mins) for d, mins in clean]
    a_clean = compute_balanced_anchor(_prompts(clean), NOW)
    a_noisy = compute_balanced_anchor(_prompts(noisy), NOW)
    drift = min((a_clean - a_noisy) % 1440, (a_noisy - a_clean) % 1440)
    assert drift <= 15


def test_balanced_anchor_ignores_input_ordering():
    """Same usage, different log ordering, same answer. Calling a pure function twice proves
    nothing; shuffling the input actually exercises that no ordering assumption crept in."""
    ts = _prompts([(d, [(9, 0), (14, 0), (19, 0)]) for d in range(1, 15)])
    shuffled = list(reversed(ts))
    assert compute_balanced_anchor(shuffled, NOW) == compute_balanced_anchor(ts, NOW)


def test_balanced_anchor_beats_or_matches_every_other_phase_on_peak_load():
    """It's an optimiser — verify it actually returns an optimum, not just a plausible number."""
    ts = _prompts([(d, [(8, 0), (9, 0), (10, 0), (15, 0), (21, 0)]) for d in range(1, 11)])
    counts = usage_histogram(ts, NOW)
    best = compute_balanced_anchor(ts, NOW)
    best_peak = max(segment_loads(counts, best))
    for phi in range(0, 1440, 7):
        assert max(segment_loads(counts, phi)) >= best_peak


# ---- The brute-force ADR-0007 cites (previously run ad hoc and never committed) ----

BRUTE_FORCE_PROFILES = {
    "heavy morning block": [(9, 0), (9, 30), (10, 0), (10, 30), (11, 0), (11, 30), (12, 0), (12, 30)],
    "two sessions": [(9, 0), (9, 30), (10, 0), (20, 0), (20, 30), (21, 0)],
    "night owl": [(22, 0), (22, 30), (23, 0), (23, 30), (0, 30)],
    "flat working day": [(h, 0) for h in range(8, 21)],
    "lumpy bursts": [(7, 0), (7, 5), (7, 10), (13, 0), (13, 5), (18, 0), (23, 0)],
    "dense office hours": [(h, m) for h in range(9, 17) for m in (0, 20, 40)],
    "single daily check": [(9, 0)],
}


@pytest.mark.parametrize("name,pattern", sorted(BRUTE_FORCE_PROFILES.items()))
def test_returned_anchor_is_optimal_over_all_1440_phases(name, pattern):
    """ADR-0007 claimed this was 'brute-forced against all 1440 phases across seven usage
    profiles'. That run happened, but only in a throwaway script that was never committed —
    the same failure as the stability table it sat next to. Committed here so the claim is
    checkable, and so it fails if the optimiser ever stops returning a true optimum."""
    ts = _prompts([(d, pattern) for d in range(1, 21)])
    counts = usage_histogram(ts, NOW)
    chosen = compute_balanced_anchor(ts, NOW)
    chosen_peak = max(segment_loads(counts, chosen))
    true_best = min(max(segment_loads(counts, phi)) for phi in range(1440))
    assert chosen_peak == true_best, f"{name}: returned peak {chosen_peak}, optimum is {true_best}"


@pytest.mark.parametrize("name,pattern", sorted(BRUTE_FORCE_PROFILES.items()))
def test_every_prompt_is_owned_at_every_phase(name, pattern):
    ts = _prompts([(d, pattern) for d in range(1, 21)])
    counts = usage_histogram(ts, NOW)
    for phi in (0, 1, 137, 313, 929, 1439):
        assert sum(segment_loads(counts, phi)) == sum(counts), f"{name}: phase {phi} loses prompts"
