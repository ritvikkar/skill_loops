#!/bin/bash
# session-startup.sh — Single SessionStart hook.
# Replaces check-health.sh + check-debriefs.sh.
# Outputs at most one-two lines as JSON systemMessage. Silent if nothing to report.
# Data only — no instructions. Behavioral instructions live in personal.md.

HEALTH_FILE="$HOME/.claude/skill-health.json"
DEBRIEF_FILE="$HOME/.claude/last-session-debrief.json"
USAGE_JSONL="$HOME/.claude/skill-usage.jsonl"
CORRECTIONS_JSONL="$HOME/.claude/skill-corrections.jsonl"

# --- Prune JSONL files older than 30 days ---
prune_jsonl() {
    local file="$1"
    [ -f "$file" ] || return
    local cutoff
    cutoff=$(python3 -c "
from datetime import datetime, timedelta, timezone
print((datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
" 2>/dev/null) || return
    python3 -c "
import json, sys
cutoff = '$cutoff'
kept = []
for line in open('$file'):
    line = line.strip()
    if not line:
        continue
    try:
        entry = json.loads(line)
        if entry.get('ts', '') >= cutoff:
            kept.append(line)
    except json.JSONDecodeError:
        continue
with open('$file', 'w') as f:
    for line in kept:
        f.write(line + '\n')
" 2>/dev/null
}

prune_jsonl "$USAGE_JSONL"
prune_jsonl "$CORRECTIONS_JSONL"

# --- Collect signals ---
python3 << 'PYEOF'
import json, os, time
from pathlib import Path

parts = []

# Signal 1: Skills below 80%
health_file = Path.home() / ".claude" / "skill-health.json"
stale_days = 0
if health_file.exists():
    try:
        data = json.loads(health_file.read_text())
        bad = [(s, v["pct"]) for s, v in data.items() if v.get("pct", 100) < 80]
        if bad:
            items = ", ".join(f"{s} ({p}%)" for s, p in sorted(bad, key=lambda x: x[1]))
            parts.append(f"Skills < 80%: {items}")

        # Check staleness
        mtime = health_file.stat().st_mtime
        stale_days = (time.time() - mtime) / 86400
    except (json.JSONDecodeError, KeyError, OSError):
        pass

# Signal 2: Last session debrief
debrief_file = Path.home() / ".claude" / "last-session-debrief.json"
if debrief_file.exists():
    try:
        debrief = json.loads(debrief_file.read_text())
        findings = []

        corrections = debrief.get("corrections", [])
        if corrections:
            skills = ", ".join(set(c["skill"] for c in corrections))
            findings.append(f"{len(corrections)} correction(s) ({skills})")

        re_invoked = [s for s in debrief.get("skills_used", []) if s.get("re_invoked")]
        if re_invoked:
            skills = ", ".join(s["skill"] for s in re_invoked)
            findings.append(f"{len(re_invoked)} re-invoked ({skills})")

        missed = debrief.get("missed_triggers", [])
        if missed:
            skills = ", ".join(m["skill"] for m in missed)
            findings.append(f"{len(missed)} missed trigger(s) ({skills})")

        if findings:
            parts.append("Last session: " + ", ".join(findings))
    except (json.JSONDecodeError, KeyError, OSError):
        pass

# Signal 3: Stale health scores
if stale_days > 7:
    parts.append(f"Health scores {int(stale_days)} days stale — run refresh")

# Output
if parts:
    msg = " | ".join(parts)
    print(json.dumps({"systemMessage": msg}))
PYEOF
