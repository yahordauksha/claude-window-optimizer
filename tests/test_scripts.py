import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPUTE_SCHEDULE = REPO_ROOT / "scripts" / "compute_schedule.py"
TUNE_SCHEDULE = REPO_ROOT / "scripts" / "tune_schedule.py"
BUILD_PING_PROMPT = REPO_ROOT / "scripts" / "build_ping_prompt.py"


def _run(script, args, data_dir):
    import os

    env = dict(os.environ)
    env["WINDOW_OPTIMIZER_DATA_DIR"] = str(data_dir)
    return subprocess.run([sys.executable, str(script)] + args, capture_output=True, text=True, env=env, timeout=10)


# ---- compute_schedule.py ----


def test_compute_schedule_with_explicit_anchor(tmp_path):
    result = _run(COMPUTE_SCHEDULE, ["--anchor", "06:00"], tmp_path)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["anchor_local_hhmm"] == "06:00"
    assert len(data["slots"]) == 4


def test_compute_schedule_rejects_invalid_anchor(tmp_path):
    result = _run(COMPUTE_SCHEDULE, ["--anchor", "not-a-time"], tmp_path)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"] == "invalid_anchor"


def test_compute_schedule_requires_an_anchor(tmp_path):
    result = _run(COMPUTE_SCHEDULE, [], tmp_path)
    assert result.returncode != 0  # argparse rejects: --anchor is required


def test_compute_schedule_never_reads_the_log(tmp_path):
    """Setup always asks; it must not quietly anchor off log noise even when a log exists.

    Regression test for the real bug this replaced: a fresh install's log is dominated by
    the act of installing and poking at the plugin, so a computed anchor there was just
    "roughly now" dressed up as a real pattern. A log full of 07:00 entries must have no
    effect on an explicitly-passed 06:00 anchor.
    """
    now = datetime.now(timezone.utc).astimezone()
    log_lines = "\n".join(
        (now - timedelta(days=d)).replace(hour=7, minute=0, second=0, microsecond=0).isoformat() for d in range(0, 6)
    )
    (tmp_path / "prompts.log").write_text(log_lines + "\n")
    result = _run(COMPUTE_SCHEDULE, ["--anchor", "06:00"], tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout)["anchor_local_hhmm"] == "06:00"


def test_compute_schedule_rejects_from_log_flag(tmp_path):
    """--from-log is gone on purpose (ADR-0004) — it must fail loudly, not silently no-op."""
    result = _run(COMPUTE_SCHEDULE, ["--from-log"], tmp_path)
    assert result.returncode != 0


# ---- tune_schedule.py ----


def test_tune_schedule_not_set_up(tmp_path):
    result = _run(TUNE_SCHEDULE, [], tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"error": "not_set_up"}


def test_tune_schedule_no_log_data(tmp_path):
    routines_state = {
        "installed_at": "2026-07-01T06:00:00+00:00",
        "anchor_local_hhmm": "06:00",
        "routines": [
            {"slot": i, "trigger_id": f"trig_{i}", "local_hhmm": "x", "utc_hhmm": "x", "cron_expression": "x"}
            for i in range(4)
        ],
    }
    (tmp_path / "routines.json").write_text(json.dumps(routines_state))
    result = _run(TUNE_SCHEDULE, [], tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"error": "no_log_data"}


def _installed_routines_state():
    return {
        "installed_at": "2026-07-01T06:00:00+00:00",
        "anchor_local_hhmm": "06:00",
        "routines": [
            {"slot": i, "trigger_id": f"trig_{i}", "local_hhmm": "x", "utc_hhmm": "x", "cron_expression": "x"}
            for i in range(4)
        ],
    }


def test_tune_schedule_with_one_day_of_data_is_insufficient(tmp_path):
    """Re-anchoring off a single day would swing the whole schedule on noise."""
    (tmp_path / "routines.json").write_text(json.dumps(_installed_routines_state()))
    now = datetime.now(timezone.utc).astimezone()
    (tmp_path / "prompts.log").write_text(now.isoformat() + "\n")
    result = _run(TUNE_SCHEDULE, [], tmp_path)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["error"] == "insufficient_log_data"
    assert data["logged_days"] == 1
    assert data["needed_days"] == 3


def test_tune_schedule_with_two_days_is_still_insufficient(tmp_path):
    (tmp_path / "routines.json").write_text(json.dumps(_installed_routines_state()))
    now = datetime.now(timezone.utc).astimezone()
    log_lines = "\n".join(
        (now - timedelta(days=d)).replace(hour=7, minute=0, second=0, microsecond=0).isoformat() for d in range(0, 2)
    )
    (tmp_path / "prompts.log").write_text(log_lines + "\n")
    result = _run(TUNE_SCHEDULE, [], tmp_path)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["error"] == "insufficient_log_data"
    assert data["logged_days"] == 2


def test_tune_schedule_with_exactly_three_days_re_anchors(tmp_path):
    (tmp_path / "routines.json").write_text(json.dumps(_installed_routines_state()))
    now = datetime.now(timezone.utc).astimezone()
    log_lines = "\n".join(
        (now - timedelta(days=d)).replace(hour=7, minute=0, second=0, microsecond=0).isoformat() for d in range(0, 3)
    )
    (tmp_path / "prompts.log").write_text(log_lines + "\n")
    result = _run(TUNE_SCHEDULE, [], tmp_path)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "error" not in data
    assert re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", data["new_anchor_local_hhmm"])


def test_tune_schedule_produces_diff_preserving_trigger_ids_and_content_kind(tmp_path):
    routines_state = {
        "installed_at": "2026-07-01T06:00:00+00:00",
        "anchor_local_hhmm": "06:45",
        "routines": [
            {
                "slot": i,
                "trigger_id": f"trig_{i}",
                "local_hhmm": "x",
                "utc_hhmm": "x",
                "cron_expression": f"45 {(6 + i * 5) % 24} * * *",
                # slot 1 has real content-kind state; the rest simulate an
                # install from before this field existed (no key at all).
                **({"kind": "github-issues", "repo": "owner/repo"} if i == 1 else {}),
            }
            for i in range(4)
        ],
    }
    (tmp_path / "routines.json").write_text(json.dumps(routines_state))

    now = datetime.now(timezone.utc).astimezone()
    log_lines = "\n".join(
        (now - timedelta(days=d)).replace(hour=6, minute=0, second=0, microsecond=0).isoformat() for d in range(1, 8)
    )
    (tmp_path / "prompts.log").write_text(log_lines + "\n")

    result = _run(TUNE_SCHEDULE, [], tmp_path)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["old_anchor_local_hhmm"] == "06:45"
    # The anchor is a load-balancing phase, not "when you start work" — assert it
    # was recomputed and is a valid time, not a specific clock value tied to the
    # estimator's internals.
    assert re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", data["new_anchor_local_hhmm"])
    assert data["logged_days"] == 7
    assert len(data["slots"]) == 4
    for i, slot in enumerate(data["slots"]):
        assert slot["trigger_id"] == f"trig_{i}"
        assert slot["slot"] == i
        assert "old_cron_expression" in slot
        assert "new_cron_expression" in slot
    assert data["slots"][1]["kind"] == "github-issues"
    assert data["slots"][1]["repo"] == "owner/repo"
    # a slot with no prior kind/repo key defaults to a plain keep-alive, never crashes
    assert data["slots"][0]["kind"] == "simple"
    assert data["slots"][0]["repo"] is None


# ---- build_ping_prompt.py ----


def test_build_ping_prompt_simple(tmp_path):
    result = _run(BUILD_PING_PROMPT, ["--kind", "simple"], tmp_path)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["allowed_tools"] == []
    assert "automated" in data["prompt"].lower()


def test_build_ping_prompt_github_issues(tmp_path):
    result = _run(BUILD_PING_PROMPT, ["--kind", "github-issues", "--repo", "owner/repo"], tmp_path)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["allowed_tools"] == ["WebFetch"]
    assert "owner/repo" in data["prompt"]


def test_build_ping_prompt_github_issues_without_repo_fails(tmp_path):
    result = _run(BUILD_PING_PROMPT, ["--kind", "github-issues"], tmp_path)
    assert result.returncode == 1
    assert "error" in json.loads(result.stdout)


def test_build_ping_prompt_rejects_unknown_kind(tmp_path):
    result = _run(BUILD_PING_PROMPT, ["--kind", "not-a-kind"], tmp_path)
    assert result.returncode != 0  # argparse choices validation rejects it
