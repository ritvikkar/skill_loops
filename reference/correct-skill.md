# /correct — Log Skill Corrections

## Goal

Capture explicit user corrections on skill output as high-confidence signal for
the session debrief pipeline. Corrections are the strongest signal that a skill
needs improvement: the user said "this was wrong."

## Triggers

`/correct`, `correction:`, "that's a correction", "log this as a correction"

## Two Modes

- **`/correct`** — Log only. Zero friction. Fix happens next session.
- **`/correct fix`** — Log AND propose a fix right now (runs eval-skill inline).

## Steps

1. **Identify the skill.** Look at conversation context for the most recently
   invoked skill (the last Skill tool call). If no skill was invoked in this
   conversation, ask: "Which skill is this correction for?" Do not guess.

2. **Capture the pushback.** Read the user's messages between the skill output
   and the `/correct` invocation. This is the correction content: what went
   wrong, what was missed, what should have been different.

3. **Classify the fix area.** Determine which part of the skill needs fixing:
   - `trigger` — skill didn't fire when it should have, or fired when it shouldn't
   - `step` — skill fired but executed a step incorrectly or missed a step
   - `gotcha` — skill missed a known edge case or blindspot
   - `unknown` — unclear what needs fixing (log it anyway, debrief pipeline will triage)

4. **Log to JSONL.** Append one JSON line to `~/.claude/skill-corrections.jsonl`:
   ```json
   {
     "ts": "ISO-8601 UTC timestamp",
     "session_id": "current session ID",
     "skill": "skill-name",
     "pushback": "the user's correction text, summarized to one sentence",
     "fix_area": "trigger|step|gotcha|unknown"
   }
   ```
   Use the Bash tool to append. Create the file if it doesn't exist.

5. **Acknowledge.** One line only: "Logged for {skill}. Will improve next session."

6. **If `/correct fix` mode:** After logging, also:
   - Read `~/.claude/skills/{skill}/skill.md`
   - Propose a specific edit that addresses the correction
   - Run `python3 ~/.claude/skills/eval-skill/harness.py {skill}` to verify
   - Show the proposed change and harness result
   - Apply if the user approves

## Gotchas

- **Don't guess the skill.** If there's ambiguity about which skill the
  correction targets, ask. A correction logged against the wrong skill is
  worse than no correction at all.

- **Summarize, don't dump.** The pushback field should be one clear sentence,
  not a raw paste of the conversation. The debrief pipeline needs signal,
  not noise.

- **Log-only mode is the default.** `/correct` without `fix` should be
  instantaneous: log and acknowledge. No reading skill files, no running
  harness, no proposing changes. The point is zero-friction capture.

- **Session ID is required.** The JSONL entry must include session_id so the
  debrief pipeline can filter by session. Get it from the conversation context.

- **Don't edit tests.json.** Even in `/correct fix` mode, corrections only
  modify skill.md. If the correction reveals a new test case, suggest it to
  the user but don't add it automatically. Tests are human-only.
