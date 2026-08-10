import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PROMPT_HOOK = REPO_ROOT / "hooks" / "log_prompt.py"
REMINDER_HOOK = REPO_ROOT / "hooks" / "session_start_reminder.py"


def _run_hook(hook_path, stdin_obj, data_dir):
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(REPO_ROOT)
    env["WINDOW_OPTIMIZER_DATA_DIR"] = str(data_dir)
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(stdin_obj),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return result


# ---- log_prompt.py (UserPromptSubmit) ----


def test_log_prompt_exits_zero_and_emits_valid_json(tmp_path):
    result = _run_hook(LOG_PROMPT_HOOK, {"hook_event_name": "UserPromptSubmit", "prompt_text": "hello world"}, tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}


def test_log_prompt_appends_a_timestamp_line(tmp_path):
    _run_hook(LOG_PROMPT_HOOK, {"hook_event_name": "UserPromptSubmit", "prompt_text": "first"}, tmp_path)
    _run_hook(LOG_PROMPT_HOOK, {"hook_event_name": "UserPromptSubmit", "prompt_text": "second"}, tmp_path)
    log_file = tmp_path / "prompts.log"
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        datetime.fromisoformat(line)  # must parse as a valid timestamp


def test_log_prompt_never_logs_prompt_content(tmp_path):
    secret_prompt = "this text must never appear in the log file"
    _run_hook(LOG_PROMPT_HOOK, {"hook_event_name": "UserPromptSubmit", "prompt_text": secret_prompt}, tmp_path)
    log_file = tmp_path / "prompts.log"
    assert secret_prompt not in log_file.read_text()


def test_log_prompt_malformed_stdin_still_exits_zero_with_valid_json(tmp_path):
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(REPO_ROOT)
    env["WINDOW_OPTIMIZER_DATA_DIR"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, str(LOG_PROMPT_HOOK)],
        input="not valid json{{{",
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}


# ---- session_start_reminder.py (SessionStart) ----


def test_reminder_says_nothing_when_never_set_up(tmp_path):
    result = _run_hook(REMINDER_HOOK, {"hook_event_name": "SessionStart", "source": "startup"}, tmp_path)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}


def test_reminder_fires_after_seven_days_since_install_with_no_tune_up(tmp_path):
    installed_at = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    (tmp_path / "routines.json").write_text(json.dumps({"installed_at": installed_at, "routines": []}))

    result = _run_hook(REMINDER_HOOK, {"hook_event_name": "SessionStart", "source": "startup"}, tmp_path)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "hookSpecificOutput" in output
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "10 days" in context
    assert "/tune-pings" in context


def test_reminder_stays_silent_under_threshold(tmp_path):
    installed_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    (tmp_path / "routines.json").write_text(json.dumps({"installed_at": installed_at, "routines": []}))

    result = _run_hook(REMINDER_HOOK, {"hook_event_name": "SessionStart", "source": "startup"}, tmp_path)
    assert json.loads(result.stdout) == {}


def test_reminder_rate_limited_to_once_per_day(tmp_path):
    installed_at = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
    (tmp_path / "routines.json").write_text(json.dumps({"installed_at": installed_at, "routines": []}))

    first = _run_hook(REMINDER_HOOK, {"hook_event_name": "SessionStart", "source": "startup"}, tmp_path)
    assert "hookSpecificOutput" in json.loads(first.stdout)

    second = _run_hook(REMINDER_HOOK, {"hook_event_name": "SessionStart", "source": "resume"}, tmp_path)
    assert json.loads(second.stdout) == {}


def test_reminder_prefers_tune_up_timestamp_over_install_timestamp(tmp_path):
    old_install = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    recent_tune = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    (tmp_path / "routines.json").write_text(json.dumps({"installed_at": old_install, "routines": []}))
    (tmp_path / "tune-state.json").write_text(json.dumps({"last_tune_up": recent_tune}))

    result = _run_hook(REMINDER_HOOK, {"hook_event_name": "SessionStart", "source": "startup"}, tmp_path)
    # recent tune-up (1 day ago) should win over the old install date (30 days ago) -> stays silent
    assert json.loads(result.stdout) == {}
