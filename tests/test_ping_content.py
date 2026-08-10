import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import pytest
from window_optimizer.ping_content import (
    PING_KIND_GITHUB_ISSUES,
    PING_KIND_SIMPLE,
    allowed_tools_for_kind,
    github_issues_prompt,
    prompt_for_kind,
    simple_ping_prompt,
)


def test_simple_ping_prompt_self_identifies_as_automated():
    prompt = simple_ping_prompt()
    assert "automated" in prompt.lower()
    assert "claude-window-optimizer" in prompt


def test_simple_ping_prompt_needs_no_tools():
    assert allowed_tools_for_kind(PING_KIND_SIMPLE) == []


def test_github_issues_prompt_uses_public_unauthenticated_api():
    prompt = github_issues_prompt("owner/repo")
    assert "api.github.com/repos/owner/repo/issues" in prompt
    assert "state=open" in prompt
    # never a private-repo-only endpoint or anything implying auth is available
    assert "token" not in prompt.lower()
    assert "gh auth" not in prompt.lower()


def test_github_issues_prompt_grants_only_webfetch():
    assert allowed_tools_for_kind(PING_KIND_GITHUB_ISSUES) == ["WebFetch"]


def test_github_issues_prompt_requires_repo():
    with pytest.raises(ValueError):
        prompt_for_kind(PING_KIND_GITHUB_ISSUES, repo=None)


def test_prompt_for_kind_dispatches_correctly():
    assert prompt_for_kind(PING_KIND_SIMPLE) == simple_ping_prompt()
    assert prompt_for_kind(PING_KIND_GITHUB_ISSUES, repo="a/b") == github_issues_prompt("a/b")


def test_prompt_for_kind_rejects_unknown_kind():
    with pytest.raises(ValueError):
        prompt_for_kind("not-a-real-kind")
