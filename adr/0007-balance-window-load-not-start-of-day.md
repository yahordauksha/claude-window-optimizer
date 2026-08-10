# ADR-0007: Anchor by balancing window load, not by guessing "start of day"

Supersedes the anchor estimator described in ADR-0001 and used through ADR-0006. The scheduling mechanics (4 resets, 5h10m spacing, ADR-0001) and setup's always-ask rule (ADR-0004) are unchanged.

## Context

The original estimator answered "what time does this person start work?" — take the earliest prompt of each calendar day over 28 days, circular-mean those times, blend 70/30 with a same-weekday average. Operator pushback, and it was right on two counts:

> *"we not only have a single anchor in a day right, so calculating just one anchor per day is misleading"*
> *"we have logging for every prompt time. why would we only count one?"*

and then, on what the objective should actually be:

> *"its calculating when the user usually runs out of tokens, and try to make it so that the reset time is perfectly timed so that he never has to wait"*

Three separate defects, in increasing order of importance:

1. **It discarded ~99% of the data.** One sample per day to estimate one scalar. Measured: three stray 06:00 pings across 20 days moved the anchor **71 minutes**. Worse, the sensitivity was non-monotonic — *five* strays moved it less than three, because what mattered was which weekday they landed on. With ~4 same-weekday samples in 28 days and a 70% weight on that average, one bad sample on the wrong weekday swung the whole schedule.
2. **"Start of day" isn't a real quantity.** People work in several sessions; a day has no single anchor. And taking the per-day *minimum* biases the estimate earlier in a way nothing corrects, since a stray 5am check counts but a late night never offsets it.
3. **It optimised the wrong thing entirely.** Even a perfect estimate of "when you start" doesn't answer the question the product exists to answer. You get blocked when a *single window* absorbs more work than its budget allows, and you then wait for that window to expire. Where your day starts is at best a weak proxy for that.

## Decision

**Choose the anchor that minimises the busiest window's share of your actual prompts.**

- Build a per-minute histogram of **every** logged prompt over the trailing 28 days (`usage_histogram`).
- The four resets partition the 24h circle into segments of 310/310/310/**510** minutes. Each segment is the work riding on that reset's budget.
- Score every one of the 1440 candidate phases by `(peak segment load, load on the 510-minute segment)` and take the minimum. Prefix sums make this ~5.7k operations, not a search.
- Ties are common with sparse data; take the centre of the widest tied band so the schedule sits on a plateau rather than on an edge that one new prompt would flip.

Minimising the peak is the right objective under uncertainty about the actual token budget: it maximises the threshold at which *any* window would start blocking you. And it produces the behaviour the Operator described — for a heavy 09:00–13:00 block, it places a reset at ~10:46, splitting 160 prompts into 80/80 instead of leaving all 160 on one budget.

Measured against the old estimator on the same data: the three stray pings that moved the old anchor 71 minutes move this one by **0**.

## Alternatives considered

- **Keep the mean, fix it with a circular median and a sample-count-scaled weekday weight.** This was the plan before the Operator's third point landed. It would have fixed the robustness symptom while leaving the estimator answering the wrong question. Rejected — patching an estimator whose target quantity is wrong is wasted work.
- **Minimise usage falling in the uncovered gaps** (the 210-minute overnight stretch plus 3×10-minute slivers). Implemented, tested, and **rejected on evidence**: it has a degenerate optimum. Gaps were scored as costing nothing, so the optimiser learned to hide usage in them — a night-owl profile scored a *perfect zero* by placing every prompt where no window was open, which is the worst possible schedule. This is why segments partition the whole day rather than tracking window coverage: it makes that optimum unrepresentable. Regression test: `test_balanced_anchor_never_hides_usage_in_uncovered_gaps`.
- **Weight prompts by tokens.** The genuinely correct measure of "budget absorbed," and still unavailable — hooks don't expose token counts (ADR-0001 / the v1 plan). Prompt volume is the honest proxy. If token data ever becomes available, only `usage_histogram` needs to change; the optimiser above is already weight-agnostic.
- **Simulate window state prompt-by-prompt** (a prompt in a gap opens its own window, shifting everything downstream). More faithful, but the added fidelity only matters in exactly the case the design is trying to prevent, and it would make the objective non-closed-form for a gain that's speculative until there's real usage data to check it against.

## Consequences

- The word "anchor" now means "the phase of the reset schedule," not "when you start work." User-facing copy already says "what time do you want your window to reset" (ADR-0005), which happens to remain the right question to ask a human — they can answer it, and it's a fine starting point until `/tune-pings` has real data.
- `compute_weighted_anchor`, `_circular_mean_minutes`, and the weekday-weighting constants are **deleted**, not deprecated — same discipline as ADR-0004's removal of `--from-log`. `first_prompt_per_day` survives, used only for counting distinct logged days.
- Tests that asserted specific clock values from the old model were rewritten to assert properties (peak load is minimal, every prompt is accounted for, the optimiser actually returns an optimum). They were coupled to estimator internals; that coupling is why they passed while the estimator was wrong.
- Still only affects `/tune-pings`. Setup asks (ADR-0004) and is unchanged.
