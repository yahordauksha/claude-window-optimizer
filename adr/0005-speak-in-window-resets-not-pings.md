# ADR-0005: Speak in window resets, not pings

## Context

Direct Operator feedback on the live setup flow: *"dont ask 'when do you want pings to land', ask 'when do you want your session reset'. Who cares when pings land dude."*

Fair. Every user-facing string in this plugin had drifted into describing the *implementation* — pings, routines, anchors, cron expressions — rather than the thing the user is actually buying. The setup question asked when they start working and the proposal table led with "4 ping routines" and a cron column. All accurate; none of it is what someone deciding "is this schedule right for me?" is actually thinking about.

The drift happened because every internal document — the v1 plan, ADR-0001, the code, the variable names — is legitimately about pings, since that *is* the mechanism. The user-facing copy inherited that vocabulary by default rather than by choice.

## Decision

**User-facing copy talks about when the usage window resets. Internal code, ADRs, and variable names keep the mechanical vocabulary.**

A message landing after the previous window expired *is* a window reset — same event, two framings. The user has an opinion about one of them ("I want a fresh window when I sit down at 9") and no opinion about the other ("a routine fires at 09:00"). So:

- `/setup-window-optimizer` STEP 2 asks: *"What time do you want your usage window to reset each day?"* — not "when do you start working," and never "when should pings land."
- STEP 4's proposal and STEP 7's report lead with reset times. The cron/UTC column stays, demoted to a secondary detail for anyone verifying against their Routines list.
- `/tune-pings` reports `First reset:` / `All resets:` rather than `Pings:`.
- The mechanism is still stated once, explicitly, where the user genuinely needs it: these appear as 4 scheduled routines in their Cloud Routines list, and here's what each does when it fires. Hiding that would be worse than over-explaining it — the user will see them there eventually.

Both command files carry this as a HARD RULE so it doesn't drift back the next time someone edits the copy while thinking in implementation terms.

## Alternatives considered

- **Leave it; "when do you start working" is close enough** — rejected: it's the same number but a different question. "When do you start working" invites a factual answer about the user's habits; "when do you want your window to reset" invites the decision they're actually making, and it's the one they can check the proposed schedule against.
- **Rename the internal vocabulary too** (`ping_content.py` → `reset_content.py`, `PING_INTERVAL_MINUTES` → …) — rejected: churn with no user-visible benefit, and the internal names are genuinely accurate about the mechanism. The split is deliberate: mechanism vocabulary inside, outcome vocabulary outside.
- **Drop mention of routines/pings from user-facing copy entirely** — rejected: the user will find 4 unexplained scheduled agents in their Cloud Routines list. Naming them once, plainly, is what stops that being a surprise.

## Consequences

- Setup reads as a product rather than as a scheduler config screen, and the proposal is checkable against something the user actually has an opinion about.
- The terms diverge between code and copy, which is a real (small) cost when reading the command files: `anchor_local_hhmm` in the JSON is presented as "first reset" on screen. The command files state the mapping explicitly so it isn't a guess.
