# ADR-0001: Cloud Routine scheduling constraints

Resolves [#1](https://github.com/yahordauksha/claude-window-optimizer/issues/1) — every downstream command (#2, #3) was blocked on these findings.

> [!note] Partially superseded
> [ADR-0004](0004-setup-always-asks-for-the-anchor.md) replaces this ADR's week-one/no-data anchor handling: setup now always asks for the anchor and never computes one from the log. Everything else here (the fixed 4-slot layout, 5h10m spacing, no repo attachment, non-interactive create/update) still stands.

## Context

The v1 plan had five explicitly unresolved questions about what the real scheduler supports. Rather than guess, this was tested directly: `RemoteTrigger` (the API backing the `/schedule` skill and https://claude.ai/code/routines) was inspected via its `list`/`get` actions against the real account, which already had two pre-existing manually-created routines ("Start session at 7:30", "Start session at 13:00") — these turned out to be exactly the ad-hoc single/double-ping setup the plan's Problem section describes wanting to replace, and they doubled as ground truth for the API's actual shape.

Note: `CronCreate`/`CronList`/`CronDelete` (a different, session-scoped, in-memory tool for ad-hoc reminders — "session-only... gone when Claude exits," 7-day auto-expiry, jitter up to 15 min) is **not** the same mechanism as Cloud Routines and was not used here. `RemoteTrigger` is the correct, persistent, account-level API.

## Decision

**1. Multi-time-per-day spacing.** A single `cron_expression` is standard 5-field cron — the minute and hour fields are independent lists, exactly as the plan suspected, so one routine cannot express "6:00, 11:05, 16:10" (it would fire on every minute×hour combination). Confirmed resolution: **one daily-recurring routine per ping time slot.** Each routine's own cron is a single fixed daily UTC time (e.g. `"10 11 * * *"`), which is trivial to express and matches the two pre-existing real routines' own shape exactly.

**2. Number of slots — fixed at 4, always.** `RemoteTrigger` has no delete action (routines can only be deleted via the web UI), so a design that changes slot *count* over time would leak undeletable routines every time the count shrinks. Instead: **always exactly 4 daily ping routines**, spaced a fixed 5h10m apart from the anchor. 4 × 310min = 1240min, leaving a wrap-around gap (last ping back to the next day's first ping) of 1440 − 1240 = 200min... 

recomputed precisely: anchor A, A+310, A+620, A+930 (minutes from anchor); wrap gap = 1440 − 930 = 510min = 8h30m. All four gaps (310, 310, 310, 510) are ≥ 5h05m (300min+ floor) — every gap, all day, every day, satisfies the "strictly more than 5h" rule with zero drift, since each slot is a fixed daily UTC time rather than an additive chain. `/tune-pings` only ever **updates** these same 4 routines' `cron_expression` in place — never creates or deletes.

**3. One-shot, non-interactive creation and update — confirmed.** `RemoteTrigger create`/`update` are direct tool calls (not a conversational flow); both complete in a single call given a full body. `/setup-window-optimizer` needs the anchor time as its only real input (from the log, or asked once if no log exists yet) — everything else about the schedule is computed. `/tune-pings` needs no interactive step at all to apply an update, once it has the 4 routines' `trigger_id`s (persisted locally at setup time — see #2/#3's specs).

**4. Repo attachment is NOT required — corrects the plan's stated assumption.** Both pre-existing real routines have no `sources`/`git_repository` in their `session_context` at all, and fire successfully. The plan assumed "Routines require one [repo]" — ground truth contradicts this. **Setup does not ask which repo to attach.** This removes one of the plan's two anticipated setup questions entirely; the only question left for a genuinely fresh install is the rough start-of-day anchor, and only when no log data exists yet.

**5. Daily Routine-run cap — still unconfirmed, accepted as low-risk.** No cap is documented anywhere in the `/schedule` skill's own reference or the API response shape, and testing it would require deliberately spamming routines to find a ceiling — a bad trade against the tiny real footprint here (exactly 4 routine *runs*/day; `/tune-pings` itself runs locally in the user's own session, not as a routine). Not worth resolving further for v1; if it's ever hit, `RemoteTrigger create` will surface it as a loud API error, not a silent failure.

## Alternatives considered

- **One routine with `cron_expression: "0,5,10 6,11,16,21 * * *"`-style combinatorial minute/hour lists** — rejected outright; this fires on every minute×hour cross-product, not the intended 4 distinct times.
- **Variable slot count, recomputed by `/tune-pings` based on the user's actual active-hours span** — rejected because routines can't be deleted via the API; shrinking the slot count would strand orphaned routines the user would have to notice and manually delete via the web UI. Fixed-4 avoids this whole failure class.
- **Asking for a repo at setup, per the original plan** — rejected once ground truth showed it isn't required by the API; asking for it anyway would just be unnecessary friction against the "one command, done" goal.

## Consequences

- `/setup-window-optimizer` and `/tune-pings` both only ever operate on exactly 4 known `trigger_id`s, persisted locally after first creation (design detail for #2/#3: store them in `.window-optimizer-routines.json` next to the log file). This makes both commands simple, idempotent-by-update, and leak-free.
- If Anthropic's API later adds routine deletion, `/tune-pings` could be revisited to support a variable slot count — not needed for v1, and not blocking anything today.
- The ping prompt itself should stay minimal (matching the two pre-existing routines' own "Just answer 'Hello'" pattern) and should self-identify as an automated keep-alive (unlike the existing bare "Hello") so it reads as obviously benign to anyone — including a different user who installs this plugin — who stumbles on it in their session history.
