# ADR-0008: Only auto-detect repos you own

Narrows ADR-0003. Auto-detection stays; what it's allowed to select does not.

## Context

An independent review found this, and it's the finding I'd most want back.

ADR-0002 had a hard rule: *"Guessing a repo from context… rejected: silently guessing wrong is worse than asking once."* ADR-0003 reversed it on direct Operator instruction — *"you shouldn't ask that. Just make shit up"* — which was correct about the UX and wrong about the trust boundary, because nobody noticed a trust boundary was being crossed. The reversal is recorded in ADR-0003 as a UX decision. It was also, unremarked, a decision about whose text this plugin feeds to an unattended agent.

The mechanics: `detect_repo.py` reads `git remote get-url origin` from whatever directory setup happened to run in. The reviewer demonstrated it directly — run setup inside a clone of `facebook/react` and it returns `facebook/react`. The ping prompt then asks a Haiku agent, with `WebFetch` and no supervision, four times a day, to fetch that repo's open issue **titles** and report them. Issue titles on a public repo are written by arbitrary internet users.

That is untrusted input flowing into a scheduled agent with network egress. It compounds with a second finding: the server attaches five MCP connectors (Gmail, Calendar, Microsoft 365, Notion, Claude Code Remote) to every new routine, an explicit `mcp_connections: []` in the create body is confirmed ignored, and the only remedy — STEP 5b's read-back-and-clear — is prose in a markdown file that an LLM is asked to follow. No code enforces it. A skipped STEP 5b ships a daily agent with a mailbox attached, reading stranger-authored text.

## Decision

**A repo is only auto-selected if the authenticated GitHub account owns it.**

`detect_repo.py` now resolves `gh api user --jq .login` first, and:

- Repo from the cwd git remote → accepted only if `owner == login` (case-insensitive), then still checked public as before. Otherwise dropped.
- Fallback path → `gh repo list` returns only your own repos today, but the ownership check is applied to it anyway rather than depending on that staying true.
- **Not authenticated → no repo at all.** Without an identity there's no way to establish ownership, so it degrades to a plain keep-alive rather than trusting whatever's lying around.

This keeps ADR-0003's actual requirement intact — setup still asks nothing — while removing the arbitrary-internet-text path. You can still be fed hostile text by an issue on *your own* repo, but that's a threat model with a named, reachable owner, not "anyone on GitHub."

## Alternatives considered

- **Go back to asking which repo.** Rejected: reverses a decision the Operator made deliberately, and the ownership check achieves the same safety without a question.
- **Report issue *counts* instead of titles.** Removes the untrusted text entirely and is genuinely tempting. Rejected for now because the count alone is a much weaker check-in, and ownership already shrinks the threat surface to your own repos. Worth revisiting if the ping ever reads richer fields (issue *bodies* would change this calculus immediately).
- **Enforce connector-stripping in code rather than in STEP 5b's prose.** Not currently possible: `RemoteTrigger` is a model-invoked tool with no Python binding, so there is no code path that could enforce it. Named here rather than quietly dropped — it remains the weakest link in this design, and if a scriptable API ever exists, that's the fix.
- **Restrict `allowed_tools` further so a hostile instruction has nothing to act on.** Already minimal (`["WebFetch"]`), and `WebFetch` is exactly what the check-in needs. Note that ADR-0006 flagged, and this ADR does not resolve, that `allowed_tools: []` has never been verified to actually mean "no tools" — given `mcp_connections: []` was confirmed ignored, an empty list meaning "unset → default" is a live possibility worth testing.

## Consequences

- A user whose current project is someone else's repo now gets a keep-alive, or their own most-recent public repo, instead of a stranger's issue tracker. Slightly less "useful" ping in that case; correctly so.
- Users with no `gh` auth get keep-alives. Acceptable: the check-in was always best-effort, and silently trusting an unverifiable repo is worse than a boring ping.
- Setup now depends on `gh api user` succeeding. If `gh` is absent the detection degrades safely rather than failing.
- The broader lesson is recorded in `CLAUDE.md`: a UX simplification that changes *what the system trusts* is a security decision wearing a UX decision's clothes, and needs to be called out as one at the time.
