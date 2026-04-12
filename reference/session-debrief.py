#!/usr/bin/env python3
"""
session-debrief.py v2 — End-of-session skill analysis.

Called by the SessionEnd hook. Reads three signals:
1. Explicit corrections from skill-corrections.jsonl
2. Skill usage from skill-usage.jsonl
3. Missed triggers from tests.json routing.fires_on arrays

Writes a single file: ~/.claude/last-session-debrief.json (overwrite).
All errors logged to ~/.claude/skill-debrief-errors.log.
"""

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

SKILLS_DIR = Path.home() / ".claude" / "skills"
CORRECTIONS_JSONL = Path.home() / ".claude" / "skill-corrections.jsonl"
USAGE_JSONL = Path.home() / ".claude" / "skill-usage.jsonl"
DEBRIEF_FILE = Path.home() / ".claude" / "last-session-debrief.json"
ERROR_LOG = Path.home() / ".claude" / "skill-debrief-errors.log"


def log_error(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with open(ERROR_LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def read_stdin_payload() -> dict:
    """Read hook stdin payload: {session_id, transcript_path, ...}."""
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def get_corrections(session_id: str) -> list[dict]:
    """Read explicit corrections for this session from JSONL."""
    corrections = []
    if not CORRECTIONS_JSONL.exists():
        return corrections
    for line in CORRECTIONS_JSONL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("session_id") == session_id:
            corrections.append({
                "skill": entry.get("skill", ""),
                "pushback": entry.get("pushback", ""),
                "fix_area": entry.get("fix_area", "unknown"),
            })
    return corrections


def get_skills_used(session_id: str) -> list[dict]:
    """Read skill usage for this session from JSONL. Count invocations."""
    counts: dict[str, int] = {}
    if not USAGE_JSONL.exists():
        return []
    for line in USAGE_JSONL.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("session_id") == session_id:
            skill = entry.get("skill", "")
            if skill:
                counts[skill] = counts.get(skill, 0) + 1
    return [
        {"skill": skill, "count": count, "re_invoked": count > 1}
        for skill, count in counts.items()
    ]


def get_routing_triggers() -> dict[str, list[str]]:
    """Load routing.fires_on arrays from all skills' tests.json files."""
    triggers: dict[str, list[str]] = {}
    if not SKILLS_DIR.exists():
        return triggers
    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        tests_file = skill_dir / "tests.json"
        if not tests_file.exists():
            continue
        try:
            data = json.loads(tests_file.read_text())
            fires_on = data.get("routing", {}).get("fires_on", [])
            if fires_on:
                triggers[skill_dir.name] = [phrase.lower() for phrase in fires_on]
        except json.JSONDecodeError:
            log_error(f"Invalid JSON in {tests_file}")
            continue
    return triggers


def get_user_messages(transcript_path: str) -> list[str]:
    """Extract user message text from transcript, excluding system-reminder content."""
    messages = []
    path = Path(transcript_path)
    if not path.exists():
        return messages
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", "")
        if isinstance(content, list):
            text = " ".join(
                c.get("text", "")
                for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            )
        else:
            text = str(content) if content else ""
        # Skip messages that are primarily system-reminder content
        if "system-reminder" in text and len(text.split("system-reminder")) > 2:
            continue
        if text.strip():
            messages.append(text)
    return messages


def find_missed_triggers(
    routing_triggers: dict[str, list[str]],
    user_messages: list[str],
    skills_invoked: set[str],
) -> list[dict]:
    """Find skills whose routing triggers appeared in user messages but were never invoked."""
    missed = []
    seen_skills: set[str] = set()
    for skill, phrases in routing_triggers.items():
        if skill in skills_invoked or skill in seen_skills:
            continue
        for phrase in phrases:
            for msg in user_messages:
                if phrase in msg.lower():
                    missed.append({
                        "skill": skill,
                        "phrase": phrase,
                        "user_message": msg[:200],
                    })
                    seen_skills.add(skill)
                    break
            if skill in seen_skills:
                break
    return missed


def main() -> None:
    try:
        payload = read_stdin_payload()
    except json.JSONDecodeError as e:
        log_error(f"Failed to parse stdin payload: {e}")
        return

    session_id = payload.get("session_id", "")
    transcript_path = payload.get("transcript_path", "")

    if not session_id:
        log_error("No session_id in hook payload")
        return

    # Signal 1: Explicit corrections
    try:
        corrections = get_corrections(session_id)
    except FileNotFoundError:
        corrections = []
    except json.JSONDecodeError as e:
        log_error(f"Corrections JSONL parse error: {e}")
        corrections = []

    # Signal 2: Skill usage
    try:
        skills_used = get_skills_used(session_id)
    except FileNotFoundError:
        skills_used = []
    except json.JSONDecodeError as e:
        log_error(f"Usage JSONL parse error: {e}")
        skills_used = []

    # Signal 3: Missed triggers
    missed_triggers = []
    if transcript_path:
        try:
            routing_triggers = get_routing_triggers()
            user_messages = get_user_messages(transcript_path)
            skills_invoked = {s["skill"] for s in skills_used}
            missed_triggers = find_missed_triggers(
                routing_triggers, user_messages, skills_invoked
            )
        except FileNotFoundError as e:
            log_error(f"Transcript not found: {e}")
        except json.JSONDecodeError as e:
            log_error(f"Transcript parse error: {e}")

    # Always write the debrief (even if empty) to clear stale data from
    # the previous session. Without this, a session that uses no skills
    # leaves the old debrief in place, and the next startup surfaces it again.
    debrief = {
        "session_id": session_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "corrections": corrections,
        "skills_used": skills_used,
        "missed_triggers": missed_triggers,
    }

    try:
        DEBRIEF_FILE.write_text(json.dumps(debrief, indent=2))
    except OSError as e:
        log_error(f"Failed to write debrief file: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_error(f"Unhandled exception:\n{traceback.format_exc()}")
