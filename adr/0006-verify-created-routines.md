# ADR-0006: Verify what was created; never trust the create response

## Context

Real incident, caught during the first live setup run. `/setup-window-optimizer` sent a create body containing no `mcp_connections` field and `allowed_tools: ["WebFetch"]`. The routine came back with **five MCP connectors attached** — Gmail, Google Calendar, Microsoft 365, Notion, and Claude Code Remote — applied by the server as account-level defaults.

Two things went wrong, and only one of them is the server's.

1. The server attaches account-default connectors to new routines. Not the plugin's doing; the user's own pre-existing "Start session at 7:30" routine had the same four.
2. **The command asserted its own tool grant from the request it sent, and never read back what actually existed.** STEP 4 told the user "no MCP connectors" and STEP 7 reported success — both derived from the request, not from reality. The violation went live on a daily-firing routine and was caught only because someone happened to read the API response by eye.

The second is the real defect, and it's the general one: this plugin's whole safety posture is "minimal, explicit grants," and it had no mechanism to detect when reality diverged from that. Any future server-side default, field rename, or silently-dropped parameter would land exactly the same way.

Worth noting what *wasn't* wrong: `allowed_tools` was correctly set to `["WebFetch"]` on the live routine, and MCP tools are named `mcp__<server>__<tool>`, so they plausibly wouldn't have matched the allowlist anyway. The practical risk was low. But "the grant we didn't want was probably inert" is not the standard a plugin that advertises minimal grants should ship — and nobody had verified even that much.

## Decision

**Every created routine is read back with `get` and diffed against what was requested, before setup reports success** (STEP 5b). Three checks, with different remedies:

- **Unexpected `mcp_connections`** → clear them with `{"clear_mcp_connections": true}`, then `get` **again** to confirm. This remedy is verified working against the real API, not assumed: it was used to clean the routine from this incident, and an independent `get` confirmed `mcp_connections: []` afterward. If the clear doesn't take, stop and hand it to the user for manual deletion.
- **`allowed_tools` is not what was requested** → stop everything and report the exact difference. Never repair a tool grant by guessing what it should be. This check earned its keep on the first real setup run after it shipped: see `adr/0011-empty-allowed-tools-means-everything.md`.
- **`cron_expression` differs from what was sent** → stop and report. A schedule that isn't what was confirmed isn't a schedule the user agreed to.

**`"mcp_connections": []` is also sent explicitly in the create body — but it does *not* work, and this is now confirmed rather than hoped.** The first live create after writing this ADR sent an explicit empty list and the server attached all five connectors anyway. So the field is kept only because it makes the request's intent legible; it is **not** a remedy, and nobody should read its presence as one. **`clear_mcp_connections` after creation is the only mechanism that actually works**, verified by independent read-back on all four routines.

That outcome is worth stating plainly because it's the exact scenario this ADR was written to catch, and it happened on the very next create: an explicit field, silently ignored. Had STEP 5b not existed, the "fix" would have shipped as a one-line change to the request body, looked correct in review, and left every routine still carrying connectors.

**A passing verification prints nothing.** The check is for catching divergence, not for reassuring the user that software worked.

## Alternatives considered

- **Trust `allowed_tools` to gate MCP tools and accept the connectors** — rejected. Plausible (MCP tools are `mcp__*`-namespaced and wouldn't match a `["WebFetch"]` allowlist), but unverified, and it would mean shipping a daily-firing routine with mail and calendar attached on the strength of a guess. It also silently redefines what the plugin promises.
- **Send `mcp_connections: []` and call it fixed** — rejected as the *only* measure: that's the same class of mistake as the original defect, trusting a request to determine reality. It's worth doing, but only alongside read-back.
- **Verify once, on the first routine only** — rejected: cheap to do all four (`get` is a fast read), and per-routine divergence is exactly the kind of thing that wouldn't be uniform.
- **Delete and recreate on any divergence** — not possible: `RemoteTrigger` has no delete action (ADR-0001). That constraint is precisely why detecting divergence *before* creating the remaining routines matters — the blast radius of proceeding is permanent-until-manually-cleaned.

## Consequences

- Setup makes 4 extra `get` calls (8 if any need clearing). Negligible cost for the only mechanism that can catch request/reality divergence.
- The plugin now has a general answer to "what if the platform does something we didn't ask for," rather than one patch for one connector bug.
- `/tune-pings` still doesn't read back its updates. Lower stakes — it only ever changes `cron_expression`, and a wrong cron is visible in the reported reset times — but it's the same class of gap and is worth revisiting if this pattern ever bites there. Named here rather than silently scoped out.
