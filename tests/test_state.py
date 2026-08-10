import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import window_optimizer.paths as paths
import window_optimizer.state as state


def _repoint(monkeypatch, tmp_path):
    data_dir = tmp_path / "window-optimizer"
    monkeypatch.setattr(paths, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(paths, "ROUTINES_STATE_PATH", str(data_dir / "routines.json"))
    monkeypatch.setattr(paths, "TUNE_STATE_PATH", str(data_dir / "tune-state.json"))
    monkeypatch.setattr(paths, "REMINDER_STATE_PATH", str(data_dir / "reminder-state.json"))
    monkeypatch.setattr(state, "ROUTINES_STATE_PATH", str(data_dir / "routines.json"))
    monkeypatch.setattr(state, "TUNE_STATE_PATH", str(data_dir / "tune-state.json"))
    monkeypatch.setattr(state, "REMINDER_STATE_PATH", str(data_dir / "reminder-state.json"))


def test_routines_state_roundtrip(monkeypatch, tmp_path):
    _repoint(monkeypatch, tmp_path)
    assert state.read_routines_state() is None
    routines = [{"slot": 0, "trigger_id": "trig_abc", "local_hhmm": "06:00", "utc_hhmm": "04:00"}]
    state.write_routines_state("2026-08-10T12:00:00+02:00", "06:00", routines)
    result = state.read_routines_state()
    assert result["installed_at"] == "2026-08-10T12:00:00+02:00"
    assert result["anchor_local_hhmm"] == "06:00"
    assert result["routines"] == routines


def test_tune_state_roundtrip(monkeypatch, tmp_path):
    _repoint(monkeypatch, tmp_path)
    assert state.read_tune_state() is None
    state.write_tune_state("2026-08-10T12:00:00+02:00")
    assert state.read_tune_state()["last_tune_up"] == "2026-08-10T12:00:00+02:00"


def test_reminder_state_roundtrip(monkeypatch, tmp_path):
    _repoint(monkeypatch, tmp_path)
    assert state.read_reminder_state() is None
    state.write_reminder_state("2026-08-10")
    assert state.read_reminder_state()["last_shown_date"] == "2026-08-10"


def test_corrupted_json_is_treated_as_absent(monkeypatch, tmp_path):
    _repoint(monkeypatch, tmp_path)
    data_dir = tmp_path / "window-optimizer"
    data_dir.mkdir(parents=True)
    (data_dir / "tune-state.json").write_text("{not valid json")
    assert state.read_tune_state() is None
