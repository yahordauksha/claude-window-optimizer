"""Filesystem locations for this plugin's local state.

Deliberately account/machine-scoped, not repo-scoped: the UserPromptSubmit
hook fires on every prompt regardless of which project is open, so the log
has to live somewhere that isn't tied to any one repo's working directory.
"""

import os

# Override lets tests (and hook subprocess tests specifically, which can't
# monkeypatch a module constant across a process boundary) point this at a
# tmp dir instead of the real machine-wide state. Absent in production.
DATA_DIR = os.environ.get("WINDOW_OPTIMIZER_DATA_DIR") or os.path.expanduser(
    os.path.join("~", ".claude", "window-optimizer")
)
LOG_PATH = os.path.join(DATA_DIR, "prompts.log")
ROUTINES_STATE_PATH = os.path.join(DATA_DIR, "routines.json")
TUNE_STATE_PATH = os.path.join(DATA_DIR, "tune-state.json")
REMINDER_STATE_PATH = os.path.join(DATA_DIR, "reminder-state.json")


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
