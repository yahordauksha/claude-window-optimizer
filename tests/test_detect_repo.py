import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import detect_repo  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DETECT_REPO_SCRIPT = REPO_ROOT / "scripts" / "detect_repo.py"


def _init_git_repo_with_remote(path, remote_url=None):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    if remote_url:
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=path, check=True)


# ---- detect_from_cwd_git_remote (real git, no network) ----


def test_detect_from_cwd_git_remote_reads_real_origin(tmp_path, monkeypatch):
    _init_git_repo_with_remote(tmp_path, "https://github.com/owner/name.git")
    monkeypatch.chdir(tmp_path)
    assert detect_repo.detect_from_cwd_git_remote() == "owner/name"


def test_detect_from_cwd_git_remote_no_remote(tmp_path, monkeypatch):
    _init_git_repo_with_remote(tmp_path, remote_url=None)
    monkeypatch.chdir(tmp_path)
    assert detect_repo.detect_from_cwd_git_remote() is None


def test_detect_from_cwd_git_remote_not_a_git_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert detect_repo.detect_from_cwd_git_remote() is None


def test_detect_from_cwd_git_remote_non_github_remote(tmp_path, monkeypatch):
    _init_git_repo_with_remote(tmp_path, "https://gitlab.com/owner/name.git")
    monkeypatch.chdir(tmp_path)
    assert detect_repo.detect_from_cwd_git_remote() is None


# ---- is_public_repo / detect_from_gh_recent_repos (mocked _run — no real gh/network) ----


def test_is_public_repo_true(monkeypatch):
    monkeypatch.setattr(detect_repo, "_run", lambda cmd: json.dumps({"isPrivate": False}))
    assert detect_repo.is_public_repo("owner/name") is True


def test_is_public_repo_false(monkeypatch):
    monkeypatch.setattr(detect_repo, "_run", lambda cmd: json.dumps({"isPrivate": True}))
    assert detect_repo.is_public_repo("owner/name") is False


def test_is_public_repo_gh_unavailable_defaults_to_not_public(monkeypatch):
    monkeypatch.setattr(detect_repo, "_run", lambda cmd: None)
    assert detect_repo.is_public_repo("owner/name") is False


def test_detect_from_gh_recent_repos_filters_private_and_sorts_by_recency(monkeypatch):
    repos = [
        {"nameWithOwner": "owner/old-public", "pushedAt": "2026-01-01T00:00:00Z", "isPrivate": False},
        {"nameWithOwner": "owner/private-but-recent", "pushedAt": "2026-08-01T00:00:00Z", "isPrivate": True},
        {"nameWithOwner": "owner/recent-public", "pushedAt": "2026-07-01T00:00:00Z", "isPrivate": False},
    ]
    monkeypatch.setattr(detect_repo, "_run", lambda cmd: json.dumps(repos))
    assert detect_repo.detect_from_gh_recent_repos() == "owner/recent-public"


def test_detect_from_gh_recent_repos_no_public_repos(monkeypatch):
    repos = [{"nameWithOwner": "owner/private", "pushedAt": "2026-01-01T00:00:00Z", "isPrivate": True}]
    monkeypatch.setattr(detect_repo, "_run", lambda cmd: json.dumps(repos))
    assert detect_repo.detect_from_gh_recent_repos() is None


def test_detect_from_gh_recent_repos_gh_unavailable(monkeypatch):
    monkeypatch.setattr(detect_repo, "_run", lambda cmd: None)
    assert detect_repo.detect_from_gh_recent_repos() is None


# ---- end-to-end: running the actual script from inside this real repo ----


def test_main_detects_this_repos_own_real_remote():
    result = subprocess.run(
        [sys.executable, str(DETECT_REPO_SCRIPT)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    # This repo's own real origin — the strongest possible regression check
    # that the cwd-git-remote path and the public-repo confirmation both work.
    assert data["repo"] == "yahordauksha/claude-window-optimizer"


# ---- Ownership trust boundary (see ADR-0008) ----


def test_is_owned_by_rejects_someone_elses_repo():
    assert detect_repo.is_owned_by("facebook/react", "yahordauksha") is False


def test_is_owned_by_accepts_own_repo_case_insensitively():
    assert detect_repo.is_owned_by("yahordauksha/thing", "yahordauksha") is True
    assert detect_repo.is_owned_by("YahorDauksha/thing", "yahordauksha") is True


def test_is_owned_by_rejects_missing_inputs():
    assert detect_repo.is_owned_by(None, "someone") is False
    assert detect_repo.is_owned_by("a/b", None) is False


def test_main_refuses_a_foreign_cwd_repo(tmp_path, monkeypatch, capsys):
    """The reviewer's finding: running setup inside a clone of someone else's project
    wired four unattended daily agents to that project's issue titles — text any
    stranger can write. It must not be selectable, whatever the cwd says."""
    _init_git_repo_with_remote(tmp_path, "https://github.com/facebook/react.git")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(detect_repo, "authenticated_login", lambda: "yahordauksha")
    monkeypatch.setattr(detect_repo, "detect_from_gh_recent_repos", lambda: None)
    detect_repo.main()
    assert json.loads(capsys.readouterr().out)["repo"] is None


def test_main_accepts_an_owned_cwd_repo(tmp_path, monkeypatch, capsys):
    _init_git_repo_with_remote(tmp_path, "https://github.com/yahordauksha/mine.git")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(detect_repo, "authenticated_login", lambda: "yahordauksha")
    monkeypatch.setattr(detect_repo, "is_public_repo", lambda repo: True)
    detect_repo.main()
    assert json.loads(capsys.readouterr().out)["repo"] == "yahordauksha/mine"


def test_main_falls_back_to_keepalive_when_not_authenticated(tmp_path, monkeypatch, capsys):
    """No identity means no way to establish ownership — refuse rather than guess."""
    _init_git_repo_with_remote(tmp_path, "https://github.com/yahordauksha/mine.git")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(detect_repo, "authenticated_login", lambda: None)
    detect_repo.main()
    out = json.loads(capsys.readouterr().out)
    assert out["repo"] is None
    assert out["reason"] == "not_authenticated"


def test_main_rejects_a_foreign_repo_from_the_gh_fallback(tmp_path, monkeypatch, capsys):
    """`gh repo list` returns only your own repos today; don't depend on that staying true."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(detect_repo, "authenticated_login", lambda: "yahordauksha")
    monkeypatch.setattr(detect_repo, "detect_from_cwd_git_remote", lambda: None)
    monkeypatch.setattr(detect_repo, "detect_from_gh_recent_repos", lambda: "someone-else/repo")
    detect_repo.main()
    assert json.loads(capsys.readouterr().out)["repo"] is None
