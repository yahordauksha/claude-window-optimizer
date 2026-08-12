# Claude Window Optimizer

**Your Claude Code allowance resets every 5 hours — spend it fast and you sit out the rest.** This schedules four resets a day, timed around when you actually work.

**1.** In a terminal:

```bash
claude plugin marketplace add yahordauksha/claude-window-optimizer
claude plugin install claude-window-optimizer@claude-window-optimizer
```

**2.** Open Claude Code — CLI or Desktop — and run:

```
/setup-window-optimizer
```

One question, one confirmation, done.

---

## The problem

Your allowance is **per 5-hour window**. Go hard and you can burn a whole window's worth in an hour — and then you're locked out for the remaining four.

```
09:00   start working, going hard
10:15   ✗ allowance gone
          └── nothing until 14:00. four hours of thumbs.
14:00   window finally resets
```

Four hours of dead time, sitting on a subscription you're paying for.

And it's worse than it looks, because you don't get to choose when that lockout lands. The window started with your **first message of the day** — whatever it was. Ask one throwaway question at 07:12 and your four-hour wall arrives at 11:15 instead of 14:15, right in the middle of the afternoon.

The usual workaround is a single scheduled ping in the morning. I ran two of those for weeks, and that's what made me build this: one ping just moves the wall, it doesn't remove it.

## The fix

Four resets a day, so your work is spread across **four separate allowances** instead of piling onto whichever one you happened to open:

```
07:50   ● reset
13:00   ● reset   ── lands mid-afternoon, on purpose
18:10   ● reset
23:20   ● reset
```

Any one stretch of heavy work is far less likely to drain a window. And when you do hit the wall, the next reset is minutes away rather than hours.

That mid-block reset at 13:00 isn't an accident — see [how the timing is chosen](#the-weekly-tune-up).

## What setup actually looks like

It asks one question, and shows you exactly what each answer produces:

```
What hours do you usually work? Rough is fine — this is only a starting
point. Once you've built up a week or two of real usage, /tune-pings
recalculates the schedule from when you actually work.

  1. 09:00–17:00     Window resets at 07:50, 13:00, 18:10, 23:20
  2. 10:00–19:00     Window resets at 09:20, 14:30, 19:40, 00:50
  3. 20:00–01:00     Window resets at 17:20, 22:30, 03:40, 08:50
  4. Something else
```

It asks about your day rather than asking you to pick reset times, because the
best reset times aren't where you'd guess. Notice option 1 puts a reset at 13:00 —
*inside* the working day. That's deliberate: a reset at 09:00 would leave your whole
morning-to-evening block riding on one allowance. I had it the other way round at
first and measured that it gave evening workers no benefit at all.

Then it shows the full plan and waits:

```
Your window will reset daily at 07:50, 13:00, 18:10, 23:20 (local).
4 routines in your Cloud Routines list. Each sends a short message:
Water, Stretch, Mood, Check-in. No tools, nothing fetched.

Create them?
```

Nothing is created until you say yes. That's the whole setup.

---

## How it works

### Why 5h10m, and not 5 hours

A scheduled message only opens a new window if the previous one has **already expired**. Send it a minute early and it lands inside a still-open window and does nothing at all.

So the gap between resets has to be *strictly more than* five hours. 5h10m gives a small margin without wasting the difference. Four of them tile a day with every gap clearing that floor — including the long overnight one.

### Why four, and why they never change

Four fits a day. They're created once and then only ever **retimed** — never added or removed — because the Routines API has no delete. A design that added and dropped routines would leave orphans for you to clean up by hand.

### What the resets actually say

A reset works because *a message was sent* — the content is irrelevant to the mechanism. So each routine sends one short, self-contained line from a [fixed pool](lib/window_optimizer/ping_content.py): a stretch reminder, a posture check, "reply with just 'ok'". Four different ones, so your Routines list isn't four identical robots.

They fetch nothing and get no tools at all. I originally had them read your GitHub repo's open issue titles, which sounded useful until a reviewer pointed out I'd wired an unattended agent to text any stranger could write by filing an issue — in exchange for nothing the mechanism actually needed. [ADR-0010](adr/0010-fixed-safe-prompt-pool.md) has the full story.

### The weekly tune-up

The plugin ships a hook that notes **when** you send prompts. Timestamps only — never content, never tokens. After a few weeks that's a picture of your real working rhythm.

Run `/tune-pings` and it shifts your four resets to whatever spreads your actual usage most evenly across the four windows:

```
Window resets: 05:36, 10:46, 15:56, 00:26  (was 08:00, 13:10, 18:20, 23:30)
Based on 23 days / 412 prompts, last 28 days
```

The goal isn't to match when you start work — it's to stop any single window carrying enough of your day to run dry. If your heavy block is 9am–1pm, you actually *want* a reset landing at 10:46: that splits four hours of hard work across two allowances instead of betting the whole block on one.

You'll get a nudge to run it after 7 days. It refuses to act on thin data rather than shuffling your schedule around noise.

---

## Honest limitations

Things I'd want to know before installing someone else's plugin. All of these are covered in more depth in [`adr/`](adr/).

**It counts prompts, not tokens.** Hooks don't expose token counts, so a one-word question weighs the same as a 50-file refactor. Prompt volume is a proxy — it's the only signal I can actually get at.

**It won't help everyone equally.** I simulated the window dynamics (`tools/window_sim.py`) across a few working patterns: a concentrated evening block gains ~31%, a 9-5 day ~15%, and someone working fifteen hours straight gains ~1% — they already chain fresh windows naturally. If your day has no idle gaps, this isn't for you.

**The weekly cap still exists.** Session and weekly allowances are consumed at the same time. This plugin does nothing about the weekly one.

**Routines can't be deleted through the API.** Setup creates four; removing them is a manual step at [claude.ai/code/routines](https://claude.ai/code/routines). That's the real cost of installing this, and I couldn't design it away.

---

## Install

### Everyone

**Step 1 — install.** In a **normal terminal**; you don't need to start Claude Code first:

```bash
claude plugin marketplace add yahordauksha/claude-window-optimizer
claude plugin install claude-window-optimizer@claude-window-optimizer
```

These install at **user scope**, so the plugin is available everywhere: every CLI session, and the Desktop app's Code tab.

**Step 2 — set it up.** Open Claude Code and run:

```
/setup-window-optimizer
```

It asks what hours you work, shows you the full proposed schedule, and waits for your confirmation before creating anything.

If the command isn't there, you're in a session that started before the install — open a new one, or run `/reload-plugins`.

### If you're on Desktop

Restart the app after installing, and you'll find the plugin under the **+** button next to the prompt box → **Plugins**.

Two things that trip people up here, both worth knowing:

- **`/plugin` doesn't work in Desktop.** It's a CLI-only slash command; Desktop has a plugin manager UI instead. Typing `/plugin marketplace add ...` into the Desktop app gets you *"`/plugin` isn't available in this environment"* — accurate, but not helpful.
- **Desktop's plugin browser only lists marketplaces you've already added.** This plugin lives in its own marketplace rather than Anthropic's official one, so it won't show up there until you've run the `marketplace add` command above once. That's the only reason a terminal is involved at all.

### Just trying it out

```bash
git clone https://github.com/yahordauksha/claude-window-optimizer.git
cd claude-window-optimizer
claude --plugin-dir "$(pwd)"
```

Loads for that one CLI session only — nothing persists, nothing to uninstall. (CLI only; `--plugin-dir` is a command-line flag.)

### Uninstalling

```bash
claude plugin uninstall claude-window-optimizer@claude-window-optimizer
claude plugin marketplace remove claude-window-optimizer
```

Your four routines aren't removed by this — delete those at [claude.ai/code/routines](https://claude.ai/code/routines).

---

## Commands

| Command | When | What it does |
|---|---|---|
| `/setup-window-optimizer` | Once | Asks what hours you work, creates the four routines |
| `/tune-pings` | Weekly | Retimes them from your actual usage |

Plus two hooks that need no setup: one logs prompt timestamps, one reminds you to tune up after a week.

## What it touches

| | |
|---|---|
| **Writes** | `~/.claude/window-optimizer/` — a timestamp log and small state files |
| **Creates** | 4 Cloud Routines on your account |
| **Sends** | One short message per reset, on the cheapest model — from a fixed pool, fetching nothing |
| **Never touches** | Your prompt content, your tokens, anything else |

---

## For the curious

The design decisions live in [`adr/`](adr/) — ten of them, including the ones I got wrong and had to reverse. The scheduling math is in [`lib/window_optimizer/schedule.py`](lib/window_optimizer/schedule.py), and `python3 tools/measure_anchor_stability.py` reproduces the measurement behind its data-sufficiency guard.

I put this through two rounds of adversarial review by independent agents, told explicitly not to trust the repo's own documentation. Both found real bugs. Several fixes in the history exist because a reviewer proved one of my claims wrong — including the time I'd published a measurement that turned out not to reproduce. One reviewer's own most confident finding was itself wrong and they retracted it, which is in there too. Anything still open is tracked, not quietly dropped.

## License

MIT
