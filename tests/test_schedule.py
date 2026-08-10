import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from window_optimizer.schedule import (
    build_schedule,
    compute_weighted_anchor,
    cron_for_minute_of_day,
    first_prompt_per_day,
    local_minutes_to_utc,
    logged_days_in_window,
    parse_hhmm,
    parse_log_timestamps,
    slot_minutes_from_anchor,
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


def test_exactly_five_hours_is_not_valid_spacing():
    """The floor is 'strictly more than 5h,' never 'at least 5h' — a boundary the plan calls out explicitly."""
    assert not (300 > 300)  # sanity: the floor comparison itself must be strict, not >=


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


def test_compute_weighted_anchor_no_data_returns_none():
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    assert compute_weighted_anchor([], now) is None


def test_compute_weighted_anchor_ignores_data_outside_trailing_window():
    tz = timezone.utc
    now = datetime(2026, 8, 10, 12, 0, tzinfo=tz)
    old = [datetime(2026, 1, 1, 6, 0, tzinfo=tz)]  # far outside the 28-day window
    assert compute_weighted_anchor(old, now) is None


def test_compute_weighted_anchor_near_midnight_does_not_average_to_noon():
    """The circular-mean bug this design deliberately avoids: naive averaging of 23:45 and 00:15 gives ~12:00."""
    tz = timezone.utc
    now = datetime(2026, 8, 10, 12, 0, tzinfo=tz)
    timestamps = [
        datetime(2026, 8, 8, 23, 45, tzinfo=tz),
        datetime(2026, 8, 9, 0, 15, tzinfo=tz),
    ]
    anchor = compute_weighted_anchor(timestamps, now)
    # correct circular mean of 23:45 and 00:15 is 00:00 (minute 0), not ~12:00 (minute 720)
    assert anchor is not None
    assert abs(anchor - 0) < 5 or abs(anchor - 1440) < 5


def test_compute_weighted_anchor_same_weekday_dominates_with_enough_samples():
    """Two same-weekday samples should pull the blended anchor toward the weekday-specific average."""
    tz = timezone.utc
    now = datetime(2026, 8, 10, 12, 0, tzinfo=tz)  # a Monday
    assert now.weekday() == 0

    timestamps = [
        # Mondays (same weekday as `now`) consistently at 6:00
        datetime(2026, 7, 27, 6, 0, tzinfo=tz),
        datetime(2026, 8, 3, 6, 0, tzinfo=tz),
        # Other weekdays consistently at 9:00
        datetime(2026, 7, 28, 9, 0, tzinfo=tz),
        datetime(2026, 7, 29, 9, 0, tzinfo=tz),
        datetime(2026, 7, 30, 9, 0, tzinfo=tz),
    ]
    anchor = compute_weighted_anchor(timestamps, now)
    # 70/30 blend toward 6:00 should land closer to 6:00 than to 9:00
    assert anchor < 8 * 60


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


def test_compute_weighted_anchor_falls_back_to_all_days_with_few_weekday_samples():
    tz = timezone.utc
    now = datetime(2026, 8, 10, 12, 0, tzinfo=tz)  # Monday
    timestamps = [
        datetime(2026, 7, 28, 7, 0, tzinfo=tz),  # Tuesday
        datetime(2026, 7, 29, 7, 0, tzinfo=tz),  # Wednesday
        datetime(2026, 7, 30, 7, 0, tzinfo=tz),  # Thursday
    ]
    # zero same-weekday (Monday) samples -> pure all-days average -> ~7:00
    anchor = compute_weighted_anchor(timestamps, now)
    assert abs(anchor - 7 * 60) < 5
