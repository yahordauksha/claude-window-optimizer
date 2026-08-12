# Claude Window Optimizer

**Stop wasting your Claude Code usage window on a 7am "quick question."**

A plugin that resets your 5-hour usage window on *your* schedule, so it's full when you sit down to work — not half-spent because you asked something trivial before breakfast.

```
/plugin marketplace add yahordauksha/claude-window-optimizer
/plugin install claude-window-optimizer@claude-window-optimizer
/setup-window-optimizer
```

One question, one confirmation, done. Works in the CLI and the Desktop app.

---

## The problem

Claude Code gives you a usage allowance on a 5-hour window. That window **starts with your first message** — whatever it happens to be.

So this happens:

```
07:12   "hey, quick one — what's the syntax for X?"
        └── your 5-hour window quietly starts here
09:00   you actually sit down to work
11:30   you're deep in something good
12:12   ✗ window expires. you're out, mid-thought.
```

You spent your window on a one-liner and a shower. The rest of your day gets shaped by a question you don't even remember asking.

The usual workaround is one scheduled ping in the morning. That's what this plugin's author ran for weeks — and it's exactly what made him build this, because a single 7am ping just relocates the problem to noon.

## The fix

Four scheduled resets a day, spaced so a fresh window is always close by:

```
08:00   ● reset   ── window is full when you start
13:10   ● reset   ── full again for the afternoon
18:20   ● reset
23:30   ● reset
```

The boundaries land where you chose them, instead of wherever your first message fell. And when you do burn through a window, the next one is minutes away instead of hours.

## What setup actually looks like

It asks one question, and shows you exactly what each answer produces:

```
What hours do you usually work?

  1. 09:00–17:00     Window resets at 07:50, 13:00, 18:10, 23:20
  2. 08:00–18:00     Window resets at 07:50, 13:00, 18:10, 23:20
  3. 20:00–01:00     Window resets at 17:20, 22:30, 03:40, 08:50
  4. Something else
```

It asks about your day rather than asking you to pick reset times, because
the best reset times aren't where you'd guess. Notice option 1 puts a reset
at 13:00 — *inside* the working day. That's deliberate: a reset at 09:00 would
leave your whole morning-to-evening block riding on a single window.

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

A reset works because *a message was sent* — the content is irrelevant to the mechanism. So each routine sends one short, self-contained line drawn from a [fixed pool](lib/window_optimizer/ping_content.py): a stretch reminder, a posture check, "reply with just 'ok'". Four different ones, so your Routines list isn't four identical robots.

They fetch nothing and are granted no tools at all. An earlier version had them read your GitHub repo's open issue titles — which meant an unattended agent was reading text any stranger could write by filing an issue, in exchange for nothing the mechanism needed. [ADR-0010](adr/0010-fixed-safe-prompt-pool.md) has the full story.

### The weekly tune-up

The plugin ships a hook that notes **when** you send prompts. Timestamps only — never content, never tokens. After a few weeks that's a picture of your real working rhythm.

Run `/tune-pings` and it shifts your four resets to whatever spreads your actual usage most evenly across the four windows:

```
Window resets: 05:36, 10:46, 15:56, 00:26  (was 08:00, 13:10, 18:20, 23:30)
Based on 23 days / 412 prompts, last 28 days
```

The goal isn't to match when you start work — it's to stop any single window carrying a disproportionate share of your day. If your heavy block is 9am–1pm, you actually *want* a reset landing at 10:46, splitting that work across two budgets instead of leaving it all on one.

You'll get a nudge to run it after 7 days. It refuses to act on thin data rather than shuffling your schedule around noise.

---

## Honest limitations

Worth knowing before you install. All of these are covered in more depth in [`adr/`](adr/).

**The core mechanic isn't documented by Anthropic.** That a scheduled message opens a fresh window comes from operational use — two hand-made routines run for weeks, windows observed starting at the ping times — not from any official source. You can check it yourself in about five hours: send a message, note the reset time, send another once the window expires, see whether the reset time follows. Everything here rests on this.

**It counts prompts, not tokens.** Hooks don't expose token counts, so a one-word question weighs the same as a 50-file refactor. Prompt volume is a proxy, and it's the only one available.

**It won't help everyone equally.** Measured on simulated window dynamics (`tools/window_sim.py`): a concentrated evening block gains ~31%, a 9-5 day ~15%, and someone working fifteen hours straight gains ~1% — they already chain fresh windows naturally. If your day has no idle gaps, this isn't for you.

**The weekly cap still exists.** Session and weekly allowances are consumed at the same time. This plugin does nothing about the weekly one.

**Routines can't be deleted through the API.** Setup creates four; removing them is a manual step at [claude.ai/code/routines](https://claude.ai/code/routines). That's the real cost of installing.

---

## Install

### CLI or Desktop

Same two steps in both — `/plugin` in the CLI, the plugin browser in Desktop:

```
/plugin marketplace add yahordauksha/claude-window-optimizer
/plugin install claude-window-optimizer@claude-window-optimizer
```

Then run `/setup-window-optimizer` once.

### Just trying it out

```bash
git clone https://github.com/yahordauksha/claude-window-optimizer.git
cd claude-window-optimizer
claude --plugin-dir "$(pwd)"
```

Loads for that session only. Nothing persists, nothing to uninstall.

---

## Commands

| Command | When | What it does |
|---|---|---|
| `/setup-window-optimizer` | Once | Asks your reset time, creates the four routines |
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

The design decisions live in [`adr/`](adr/) — eight of them, including the ones that turned out wrong and got reversed. The scheduling math is in [`lib/window_optimizer/schedule.py`](lib/window_optimizer/schedule.py), and `python3 tools/measure_anchor_stability.py` reproduces the measurement behind its data-sufficiency guard.

This project has been through two rounds of adversarial review by independent agents told explicitly not to trust its own documentation. Both found real bugs, and several fixes in the history exist because a reviewer proved a claim wrong — including one round where the reviewer's own most confident finding was itself wrong, and they retracted it. Open findings are tracked rather than quietly dropped.

## License

MIT
