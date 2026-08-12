# ADR-0011: An empty `allowed_tools` grants everything, not nothing

Resolves the open question ADR-0006 flagged and could not answer. The answer is the dangerous one.

## Context

ADR-0006 built STEP 5b — read every created routine back and diff it against what was requested — after the server attached five MCP connectors nobody asked for. It also recorded a question it couldn't settle:

> whether `allowed_tools: []` truly means "no tools" or is read as "unset" ... given `mcp_connections: []` was confirmed ignored, an empty list meaning "unset → default" is a live possibility.

Two independent reviewers flagged the same gap. ADR-0010 then made it *look* less urgent: once the prompts fetched nothing and needed no tools, a permissive reading would grant tools nothing tried to use.

The first real setup run after that settled it. A routine created with `"allowed_tools": []` came back with:

```
["preset:default", "Task", "Bash", "Glob", "Grep", "Read", "Edit", "MultiEdit",
 "Write", "NotebookEdit", "WebFetch", "TodoWrite", "WebSearch", "BashOutput",
 "KillBash", "Skill", "Tmux", "Monitor", "SendUserFile", "REPL"]
```

Empty means **unset**, and unset means the account's full default set: shell execution, file writes, file sending. On an unattended routine firing daily. It also arrived with all five MCP connectors again — so the failure was compound.

The "less urgent" reasoning was wrong, and wrong in an instructive way: it assumed the prompt not *asking* for a tool makes the grant harmless. A grant is a capability, not a request. What made this survivable was that STEP 5b **stopped the run at routine 1 of 4** rather than proceeding — the safeguard from ADR-0006 doing precisely the job it was built for, on its first live exercise.

## Decision

**Never send `allowed_tools: []`. Send the narrowest non-empty list instead.**

Verified directly against the live API: a non-empty list is honoured exactly. Updating the stranded routine to `["TodoWrite"]` and re-reading returned `["TodoWrite"]` unchanged. This also retroactively explains why the earlier `["WebFetch"]` routines kept their narrow grant while `[]` blew wide open — the distinction was never empty-vs-narrow, it was empty-vs-anything.

So `ping_content.allowed_tools()` returns `["TodoWrite"]`. That tool is the choice because it is a session-local scratch list: no filesystem, no network, no side effects outside the run, and nothing any prompt in the pool will ever call. It is a placeholder occupying the slot that `[]` would otherwise leave open for everything.

STEP 5b's tool check is unchanged in spirit and now compares against what STEP 2b actually returned rather than against a hardcoded `[]`.

## Alternatives considered

- **Keep `[]` and rely on the prompts not using tools.** This is the reasoning ADR-0010 used to downgrade the risk, and it's wrong: an unattended agent with `Bash` and `Write` is a capability regardless of what its prompt says, and prompts are not a security boundary.
- **Pick a different placeholder tool.** `Read`/`Glob` leak filesystem contents; `Skill` can invoke other behaviour; `SendUserFile` and `REPL` are worse than the problem. `TodoWrite` was chosen for having the smallest blast radius of anything in the default set.
- **Ask the API for a documented "no tools" value.** None is documented. If one appears, it should replace `MINIMAL_TOOL` and this ADR should be superseded rather than amended.
- **Abort setup entirely until Anthropic supports an empty grant.** Considered seriously, since the plugin cannot express "no tools." Rejected: `["TodoWrite"]` is a genuinely tight grant, and the alternative is a plugin that can't function over a distinction with no practical consequence.

## Consequences

- Every reset routine now carries exactly one harmless tool rather than either nothing (impossible) or everything (the bug).
- ADR-0006's open question is closed. Its STEP 5b is now demonstrated, not merely argued for — it caught this on the first live run it was ever exercised on, and stopped after one routine instead of four.
- The general lesson, already in `CLAUDE.md`: the grant you requested is not the grant you got. This is the second field where a request was silently overridden, which makes read-back a structural requirement rather than a precaution against one known bug.
- Any routine created before this fix has full default tools. There is no API delete, so those must be disabled or removed by hand at https://claude.ai/code/routines.
