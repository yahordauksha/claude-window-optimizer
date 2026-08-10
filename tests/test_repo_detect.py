import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from window_optimizer.repo_detect import parse_github_remote


def test_parses_https_url():
    assert parse_github_remote("https://github.com/owner/name.git") == "owner/name"
    assert parse_github_remote("https://github.com/owner/name") == "owner/name"


def test_parses_ssh_shorthand():
    assert parse_github_remote("git@github.com:owner/name.git") == "owner/name"
    assert parse_github_remote("git@github.com:owner/name") == "owner/name"


def test_parses_ssh_url_form():
    assert parse_github_remote("ssh://git@github.com/owner/name.git") == "owner/name"


def test_handles_trailing_slash():
    assert parse_github_remote("https://github.com/owner/name/") == "owner/name"


def test_non_github_url_returns_none():
    assert parse_github_remote("https://gitlab.com/owner/name.git") is None
    assert parse_github_remote("https://bitbucket.org/owner/name") is None


def test_empty_or_none_returns_none():
    assert parse_github_remote(None) is None
    assert parse_github_remote("") is None
    assert parse_github_remote("   ") is None


def test_malformed_url_returns_none():
    assert parse_github_remote("not a url at all") is None
    assert parse_github_remote("https://github.com/just-owner-no-repo") is None
