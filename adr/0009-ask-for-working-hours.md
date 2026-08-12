# ADR-0009: Ask for working hours, and derive the anchor from them

Supersedes ADR-0005's *question*, keeps its *principle*. Also closes the round-2 review finding that ADR-0004 and ADR-0005 had left setup asking a question whose answer is systematically the wrong anchor.

## Context

ADR-0004 established that setup always asks rather than computing from a log. ADR-0005 established that the question should be about window resets, not implementation. Both hold up. But an independent reviewer pointed out that the resulting question — *"what time do you want your usage window to reset each day?"* — produces a bad schedule when its answer is used directly as the anchor, and that this compounds because the user lives with that schedule until `/tune-pings` has enough data.

I initially deferred this: my quick simulation showed a ~3% effect where the reviewer reported ~16%, and I wasn't going to change the core heuristic on an unresolved 5× discrepancy.

Building the simulator settled it, and **the reviewer was approximately right and I was wrong**. My throwaway model didn't simulate window dynamics properly. With a real one (`tools/window_sim.py`, 28 days × 35 prompts/day, mean of 20 seeds, peak prompts on any single window):

| profile | no plugin | anchor = stated start | best possible |
|---|---|---|---|
| 9-5 steady | 28.5 | 27.6 | 23.6 |
| **evening 20:00–01:00** | **41.5** | **41.5** | **24.6** |
| split day | 23.6 | 23.6 | 17.8 |
| bursty 09–18 | 24.1 | 23.9 | 18.1 |
| long day 08–23 | 19.2 | 19.1 | 16.6 |

The evening row is the indictment: a user who installs this plugin, answers the question honestly, and waits gets **exactly the same outcome as never installing it**, while a 41% improvement was sitting there. The mechanism is fine; the question wastes it.

The cause is structural. A reset at the head of a work block leaves the entire block riding on one budget. What you want is a reset landing *partway through* — which is exactly what `/tune-pings`' objective picks, and exactly what a start time can't express.

I also checked whether a fixed offset would rescue it (anchor = stated time + k). It doesn't: offsets from 0 to 210 minutes are uniformly bad, and while +300 helps the evening and split profiles it makes 9-5 *worse*. There is no single offset, because the right anchor depends on the shape of the day.

## Decision

**Setup asks what hours you work, and derives the anchor by running the same objective `/tune-pings` uses against a flat synthetic day covering those hours.**

- New `anchor_for_working_hours(start, end)` builds a uniform histogram over the stated span and calls `best_anchor_for_histogram` — the function `compute_balanced_anchor` was refactored to expose, so both paths provably optimise the same thing. A test asserts the two entry points agree.
- `compute_schedule.py --hours HH:MM-HH:MM` is the path setup uses. Overnight ranges wrap correctly. `--anchor HH:MM` survives for anyone who genuinely wants to name a reset time.
- Options in the question still show the reset times each choice produces (the fix from the previous revision) — that requirement is unchanged and, if anything, matters more now that the mapping from answer to schedule isn't identity.

Measured improvement, same simulator, as a fraction of the achievable gap closed:

| profile | gap closed |
|---|---|
| evening | **88%** |
| 9-5 | **74%** |
| long day | 18% |
| split day / bursty | 0% |

Never worse anywhere. The two 0% rows are multi-block days — a morning and a late evening with a long gap — which a flat block genuinely cannot represent. `/tune-pings` fixes those once real data exists; setup no longer pretends to.

**ADR-0005's principle survives intact.** The user is still never asked about pings, cron, or anchors, and still sees reset times as the answer. What changed is that we now ask them something they actually know (when they work) instead of something they'd have to reverse-engineer the scheduler to answer well (when a reset should fire).

## Alternatives considered

- **Keep asking for a reset time.** Rejected on the measurement above: honest answers produce near-zero benefit for the profile that stands to gain most.
- **Apply a fixed offset to the stated start.** Tested across nine offsets and five profiles; no offset is good everywhere and the best-on-average one degrades the most common profile. Rejected on evidence.
- **Ask two questions (start, then end).** Same information, worse experience. One question about a range gets both numbers.
- **Ask nothing and pick a default.** Tempting given the no-questions discipline of ADR-0003, but the shape of someone's day is exactly the thing no signal on the machine reveals, and it's the input that matters most.

## Consequences

- The initial schedule is now a coarse version of the eventual tuned one rather than a different idea, because both come from one objective. That's a real design improvement independent of the numbers.
- Multi-block workers still get a mediocre first week. Named, not hidden; `/tune-pings` is the fix and the README says who benefits least.
- `tools/window_sim.py` now exists and is the thing ADR-0007 declined to build. It was the right call to be skeptical of simulation-based *optimisation* (a reviewer showed it doesn't generalise out-of-sample), but simulation-based *evaluation* of a fixed heuristic is exactly what was needed here, and its absence let this bug sit undetected through two reviews.
