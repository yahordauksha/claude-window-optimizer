import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPUTE_SCHEDULE = REPO_ROOT / "scripts" / "compute_schedule.py"
TUNE_SCHEDULE = REPO_ROOT / "scripts" / "tune_schedule.py"


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


def test_compute_schedule_from_log_with_no_data(tmp_path):
    result = _run(COMPUTE_SCHEDULE, ["--from-log"], tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"error": "no_log_data"}


def test_compute_schedule_from_log_with_data(tmp_path):
    now = datetime.now(timezone.utc).astimezone()
    log_lines = "\n".join(
        (now - timedelta(days=d)).replace(hour=7, minute=0, second=0, microsecond=0).isoformat() for d in range(1, 6)
    )
    (tmp_path / "prompts.log").write_text(log_lines + "\n")
    result = _run(COMPUTE_SCHEDULE, ["--from-log"], tmp_path)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["anchor_local_hhmm"] == "07:00"


def test_compute_schedule_requires_exactly_one_mode(tmp_path):
    result = _run(COMPUTE_SCHEDULE, [], tmp_path)
    assert result.returncode != 0  # argparse rejects: neither --anchor nor --from-log given


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


def test_tune_schedule_produces_diff_preserving_trigger_ids(tmp_path):
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
    assert data["new_anchor_local_hhmm"] == "06:00"
    assert data["logged_days"] == 7
    assert len(data["slots"]) == 4
    for i, slot in enumerate(data["slots"]):
        assert slot["trigger_id"] == f"trig_{i}"
        assert slot["slot"] == i
        assert "old_cron_expression" in slot
        assert "new_cron_expression" in slot
