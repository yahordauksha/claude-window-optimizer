# ADR-0002: Useful ping content, not a no-op

Resolves [#7](https://github.com/yahordauksha/claude-window-optimizer/issues/7).

> [!note] Superseded
> [ADR-0003](0003-auto-detect-instead-of-asking.md) replaced this ADR's "ask the user which repo, never guess" stance with auto-detection. [ADR-0010](0010-fixed-safe-prompt-pool.md) then removed the whole idea: resets now send fixed, self-contained prompts and fetch nothing, so there are no content "kinds", no `WebFetch` grant, and no repo. Kept for the reasoning trail — the useful part is how a reasonable-looking personalisation feature turned into the plugin's only real attack surface.

## Context

v1 shipped with every ping sending the same fixed "reply with a short acknowledgement" prompt — mechanically correct (it registers a message, which is all the window-keepalive mechanism actually needs), but the Operator pointed out it's a wasted opportunity: a ping that's obviously a no-op is also obviously disposable/confusing to anyone who sees it in their Cloud Routines list, and it could just as cheaply do something real. The Operator's own examples: midday (usually coding) → last open GitHub issue; morning → check email.

Separately, setup itself didn't explain what an "anchor" is or that the 4 things about to be created are pings — both fixed here, not just the content question.

## Decision

**Ping content is now assigned per slot, from one of two kinds:**

- `simple` — the original no-op keep-alive (unchanged prompt, `allowed_tools: []`).
- `github-issues` — a check-in that uses `WebFetch` against the **public, unauthenticated** GitHub REST API (`api.github.com/repos/{owner}/{name}/issues?state=open&sort=updated`) to report the most recently updated open issues on a repo the user names. Verified directly (via a real, unauthenticated `curl` call against this repo) before committing to the design — not assumed.

**v1 explicitly does not attempt email, calendar, or any MCP-connector-backed check**, even though the Operator's own morning-email example was right there. Reason: confirming an MCP connector (e.g. Gmail) actually authenticates correctly when attached to a *scheduled Cloud Routine* — as opposed to a normal interactive session — isn't verifiable without creating a real routine and firing it, and `RemoteTrigger` has no delete action (see ADR-0001). Spending an undeletable-via-API routine to test something that might not even work is a bad trade against just shipping the one kind that's fully verified and building on it later. This is a disclosed scope cut, not a silently dropped requirement — the setup command says so explicitly if a user's description implies something this doesn't cover.

**Setup now explains two things every time, not just once in passing:** what "anchor" means (the local time each day this system treats as roughly "start of work," which the 4 pings are spaced out from), and that the 4 things about to be created are pings that will show up in the user's real Cloud Routines list. Both are said in STEP 2 (before asking) and reinforced in STEP 4 (the proposal) and STEP 7 (the report) — not just documented in this ADR where a user would never see it.

**Content is fixed at setup time, never touched by `/tune-pings`.** `/tune-pings` only ever calls `RemoteTrigger update` with `cron_expression` — `kind`/`repo`/the actual prompt stay exactly as `/setup-window-optimizer` set them. Re-deriving "what should each slot check now" on every weekly tune-up is a meaningfully different, unbuilt feature (it would need to re-ask or re-infer the user's rhythm every week) — out of scope here, and not something to improvise into `/tune-pings`' existing, narrowly-scoped update call.

**Tool grant stays minimal and kind-specific.** A `github-issues` slot gets exactly `["WebFetch"]` — no `Bash`, no repo checkout (`session_context.sources` stays unattached, same as ADR-0001), no MCP connectors. The grant comes from tested code (`ping_content.allowed_tools_for_kind`), not composed per-invocation, so it can't silently drift wider than intended.

## Alternatives considered

- **`gh` CLI via Bash, instead of WebFetch against the public API** — rejected: whether the Cloud Routine's CCR sandbox has `gh` pre-authenticated for the user's account is unverified and not worth assuming; the public REST API needs no auth at all for a public repo, which is both simpler and already directly verified.
- **Asking the user to attach the repo as a real git source** (`session_context.sources`) — rejected: unnecessary for just reading open issues via the REST API, and it would reopen ADR-0001's "no repo attachment required" finding for no real benefit.
- **Re-deriving ping content every week from `/tune-pings`** — rejected for now (see Decision above); content staying fixed after setup is the simpler, already-shippable behavior, and revisiting this is a clean, separable follow-up if it turns out to matter in practice.
- **Guessing a repo from context** (e.g. the currently open project) — rejected: `/setup-window-optimizer` can run from any working directory, and a scheduled Cloud Routine has no "current project" of its own regardless: silently guessing wrong is worse than asking once.

## Consequences

- A user who wants email/calendar-based pings doesn't get them yet — this needs a follow-up issue once MCP-connector-in-a-routine behavior is actually verified (create one real routine, fire it via `RemoteTrigger action: "run"`, confirm the connector actually authenticates — that's the concrete next step, not more guessing).
- `routines.json`'s schema grew two fields (`kind`, `repo`) per slot. `tune_schedule.py` passes them through via `.get()` with safe defaults, so an install from before this ADR (if one existed) wouldn't crash `/tune-pings` — though in practice v1 was never released before this shipped, so this is a forward-looking safety net more than a real migration concern.
- Setting up now involves one more optional question (STEP 2b) — deliberately framed as skippable in one line, so it doesn't reopen the "install, run once, done" friction ADR-0001 and the original plan were built around.
