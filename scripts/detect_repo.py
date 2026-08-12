#!/usr/bin/env python3
"""CLI: best-effort auto-detect a public GitHub repo for the useful-ping check.

Used by /setup-window-optimizer so it doesn't have to ask which repo to
use. Tries the current project's own git remote first (the strongest
signal available: "this is what's open right now"), falls back to the
account's most recently pushed-to public repo via `gh`. Never prompts;
if nothing is found, the caller falls back to plain keep-alive pings.

A repo found via the cwd git remote is confirmed public via a `gh repo
view` call before being trusted — a private repo would just silently
fail the public, unauthenticated GitHub API call the ping itself makes
(see ADR-0002), so this is checked here rather than discovered at
ping-time. `gh repo list`'s own results are already filtered by
`isPrivate`, so no extra check is needed for that path.

Prints one JSON object: {"repo": "owner/name"} or {"repo": null}
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from window_optimizer.repo_detect import parse_github_remote  # noqa: E402


def _run(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def detect_from_cwd_git_remote():
    url = _run(["git", "remote", "get-url", "origin"])
    return parse_github_remote(url) if url else None


def authenticated_login():
    """The GitHub account this machine is logged in as, or None if not authenticated."""
    output = _run(["gh", "api", "user", "--jq", ".login"])
    return output or None


def is_owned_by(repo, login):
    """True only if `repo` is 'login/something' (case-insensitive).

    This is a trust boundary, not a nicety. The ping prompt asks an unattended
    cloud agent to fetch a repo's open issue *titles* — text any stranger can
    write by opening an issue. Auto-detection reads whatever `git remote origin`
    says in whatever directory setup happened to run in, so without this check,
    running setup inside a clone of someone else's project wires four daily
    agents to attacker-authored text. Restricting to repos you own keeps
    ADR-0003's no-questions UX while removing the arbitrary-internet-text path.
    """
    if not repo or not login:
        return False
    return repo.split("/", 1)[0].lower() == login.lower()


def is_public_repo(repo):
    output = _run(["gh", "repo", "view", repo, "--json", "isPrivate"])
    if not output:
        return False  # can't confirm -> don't use it
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return False
    return not data.get("isPrivate", True)


def detect_from_gh_recent_repos():
    output = _run(["gh", "repo", "list", "--limit", "20", "--json", "nameWithOwner,pushedAt,isPrivate"])
    if not output:
        return None
    try:
        repos = json.loads(output)
    except json.JSONDecodeError:
        return None
    public_repos = [r for r in repos if not r.get("isPrivate")]
    if not public_repos:
        return None
    public_repos.sort(key=lambda r: r.get("pushedAt") or "", reverse=True)
    return public_repos[0]["nameWithOwner"]


def main():
    login = authenticated_login()
    if not login:
        # Can't establish who we are, so can't establish that any repo is ours.
        # Fall back to a plain keep-alive rather than trusting an unowned repo.
        print(json.dumps({"repo": None, "reason": "not_authenticated"}))
        return

    repo = detect_from_cwd_git_remote()
    if repo and not is_owned_by(repo, login):
        # The current directory is someone else's project. Don't wire a daily
        # unattended agent to its issue tracker just because we're standing in it.
        repo = None
    if repo and not is_public_repo(repo):
        repo = None
    if not repo:
        # `gh repo list` with no argument returns only the authenticated user's
        # own repos, so this path is owned by construction — but re-check anyway
        # rather than relying on that behaviour staying true.
        candidate = detect_from_gh_recent_repos()
        repo = candidate if is_owned_by(candidate, login) else None
    print(json.dumps({"repo": repo}))


if __name__ == "__main__":
    main()
