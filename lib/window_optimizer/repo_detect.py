"""Parse a GitHub repo out of a git remote URL. Pure, no subprocess calls here.

See scripts/detect_repo.py for the actual detection flow (cwd's git
remote, falling back to the account's most recently pushed-to public
repo) — kept separate so the URL-format parsing is unit-testable without
mocking subprocesses.
"""

import re

_GITHUB_URL_PATTERNS = (
    re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s]+?)(\.git)?/?$"),
    re.compile(r"^git@github\.com:([^/\s]+)/([^/\s]+?)(\.git)?/?$"),
    re.compile(r"^ssh://git@github\.com/([^/\s]+)/([^/\s]+?)(\.git)?/?$"),
)


def parse_github_remote(url):
    """'https://github.com/owner/name.git' (or ssh/git@ form) -> 'owner/name', or None if not a GitHub URL."""
    if not url:
        return None
    url = url.strip()
    for pattern in _GITHUB_URL_PATTERNS:
        match = pattern.match(url)
        if match:
            owner, name = match.group(1), match.group(2)
            return f"{owner}/{name}"
    return None
