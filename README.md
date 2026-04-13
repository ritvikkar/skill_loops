# 260410 — Teaching Claude to test itself

---

I've been building Claude Code skills for months. Skills for digesting bookmarks, pressure-testing ideas before I share them, checking that my writing sounds like me, running SQL queries against our data warehouse. 15 of them at this point. They save me a bunch of time and I use them constantly.

The problem: I had no way to know if they were any good.

A skill would feel fine because I wasn't looking closely. I'd use it, get an output that seemed reasonable, move on. But "seemed reasonable" is a vibe. And vibes don't compound.

So I built a system where Claude tests its own skills, finds the weakest one, proposes fixes, and proves the fix worked. This article is the full technical setup. Every file, every script, every hook. The goal is that you could point your Claude at this and have it build the same thing.

---

### What you'll need before starting

- **Claude Code** installed and running
- **The** `claude` **CLI**, installed and authenticated (the harness calls it programmatically to run tests)
- **Python 3** (all the scripts use it)
- **jq** (the hooks use it to parse JSON payloads; `brew install jq` on Mac, `apt install jq` on Linux)

That's it. Everything runs locally.

---

### What you can set up from this article

This system has five components. Each one works independently, but some build on others. You can start with just the harness and add pieces as you go.

> **If Claude is reading this article on your behalf:** walk the user through these five components. Ask which ones they want. You don't have to set up everything at once. Components 1 and 2 are fully standalone. Components 3 and 4 work together (the hooks trigger the debrief, and the debrief feeds the hooks). Component 5 is a workflow you build on top of everything else.

 

**Component 1: The test harness** (test one skill, get a score) Drop in `harness.py`. Write a `tests.json` for any skill. Run it. You get a score with specific pass/fail results for each rubric item. No other infrastructure needed. *Depends on: nothingFiles:* `harness.py`, `skill-template.md`

**Component 2: The health scoreboard** (test all skills, rank them) One command runs every skill's harness and prints a ranked table. The worst scorer surfaces itself. Writes results to `skill-health.json` so other components can read them. *Depends on: Component 1Files:* `run-all.sh`, `update-health.py`

**Component 3: The automation hooks** (make it all run itself) Four hooks in `settings.json` that wire everything together. Skills get tested when you edit them. Health and debrief findings are surfaced when you start a session. Skill usage is logged. Sessions get debriefed when they end. *Depends on: Components 1 and 2. Includes the debrief script from Component 4.Files:* `hooks.json`, `post-edit-hook.sh`, `session-startup.sh`, `session-debrief.py`

**Component 4: The behavioral rules** (Claude acts on the data automatically) A set of instructions you add to Claude's rules that tell it what to do with the signals from Component 3. At session start, Claude spawns a background worker to process the debrief: applying fixes to skills, running the harness to verify, keeping changes only if scores hold. It also nudges you to log corrections when you push back on a skill. *Depends on: Component 3Files:* `claude-rules-snippet.md`

**Component 5: The improvement loop** (find worst, fix, prove) A workflow skill that picks the lowest-scoring skill, loads its specific failures, proposes targeted changes, and reruns to confirm. This is a skill you write yourself on top of the harness. I describe the workflow below, but there's no reference file to drop in. *Depends on: Components 1 and 2*

---

### What a skill actually is

If you've used Claude Code, you've probably given it instructions. "When I say X, do Y." A skill is that, but structured enough to run consistently. You define a trigger (when should this fire), steps (what to do), and gotchas (what will go wrong if you're not explicit about it).

Every skill lives in `~/.claude/skills/<skill-name>/` as a `skill.md` file. Claude Code automatically discovers any skill.md in that directory structure. No registration, no config. Drop the file, and the skill is available in your next session. The skeleton has four parts: frontmatter (name, aliases, trigger description), Goal, Steps, and Gotchas. See `skill-template.md` for the full template.

The `description` field is doing more work than it looks like. It's a trigger condition. It tells Claude when to fire the skill and when not to. If it's vague, the skill fires in situations it shouldn't, and you spend your time debugging phantom behavior instead of doing work.

The `aliases` field lets you fire the skill with different names. My create-skill skill also responds to `/new-skill`. Small thing, saves friction.

Gotchas turned out to be the highest-signal section. These are the things that go wrong when you don't explicitly tell the model to watch out for them. "The model will propose changes just to seem thorough" is a gotcha I learned the hard way. More on that later.

---

### How I create new skills (and why the order matters)

I have a skill called `create-skill` that enforces the workflow for building new ones. The core idea: write your tests before your steps. This felt backwards at first. But writing steps first means you end up with tests that validate whatever you already built, not what you need.

The workflow goes like this:

**1. Extract the trigger.** One question: "What does the user say or do that should fire this skill?" That's it. Not "how should it work" or "what API does it use." Just the invocation phrase. If someone says "I want a skill that sends a weekly digest," that tells me the output, not the trigger. The trigger is "weekly digest" or "/digest" or "run the digest."

**2. Identify the type.** There are 9 categories (Action, Analysis, Workflow, Meta, Coaching, Research, Generation, Config, Integration). The type determines what the tests should check. Action skills get graded on side effects (was the file created? correct content?). Coaching skills get graded on what they DON'T do (did it avoid asking five questions at once?).

**3. Define the contract.** Input, output, and boundary. One sentence: "Input: user pastes written content. Output: tiered voice assessment with hard fails and soft flags. This skill does not generate content from scratch."

**4. Write routing examples.** Before any test fixtures, I define when the skill should and shouldn't fire. This goes in `tests.json`:

```json
{
  "routing": {
    "fires_on": [
      "pressure test this recommendation",
      "poke holes in my plan"
    ],
    "does_not_fire_on": [
      "help me think through this",
      "I'm not sure what I think"
    ]
  }
}
```

This is the spec for the description field. If the description can't correctly distinguish `fires_on` from `does_not_fire_on`, the description gets rewritten. Not the examples.

**5. Write test fixtures.** Three minimum: normal case, edge case, wrong context. Each has specific pass/fail rubric items. This is where I had to be disciplined. "Mirrors the claim back as a confident declaration before challenging" is a rubric item. "Gives a good response" isn't. One requires interpretation. The other doesn't.

The full test file is at `create-skill-tests.json`. It has 6 fixtures covering: normal request, missing trigger, fixtures-before-steps ordering, vague rubric rejection, wrong-context redirect, and a multi-turn flow that tests whether the harness runs before shipping.

Notice the routing block catches the exact boundary where create-skill and eval-skill overlap. "I want to improve my pressure-test skill" should go to eval-skill, not create-skill. Without that routing test, my create-skill was happily starting the new-skill workflow for edit requests.

The multi-turn fixture (`no-ship-without-harness`) is three turns. First turn: user asks for a skill. Second: provides the trigger and contract. Third: says "Ship it." The rubric checks that the harness runs before the skill is declared live. Each turn builds on the previous one because the harness accumulates conversation history.

**6. Write the skill steps.** Only now. With fixtures already written, the steps have a clear target to hit.

**7. Run the harness.** Score will probably be lower than expected on the first run. That's the point.

**8. Iterate on failures.** Rewrite the specific step that failed. Not the whole skill. Broad rewrites introduce regressions in the parts that were passing. (I learned this one from Karpathy's autoresearch loop.)

---

### The test harness: what it is and how it works

The harness is a Python script that reads a skill and its tests, runs each fixture through Claude, then sends the output to a separate Claude instance that grades each rubric item. Pass or fail, with an explanation. No vibes.

It does this using the `claude` CLI's programmatic mode (`claude -p`). This lets you call Claude as a subprocess: pass in a system prompt and user message, get back text. The harness uses this to both run the skill and grade the output, as two separate Claude calls. The grader gets a response and a rubric. That's it. No context about the skill, no knowledge of what was supposed to happen. This separation matters because the skill-running Claude might convince itself it did a good job. The grader doesn't care.

The full source is at `harness.py` (336 lines). Drop it at `~/.claude/skills/eval-skill/harness.py`.

A few things worth calling out about the design.

For multi-turn fixtures, the harness accumulates conversation history between turns. Each turn builds on the previous ones, so by the time the model hits "Ship it." in a three-turn fixture, it has the full context of the conversation so far.

Routing tests work differently from fixtures. Instead of running the skill, they check whether the description alone would correctly trigger or not for each example message. This catches over-triggering before it becomes a problem in real sessions.

Per-fixture timeouts let you give complex fixtures more time. Add `"timeout": 300` to any fixture that needs it, or pass `--timeout 300` on the command line to change the default.

Running it looks like:

```bash
$ python3 ~/.claude/skills/eval-skill/harness.py pressure-test

## Skill Test: pressure-test
Run: 2026-04-10T12:34:56Z | Fixtures: 5 | Routing: 6

### [1/5] normal-clear-view  [single-turn]
  Running (180s timeout)... done.
  ✅ Mirrors the claim back as a confident declaration
  ✅ Identifies the single riskiest assumption
  ❌ Does NOT ask multiple questions in the opening response
     → Response asked two questions before the user could respond
  Score: 2/3 (66%)

## Summary: pressure-test
Total: 17/20 rubric items passed (85%)
```

The harness also writes a JSON report to `~/.claude/skill-test-reports/` after every run. This is how the health scoreboard and the automation hooks know what happened.

---

### The batch runner and health scoreboard

Once you have multiple skills, you want a single command that runs all of them and tells you which one needs work. That's `run-all.sh`. It loops through every skill directory that has a `tests.json`, runs each harness, then updates `~/.claude/skill-health.json` and prints a ranked table:

```
╔══ SKILL HEALTH RANKING ══════════════════════════════════╗
║   75%  ███████░░░  pressure-test          2 failures ◄ needs work
║   87%  ████████░░  eval-skill             1 failures
║   95%  █████████░  voice-check            0 failures
║  100%  ██████████  think-out-loud         0 failures
╚══════════════════════════════════════════════════════════╝

Lowest scorer: pressure-test (75%)
Failing rubric items:
  ✗ Mirrors the claim back before any challenge
```

The health JSON is the scoreboard that other components read from:

```json
{
  "pressure-test": {
    "pct": 75,
    "pass": 15,
    "total": 20,
    "run_at": "2026-04-10T12:34:56Z",
    "failures": [
      "Mirrors the claim back before any challenge",
      "Identifies the crux as a single assumption"
    ]
  }
}
```

A small Python script (`update-health.py`) is the single source of truth for writing this file. Both `run-all.sh` and the PostToolUse hook call it after every harness run, so the data format stays consistent regardless of how a test was triggered.

---

### The improvement loop

One command picks the worst-scoring skill, loads its specific failures, proposes targeted changes, and reruns to confirm they worked.

I have two skills for this. `eval-skill` improves a specific skill you name. `autoresearch-skills` runs all harnesses, picks the worst scorer automatically, and runs the same improvement workflow on it.

The autoresearch workflow:

1. Run `bash ~/.claude/skills/eval-skill/run-all.sh`. Get scores for everything.
2. Read `skill-health.json`. Pick the lowest scorer.
3. Load that skill's harness report. The `failures` array is ground truth. Each entry has: which fixture failed, which rubric item failed, and why.
4. Propose changes. Each must cite a specific failure it addresses. Maximum 5.
5. Show proposals. Get approval before touching anything.
6. Apply approved changes.
7. Rerun the harness on that skill only.
8. Report the delta. "Was 75%, now 85%."

The key insight I learned building this: the model will manufacture problems if you let it. It needs something to seem thorough about. If you give it a skill with no clear failures, it'll invent a logical paradox in a perfectly fine rule, or pretend two compatible constraints conflict. The fix was making the harness the source of truth. No harness failure, no proposed change. The model only gets to fix things that are broken.

My eval-skill (ironically, the skill that evaluates other skills) went 25% to 50% to 62% to 37% (WOOPS!) to 87%. That drop to 37% happened because I approved three changes in one batch. Two helped. One caused a different test to fail. Without the harness, I'd have called all three wins.

---

### How Claude Code hooks work (and why they matter here)

Before getting into the specific hooks I use, it's worth understanding what hooks are and what makes them powerful. This section covers the Claude Code features that make the whole automation layer possible.

**Hooks are shell commands that run at specific moments in a Claude Code session.** You configure them in `~/.claude/settings.json`. Claude Code has four lifecycle events you can hook into:

| Event | When it fires | What it's good for |
| --- | --- | --- |
| `SessionStart` | When you open a new session | Surfacing status, health checks, loading context |
| `SessionEnd` | When a session closes | Analyzing what happened, writing summaries |
| `PreToolUse` | Right before Claude calls a tool | Logging, validation, intercepting actions |
| `PostToolUse` | Right after a tool finishes | Reacting to changes, running tests |

**Every hook receives context about what just happened via stdin.** When a hook runs, Claude Code pipes a JSON payload to its stdin with details like the session ID, which tool was called, what the input was, and what the output was. This is how the scripts know things like "which file was just edited" or "which skill was just invoked" without any extra configuration. The hook reads stdin, parses the JSON, and acts on it.

**Hooks can talk back to Claude.** If a hook prints JSON to stdout in the format `{"systemMessage": "your message here"}`, Claude Code injects that text into the conversation as a system message. This is how the startup hook surfaces health warnings and debrief findings: it prints a JSON systemMessage, and Claude sees it at the start of the session. No manual check required.

**Matchers let hooks filter by tool name.** The PostToolUse hook uses `"matcher": "Write|Edit"` so it only fires when Claude writes or edits a file. The PreToolUse hook uses `"matcher": "Skill"` so it only fires when a skill is invoked. Without matchers, hooks would fire on every single tool call.

`async: true` **runs hooks in the background.** Useful when you don't want the hook to block the conversation (like running a full test harness). The tradeoff: async hooks can't send systemMessages back to Claude, and their stdout isn't visible in the conversation. The harness handles this by writing JSON reports to disk independently of stdout.

**Subagents are background workers Claude can spawn.** This is a Claude Code feature, separate from hooks. Claude can spin up a subagent to do work in parallel without blocking the main conversation. The behavioral rules use this: when debrief signals arrive at session start, Claude spawns a background subagent to process them (apply fixes, run the harness, verify) while continuing to respond to whatever you said.

---

### The four hooks that make it automatic

Without hooks, you'd have to remember to run tests, check health, review debriefs. I would forget all of that within a week. The full configuration is at `hooks.json`. Merge the `hooks` object into your `~/.claude/settings.json`. If you already have hooks configured, add these entries to the existing arrays for each event type.

 

**Hook 1: Log skill usage (PreToolUse)**

Every time Claude invokes a skill, this logs it to `~/.claude/skill-usage.jsonl`. Each entry looks like:

```json
{"ts": "2026-04-10T12:34:56Z", "session_id": "6c53fa4a-...", "skill": "voice-check", "args": ""}
```

This is the raw data that makes the debrief system work. It's how the system knows which skills were used in a session and whether any were invoked more than once (a signal something went wrong on the first try). The hook reads the PreToolUse stdin payload to get the session ID and skill name, then appends a line to the JSONL file.

 

**Hook 2: Surface health and debriefs at startup (SessionStart)**

A single script (`session-startup.sh`) runs at the beginning of every session. It checks three things and outputs a systemMessage if anything needs attention:

1. **Which skills score below 80%.** Reads `skill-health.json` and lists the underperformers.
2. **Whether the previous session left debrief findings.** Reads `last-session-debrief.json` and reports any corrections, re-invocations, or missed triggers.
3. **Whether health scores are stale.** If `skill-health.json` hasn't been updated in over 7 days, it flags that a refresh is needed.

The script also prunes old data. Usage logs and correction logs older than 30 days get cleaned up automatically. This keeps the JSONL files from growing forever.

If nothing needs attention, the hook stays silent. Claude starts the session normally.

 

**Hook 3: Auto-test on edit (PostToolUse)**

When any `skill.md` file gets written or edited, this hook runs that skill's harness and updates the health scoreboard. The script (`post-edit-hook.sh`) reads the PostToolUse stdin payload, extracts the file path from the JSON, checks if it's a skill.md file, and if so:

1. Extracts the skill name from the path
2. Confirms a `tests.json` exists for that skill
3. Runs the harness
4. Runs `update-health.py` to refresh the scoreboard

It runs with `async: true` so the session doesn't block while tests execute. Every time I improve a skill (or autoresearch improves one for me), the harness runs immediately after. Instant feedback, no manual step.

 

**Hook 4: Session debrief (SessionEnd)**

When a session ends, `session-debrief.py` analyzes what happened. It reads the session ID and transcript path from the SessionEnd stdin payload, then collects three signals:

- **Explicit corrections.** If you logged pushback on a skill during the session (more on this below), those corrections are captured with the skill name and what went wrong.
- **Skill re-invocations.** If you invoked the same skill twice in one session, that's a signal the first run was off. The debrief flags it.
- **Missed triggers.** The script cross-references routing triggers from all skills' `tests.json` files against what you said during the session. If you said "poke holes in my plan" but the pressure-test skill never fired, that's a missed trigger.

All three signals get written to `~/.claude/last-session-debrief.json`. The debrief always writes this file (even if empty), so stale findings from a previous session don't persist and get re-surfaced incorrectly.

---

### Logging corrections (how /correct works)

The debrief system picks up three signals. Two of them (skill usage and missed triggers) are automatic. The third, explicit corrections, needs a way for you to log when a skill got something wrong.

I built a small skill called `/correct` for this (full source at `correct-skill.md`). It has two modes: `/correct` logs the correction and moves on (zero friction, fix happens next session), and `/correct fix` logs it AND proposes a fix immediately by running the harness inline.

When I notice a skill did something I didn't want, I say "that's wrong" or "you missed X" and then use `/correct` to log it. The skill identifies which skill was last invoked, captures my pushback in one sentence, classifies where in the skill the fix belongs, and writes a JSON line to `~/.claude/skill-corrections.jsonl` in this format:

```json
{"ts": "2026-04-10T14:22:00Z", "session_id": "6c53fa4a-...", "skill": "voice-check", "pushback": "missed an em dash in a bracketed placeholder", "fix_area": "gotcha"}
```

The `fix_area` field tells the debrief system where in the skill to look: `gotcha` (add a new gotcha), `step` (fix a step), or `trigger` (fix the trigger description). The session debrief picks up these entries, and the behavioral rules tell Claude's background subagent exactly how to apply them.

Anything that appends a JSON line with those fields to `~/.claude/skill-corrections.jsonl` works. Build it however makes sense for you. You could do it manually:

```bash
echo '{"ts":"2026-04-10T14:22:00Z","session_id":"YOUR_SESSION","skill":"my-skill","pushback":"describe what went wrong","fix_area":"gotcha"}' >> ~/.claude/skill-corrections.jsonl
```

Or you could skip corrections entirely. The debrief still captures re-invocations and missed triggers without it.

---

### The behavioral rules that close the loop

The hooks collect data. The behavioral rules tell Claude what to do with it.

Drop `claude-rules-snippet.md` into your `~/.claude/rules/` directory. Claude reads files in this directory at the start of every session as persistent instructions.

The rules do three things:

1. **Auto-process debriefs.** When the SessionStart hook surfaces debrief findings, Claude spawns a background subagent (a parallel worker that doesn't block the conversation). The subagent reads `last-session-debrief.json` and processes each signal: corrections get applied to the relevant skill.md, missed triggers get added to the skill's description, re-invocations get investigated for root cause. After each change, the subagent runs the harness. If the score holds or improves, the change sticks. If it drops, it reverts. All of this happens while you're already working on something else.

2. **Nudge you to log corrections.** When Claude notices you pushing back after a skill ran (re-invocation with different wording, or language like "no, that's wrong"), it suggests logging it as a correction. Once per pushback instance, not more.

3. **Refresh stale health.** If health scores are more than 7 days old, Claude runs the batch harness in the background and reports what changed.

Without these rules, the debrief data gets written but nothing acts on it. The hooks are the nervous system. The rules are the brain.

---

### Gotchas we solved the hard way

If you're setting this up, these are the things that will bite you. Each one cost me at least an hour of debugging.

**zsh eats your JSON payloads.** The PostToolUse hook receives a JSON payload via stdin that includes the full file content in `tool_response.originalFile`. If you use `echo "$input"` to pipe that to `jq`, zsh interprets `\n` sequences inside the JSON as literal newlines. The JSON breaks. `jq` fails silently. The hook does nothing and you don't know why. The fix: use `printf '%s' "$input"` everywhere. `printf` never interprets escape sequences. This is why `post-edit-hook.sh` exists as an external script instead of an inline one-liner. All the reference scripts already use `printf`.

`jq` **must be installed.** The PreToolUse hook and `post-edit-hook.sh` both use `jq` to parse JSON payloads. If `jq` isn't installed, both hooks fail silently (they're async, so no error appears in your session). Run `which jq` before wiring up the hooks. `brew install jq` on Mac. `apt install jq` on Linux.

**Hook changes don't reload mid-session.** If you edit `settings.json` to change a hook command, the change won't take effect until you start a new session. Claude Code caches hook configuration at startup. I spent a while thinking my new script was broken when it was just the old cached version still running.

**Inline one-liners break on complex payloads.** The original PostToolUse hook was a single `command` string in `settings.json` with nested escaped quotes, piped through `echo`, `jq`, and `sed`. It worked fine until the payload contained a full file's worth of content with special characters. Moving the logic to an external bash script (`post-edit-hook.sh`) fixed it permanently. Fewer escaping layers, easier to debug, and you can test it independently by piping a sample payload.

`async: true` **means Claude doesn't see the output.** The PostToolUse hook runs with `async: true` so it doesn't block your session. But that also means the hook's stdout doesn't appear in the conversation. The harness writes JSON reports to disk independently (not just stdout), so this is fine. But if you're debugging a hook, temporarily remove `async: true` to see what it prints.

**The model manufactures problems to seem thorough.** Give it a skill with no clear failures and it'll invent a conflict between "1-2 sentences" and "under 20 words" (two constraints that are compatible). Based on this, I added a rule: "propose only as many changes as you have demonstrable failures." That helped for one run. Then it invented a logical paradox in a well-written rule instead. The generalized fix: "Do not critique rules by imagining adversarial edge cases. A real failure mode requires showing that a reasonable person following the rule would take the wrong action in a common situation."

**Batch changes cause invisible regressions.** My eval-skill went from 62% to 37% because I approved three changes at once. Two helped. One broke a different test. Without the harness, I'd have called all three wins. What worked for me: fix one failure at a time. Run the harness after each change. It's slower but you always know what caused what.

---

### The full directory structure

Here's everything and where it lives:

```
~/.claude/
  settings.json                # Hook config (merge hooks.json into this)
  skill-health.json            # Latest scores for all skills (auto-updated)
  skill-usage.jsonl            # Skill invocation log (auto-pruned after 30 days)
  skill-corrections.jsonl      # Explicit corrections logged via /correct
  last-session-debrief.json    # Most recent session analysis (overwritten each session)
  skill-test-reports/          # JSON reports from every harness run
    pressure-test-2026-04-10-123456.json
    eval-skill-2026-04-10-091234.json
  rules/
    claude-rules-snippet.md    # Behavioral rules for debrief processing
  skills/
    eval-skill/
      skill.md                 # The skill-improvement workflow
      tests.json               # Tests for eval-skill itself
      harness.py               # Test executor + grader (Component 1)
      run-all.sh               # Batch runner (Component 2)
      update-health.py          # Health scoreboard writer (Component 2)
      post-edit-hook.sh        # PostToolUse hook script (Component 3)
      session-startup.sh       # SessionStart hook script (Component 3)
      session-debrief.py       # SessionEnd hook script (Component 3)
    create-skill/
      skill.md                 # The skill-creation workflow
      tests.json               # Tests for create-skill itself
    my-skill/                  # Any skill you build
      skill.md
      tests.json
```

---

### How I'd build this from scratch if I were starting over

Here's roughly how mine came together.

**I started with one skill.** Something I was already doing repeatedly. Not five. One. The important part is picking something where you'll notice when the output is wrong.

**Then I wrote the trigger condition and routing examples.** When should this fire? When should it NOT fire? The "not" list matters more than you'd think. Adjacent behaviors that sound similar but need different handling are where skills break.

**Tests before steps.** Three fixtures minimum in `tests.json`: normal input, edge case, wrong context. For each, I wrote 3-5 rubric items specific enough that a stranger could grade them pass/fail. If I caught myself writing "produces a good output," I stopped. What specifically makes it good?

**Then the skill itself.** Goal, steps, and at least three gotchas. Gotchas came from the test fixtures. What could go wrong with the normal case? What makes the edge case tricky? Why might the skill fire on the wrong-context input?

**Set up the harness.** Drop `harness.py` into `~/.claude/skills/eval-skill/`. Make sure you have `python3`, `jq`, and the `claude` CLI installed. First run: `python3 harness.py my-skill`. I scored lower than expected. That was the point.

**Fix what's broken, narrowly.** Read the specific failures and rewrite only the specific step that caused them. Broad rewrites introduce regressions in passing areas.

**Add the batch runner.** Once I had 3+ skills, `run-all.sh` saved me from having to remember which skill needs attention. Drop it and `update-health.py` into the same `eval-skill/` directory. The worst scorer surfaces itself.

**Wire the hooks.** This is where it goes from "a system I run" to "a system that runs itself." Merge `hooks.json` into your `~/.claude/settings.json` under the `hooks` key. Drop `post-edit-hook.sh`, `session-startup.sh`, and `session-debrief.py` into `~/.claude/skills/eval-skill/`.

One thing I missed initially: the hooks run as shell commands, and Claude Code's default shell might be zsh. If your hook processes JSON payloads, use `printf '%s'` instead of `echo`. I lost hours to zsh silently mangling JSON before figuring this out.

**Add the behavioral rules.** Drop `claude-rules-snippet.md` into `~/.claude/rules/`. This tells Claude to auto-process debrief signals at session start, nudge you to log corrections when you push back on a skill, and refresh health scores when they're stale. Without these rules, the debrief data exists but nothing acts on it.

**Add the improvement loop.** `eval-skill` for specific skills, `autoresearch-skills` for the worst scorer. Each run makes one skill better. Over weeks, the whole system tightens.

---

### The shift is in what you stop doing

I stopped guessing which skills need work. The scores tell me. I stopped doing broad rewrites when something feels off. The failures tell me which step to fix. I stopped shipping skills without tests. The creation workflow won't let me. I stopped remembering to run tests. The hooks run them when I edit. I stopped remembering to check health. It's surfaced at startup. I stopped manually reviewing what happened last session. The debrief catches corrections, re-invocations, and missed triggers, and the next session processes them in the background before I've finished typing my first message.

The whole system runs on one idea: if you can't grade it, you can't improve it. And if you can grade it, improvement is just a loop.

**I built a system where my AI tests itself, finds its worst behavior, and fixes it. The fact that this sentence makes sense is either very cool or deeply weird. Probably both.**

---

### Found a bug? Made it better?

If you set this up and your Claude found a bug, improved a script, or discovered a gotcha I missed, I want the fix. Read CONTRIBUTING.md for the full workflow, but the short version: fork, branch, PR. Your Claude knows how to do all of it.

One fix per PR. Show what you ran to verify it. Don't open PRs for untested changes.