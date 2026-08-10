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
    repo = detect_from_cwd_git_remote()
    if repo and not is_public_repo(repo):
        repo = None
    if not repo:
        repo = detect_from_gh_recent_repos()
    print(json.dumps({"repo": repo}))


if __name__ == "__main__":
    main()
