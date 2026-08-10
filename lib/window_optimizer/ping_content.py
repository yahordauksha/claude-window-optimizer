"""Ping content templates: what each slot's Cloud Routine prompt actually says.

Separate from schedule.py (timing math) — this is about *what* a ping does,
not *when*. See adr/0002-useful-ping-content.md for why the kind set is
deliberately narrow in v1: WebFetch against a public, unauthenticated API
only — no MCP connectors, no private-repo support, no `gh` CLI auth
assumptions. Those weren't verifiable without spending an undeletable-via-API
test routine, so they're a disclosed follow-up, not something guessed at.
"""

PING_KIND_SIMPLE = "simple"
PING_KIND_GITHUB_ISSUES = "github-issues"

KNOWN_KINDS = (PING_KIND_SIMPLE, PING_KIND_GITHUB_ISSUES)

_PLUGIN_URL = "https://github.com/yahordauksha/claude-window-optimizer"


def simple_ping_prompt():
    return (
        "This is an automated keep-alive ping from the Claude Window Optimizer "
        f"plugin ({_PLUGIN_URL}). It exists only to keep your Claude Code usage "
        "window aligned to your work hours — no action is needed. Reply with a "
        "short acknowledgement."
    )


def github_issues_prompt(repo):
    """`repo` is 'owner/name' for a PUBLIC GitHub repo — uses the unauthenticated public REST API only."""
    api_url = f"https://api.github.com/repos/{repo}/issues?state=open&sort=updated&per_page=3"
    return (
        "This is an automated check-in from the Claude Window Optimizer plugin "
        f"({_PLUGIN_URL}), timed to when you're usually working. Use WebFetch on "
        f'"{api_url}" and report the titles of up to 3 most-recently-updated open '
        f"issues on {repo}, one line each (issue number + title, nothing else). "
        'If there are none, just say "No open issues." Keep your reply short — '
        "this is a quick check-in, not a full report."
    )


def allowed_tools_for_kind(kind):
    if kind == PING_KIND_GITHUB_ISSUES:
        return ["WebFetch"]
    return []


def prompt_for_kind(kind, repo=None):
    if kind == PING_KIND_GITHUB_ISSUES:
        if not repo:
            raise ValueError("github-issues kind requires a repo")
        return github_issues_prompt(repo)
    if kind == PING_KIND_SIMPLE:
        return simple_ping_prompt()
    raise ValueError(f"unknown ping kind: {kind!r}")
