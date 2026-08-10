"""Small JSON state files this plugin reads/writes locally. No secrets, no message content."""

import json
import os

from window_optimizer.paths import (
    REMINDER_STATE_PATH,
    ROUTINES_STATE_PATH,
    TUNE_STATE_PATH,
    ensure_data_dir,
)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_json(path, data):
    ensure_data_dir()
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)  # atomic on POSIX and Windows — no torn reads


def read_routines_state():
    """{'installed_at': iso8601, 'anchor_local_hhmm': 'HH:MM',
    'routines': [{'slot': 0, 'trigger_id': '...', 'local_hhmm': 'HH:MM', 'utc_hhmm': 'HH:MM',
    'cron_expression': '...'}, ...]} or None."""
    return _read_json(ROUTINES_STATE_PATH)


def write_routines_state(installed_at_iso, anchor_local_hhmm, routines):
    _write_json(
        ROUTINES_STATE_PATH,
        {"installed_at": installed_at_iso, "anchor_local_hhmm": anchor_local_hhmm, "routines": routines},
    )


def read_tune_state():
    """{'last_tune_up': iso8601} or None."""
    return _read_json(TUNE_STATE_PATH)


def write_tune_state(last_tune_up_iso):
    _write_json(TUNE_STATE_PATH, {"last_tune_up": last_tune_up_iso})


def read_reminder_state():
    """{'last_shown_date': 'YYYY-MM-DD'} or None."""
    return _read_json(REMINDER_STATE_PATH)


def write_reminder_state(last_shown_date_iso):
    _write_json(REMINDER_STATE_PATH, {"last_shown_date": last_shown_date_iso})
