# ADR-0004: Setup always asks for the anchor; only /tune-pings reads the log

Fixes [#10](https://github.com/yahordauksha/claude-window-optimizer/issues/10) properly. Supersedes ADR-0001's decision 5 (week-one anchor handling) and replaces the partial fix that preceded this one.

## Context

Two rounds of the same bug, reported live by the Operator both times:

1. First run: setup reported "anchor at 13:40 local, computed from your logged activity" on a fresh install. Root cause: `/setup-window-optimizer` is itself a prompt, so the `UserPromptSubmit` hook logs its own invocation before STEP 2 reads the log back. One timestamp's weighted average is trivially itself.
2. After adding a 3-distinct-day minimum: **same symptom again** — "13:49 anchor." The guard worked as written, but the log by then contained a few days of the Operator and me iterating on this plugin, clustered in the afternoon. So the anchor was a genuine, correctly-computed average of *testing this plugin*, not of the Operator's actual working rhythm.

The Operator's response was the right call and worth quoting, because it names the real problem: *"why is it still just current time. Dude you can just ask the first time, its fine."*

The second failure is the instructive one. The first fix was technically sound and still produced a useless answer, because the flaw wasn't the threshold — it was the premise. **On a first run there is no such thing as trustworthy log data**, by construction: the log's entire contents are the act of installing and trying out this plugin. No threshold fixes that, because the data isn't sparse, it's unrepresentative. Raising the minimum to 7 or 14 days would just delay the same wrong answer, and would leave setup unable to complete at all until then.

## Decision

**`/setup-window-optimizer` always asks for the anchor. It never reads the log.** `compute_schedule.py`'s `--from-log` mode is deleted outright, not merely unused — a mode that exists gets reached for again later, and this is the second time this exact behavior has had to be walked back.

**Log-based anchoring lives exclusively in `/tune-pings`** (`tune_schedule.py`), where it was always the right idea: that command is explicitly framed around a trailing ~4-week window, runs weekly, and exists precisely to correct the initial guess with real data once real data exists.

**The 3-distinct-day minimum moves to `tune_schedule.py`**, where it still does useful work — it stops an early or unusual week from swinging the whole schedule on two days of noise, and now returns `insufficient_log_data` with the actual day count so `/tune-pings` can say what it's declining to do and why.

This also restores what the original v1 plan actually specified for week one ("setup command should ask once, or default to a reasonable guess... that the first `/tune-pings` run corrects after ~2 weeks of logging") — ADR-0001's decision 5 drifted from that toward auto-computation, and this is the correction.

## Alternatives considered

- **Raise the minimum-days threshold (7, 14, 28)** — rejected: doesn't address the actual defect. First-run log data is unrepresentative rather than merely thin, so a higher bar delays the wrong answer instead of preventing it, and blocks setup from completing in the meantime.
- **Exclude the plugin's own setup invocation from the log before computing** — rejected: fixes exactly one polluting entry while every other entry from the same install-and-try-it session remains. Fiddly, incomplete, and still leaves setup depending on data that doesn't exist yet.
- **Keep `--from-log` as an opt-in flag for people who install and wait a month before running setup** — rejected as speculative: nobody installs a plugin and then doesn't run its one setup command for a month. Keeping a mode alive for a hypothetical user is how this bug recurs a third time.
- **Ask, but pre-fill the computed value as a suggested default** — rejected: this is the failure mode in a friendlier costume. A wrong number shown as a suggestion still anchors the answer, and still has to explain where it came from.

## Consequences

- Setup now always costs exactly one question. Given that the plugin's whole pitch is "install, run once, done," one deliberate question is a better trade than a silently wrong schedule the user has to notice and correct — and it removes an entire class of "why is it just current time" confusion.
- Anyone who *does* have weeks of real log data before first running setup gets a guess rather than a computed anchor. That's fine: `/tune-pings` fixes it on the first run, which is exactly the mechanism that already exists for this.
- `compute_schedule.py` gets meaningfully simpler (no log reads, no error branches for missing/insufficient data), and `tune_schedule.py` owns log-based anchoring end to end — one behavior, one home.
