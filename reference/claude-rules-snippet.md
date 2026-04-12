# Claude Rules Snippet for Skill Loop Automation

Add this to your `~/.claude/rules/personal.md` (or any global rules file).
These behavioral instructions tell Claude how to act on the signals surfaced
by the SessionStart hook and the session debrief system.

---

## Session Startup

At the start of every session:
1. If startup context includes debrief data from `last-session-debrief.json`, spawn a BACKGROUND subagent to process it (see debrief routine below). Handle the user's message immediately. Never block the user for debrief processing.

### Skill debrief routine

When `session-startup.sh` surfaces debrief data at startup:

1. Spawn a **BACKGROUND** subagent. Handle the user's message immediately.
   The subagent runs in parallel. Never block the user.

2. The subagent reads `~/.claude/last-session-debrief.json` and processes each signal:
   - **corrections**: read the skill's `skill.md`, apply the fix per `fix_area`
     (gotcha/step/trigger). Run `python3 ~/.claude/skills/eval-skill/harness.py <skill>`.
     Keep if score holds or improves. Revert if it drops.
   - **re_invoked skills**: read `skill.md`, look for what might cause repeat usage.
     If a clear fix exists, apply and verify with harness. If unclear, skip.
   - **missed_triggers**: read `skill.md`, add the missed phrase to the trigger
     description. Run harness. Keep if routing score holds. Revert if it drops.

3. Auto-apply changes to `skill.md`. NEVER change `tests.json` without asking the user.

4. When the subagent completes:
   - Changes made: one line. "Applied: voice-check gotcha fix (87% -> 92%)".
   - New fixture warranted: "New use case for voice-check: [desc]. Add test fixture?"
   - Nothing actionable: say nothing.

5. If health scores are >7 days stale, run `bash ~/.claude/skills/eval-skill/run-all.sh --quiet`
   in background. One line when done: "Health refresh complete. N improved, M regressed."

### Correction nudge behavior

When you notice the user pushing back after a skill ran (re-invocation with
different wording, or clear correction language like "no, that's wrong" or
"you missed X"), suggest: "Log as skill correction? `/correct`"

Build the habit over time. Don't nag: suggest once per pushback instance.
