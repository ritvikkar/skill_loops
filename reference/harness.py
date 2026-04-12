#!/usr/bin/env python3
"""Skill test harness — runs a skill against test fixtures and grades output.

Usage:
  python3 harness.py <skill-name>
  python3 harness.py <skill-name> --fixture <fixture-id>
  python3 harness.py <skill-name> --timeout 300

Fixture format:
  Single-turn: { "id", "description", "input", "rubric" }
  Multi-turn:  { "id", "description", "turns": [{ "input", "rubric" }, ...] }
  Per-fixture timeout: add "timeout": 300 to any fixture (overrides default)

Requires:
  - claude CLI installed and authenticated (no API key needed)
  - ~/.claude/skills/<skill-name>/tests.json

Reports saved to: ~/.claude/skill-test-reports/
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILLS_DIR = Path.home() / ".claude" / "skills"
REPORTS_DIR = Path.home() / ".claude" / "skill-test-reports"

GRADER_SYSTEM = """\
You are a precise skill output grader. Given a Claude response and a list of rubric items, \
determine whether each rubric item was satisfied by the response.

Rules:
- Grade strictly — partial satisfaction is a fail
- Respond ONLY with valid JSON, no text outside the JSON
- Format exactly:
{
  "grades": [
    {"rubric_item": "<exact item text>", "pass": true, "explanation": "<one sentence>"},
    ...
  ]
}"""

ROUTING_GRADER_SYSTEM = """\
You are a skill routing classifier. Given a skill description and a user message, determine \
whether the message is a clear trigger for that skill based solely on the description's stated \
trigger criteria.

Rules:
- Base your judgment strictly on the description's trigger conditions, not general usefulness
- Respond ONLY with valid JSON, no text outside the JSON
- Format exactly:
{"should_trigger": true, "reasoning": "<one sentence>"}
or
{"should_trigger": false, "reasoning": "<one sentence>"}"""


def strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:].strip()
    return content


def extract_description(skill_content: str) -> str:
    match = re.search(r"description:\s*(.+)", skill_content)
    return match.group(1).strip() if match else "Follow skill instructions correctly"


def run_claude(system: str, user: str, timeout: int = 180) -> str:
    cmd = ["claude", "-p", "--no-session-persistence", "--output-format", "text", "--system-prompt", system, user]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise RuntimeError(f"claude call failed (exit {result.returncode}): {result.stderr[:300]}")
    return result.stdout.strip()


def grade_turn(skill_goal: str, user_input: str, response: str, rubric: list[str]) -> list[dict]:
    payload = json.dumps({
        "skill_goal": skill_goal,
        "user_input": user_input,
        "claude_response": response,
        "rubric": rubric,
    }, indent=2)
    raw = run_claude(GRADER_SYSTEM, payload)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Grader returned non-JSON: {raw[:300]}")
    return json.loads(match.group()).get("grades", [])


def run_single(skill_system: str, skill_goal: str, fixture: dict, timeout: int = 180) -> tuple[str, list[dict]]:
    """Single-turn: run and grade one user message."""
    response = run_claude(skill_system, fixture["input"], timeout=timeout)
    grades = grade_turn(skill_goal, fixture["input"], response, fixture["rubric"])
    return response, grades


def run_multiturn(skill_system: str, skill_goal: str, fixture: dict, timeout: int = 180) -> list[dict]:
    """
    Multi-turn: run each turn sequentially, accumulating history.
    Returns flat list of grade dicts, each with turn_index added.
    """
    history: list[dict] = []
    all_grades: list[dict] = []

    for turn_idx, turn in enumerate(fixture["turns"]):
        # Build user message: history prefix + current input
        if history:
            history_str = "\n\n".join(
                f"Human: {h['user']}\nAssistant: {h['response']}"
                for h in history
            )
            user_msg = f"{history_str}\n\nHuman: {turn['input']}"
        else:
            user_msg = turn["input"]

        response = run_claude(skill_system, user_msg, timeout=timeout)
        history.append({"user": turn["input"], "response": response})

        grades = grade_turn(skill_goal, turn["input"], response, turn.get("rubric", []))
        for g in grades:
            g["turn"] = turn_idx + 1
        all_grades.extend(grades)

    return all_grades


def print_grades(grades: list[dict], all_failures: list[dict], fid: str) -> tuple[int, int]:
    fixture_pass = 0
    for g in grades:
        passed = g.get("pass", False)
        icon = "✅" if passed else "❌"
        turn_label = f"[T{g['turn']}] " if "turn" in g else ""
        print(f"  {icon} {turn_label}{g['rubric_item']}")
        if not passed:
            print(f"     → {g['explanation']}")
            all_failures.append({
                "fixture": fid,
                "turn": g.get("turn"),
                "item": g["rubric_item"],
                "explanation": g["explanation"],
            })
        if passed:
            fixture_pass += 1
    return fixture_pass, len(grades)


def run_routing_tests(skill_name: str, routing: dict, skill_description: str) -> tuple[int, int]:
    """Test routing block: fires_on and does_not_fire_on examples."""
    fires_on = routing.get("fires_on", [])
    does_not_fire = routing.get("does_not_fire_on", [])
    pass_count = 0
    total = len(fires_on) + len(does_not_fire)

    if not total:
        return 0, 0

    print(f"\n## Routing Tests: {skill_name}")
    print("=" * 60)

    for msg in fires_on:
        payload = json.dumps({"skill_description": skill_description, "user_message": msg})
        try:
            raw = run_claude(ROUTING_GRADER_SYSTEM, payload)
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            result = json.loads(match.group()) if match else {"should_trigger": None}
            passed = result.get("should_trigger") is True
            icon = "✅" if passed else "❌"
            print(f"  {icon} fires_on: \"{msg[:70]}\"")
            if not passed:
                print(f"     → Expected: should trigger. Got: {result.get('reasoning', 'no reason')}")
            if passed:
                pass_count += 1
        except Exception as e:
            print(f"  ❌ fires_on: \"{msg[:70]}\"\n     → Error: {e}")

    for msg in does_not_fire:
        payload = json.dumps({"skill_description": skill_description, "user_message": msg})
        try:
            raw = run_claude(ROUTING_GRADER_SYSTEM, payload)
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            result = json.loads(match.group()) if match else {"should_trigger": None}
            passed = result.get("should_trigger") is False
            icon = "✅" if passed else "❌"
            print(f"  {icon} does_not_fire_on: \"{msg[:70]}\"")
            if not passed:
                print(f"     → Expected: should NOT trigger. Got: {result.get('reasoning', 'no reason')}")
            if passed:
                pass_count += 1
        except Exception as e:
            print(f"  ❌ does_not_fire_on: \"{msg[:70]}\"\n     → Error: {e}")

    pct = int(pass_count / total * 100) if total else 0
    print(f"\n  Routing score: {pass_count}/{total} ({pct}%)")
    print("-" * 40)
    return pass_count, total


def run_tests(skill_name: str, fixture_filter: str | None = None, default_timeout: int = 180) -> None:
    skill_path = SKILLS_DIR / skill_name / "skill.md"
    fixtures_path = SKILLS_DIR / skill_name / "tests.json"

    if not skill_path.exists():
        print(f"Error: skill '{skill_name}' not found at {skill_path}")
        sys.exit(1)
    if not fixtures_path.exists():
        print(f"Error: no tests.json at {fixtures_path}")
        sys.exit(1)

    raw_skill = skill_path.read_text()
    skill_goal = extract_description(raw_skill)
    skill_system = strip_frontmatter(raw_skill)

    with open(fixtures_path) as f:
        data = json.load(f)
    routing = data.get("routing", {})
    fixtures = [fx for fx in data["fixtures"] if fx.get("id")]

    if fixture_filter:
        fixtures = [f for f in fixtures if f["id"] == fixture_filter]
        if not fixtures:
            print(f"Error: fixture '{fixture_filter}' not found")
            sys.exit(1)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    routing_count = len(routing.get("fires_on", [])) + len(routing.get("does_not_fire_on", []))
    routing_label = f" | Routing: {routing_count}" if routing_count else ""
    print(f"\n## Skill Test: {skill_name}")
    print(f"Run: {now} | Fixtures: {len(fixtures)}{routing_label}")
    print(f"Goal: {skill_goal}")
    print("=" * 60)

    total_pass = 0
    total_checks = 0
    all_failures: list[dict] = []

    # Run routing tests first if routing block exists and no fixture filter
    routing_pass = routing_total = 0
    if routing and not fixture_filter:
        routing_pass, routing_total = run_routing_tests(skill_name, routing, skill_goal)
        total_pass += routing_pass
        total_checks += routing_total

    for i, fixture in enumerate(fixtures, 1):
        fid = fixture["id"]
        is_multiturn = "turns" in fixture
        mode = f"multi-turn ({len(fixture['turns'])} turns)" if is_multiturn else "single-turn"

        print(f"\n### [{i}/{len(fixtures)}] {fid}  [{mode}]")
        print(f"{fixture['description']}")

        if is_multiturn:
            for t, turn in enumerate(fixture["turns"], 1):
                preview = turn["input"][:100] + ("..." if len(turn["input"]) > 100 else "")
                print(f"  T{t}: \"{preview}\"")
        else:
            preview = fixture["input"][:120] + ("..." if len(fixture["input"]) > 120 else "")
            print(f'Input: "{preview}"')

        fixture_timeout = fixture.get("timeout", default_timeout)
        print(f"  Running ({fixture_timeout}s timeout)... ", end="", flush=True)
        try:
            if is_multiturn:
                grades = run_multiturn(skill_system, skill_goal, fixture, timeout=fixture_timeout)
                print("done.\n")
            else:
                response, grades = run_single(skill_system, skill_goal, fixture, timeout=fixture_timeout)
                resp_preview = response[:200] + ("..." if len(response) > 200 else "")
                print(f"done.\n  Response: {resp_preview}\n")
        except Exception as e:
            print(f"FAILED\n  Error: {e}\n")
            continue

        fixture_pass, fixture_total = print_grades(grades, all_failures, fid)
        total_pass += fixture_pass
        total_checks += fixture_total

        pct = int(fixture_pass / fixture_total * 100) if fixture_total else 0
        print(f"\n  Score: {fixture_pass}/{fixture_total} ({pct}%)")
        print("-" * 40)

    # Summary
    pct = int(total_pass / total_checks * 100) if total_checks else 0
    print(f"\n## Summary: {skill_name}")
    print(f"Total: {total_pass}/{total_checks} rubric items passed ({pct}%)\n")

    if all_failures:
        print("Failures:")
        for f in all_failures:
            turn_label = f" T{f['turn']}" if f.get("turn") else ""
            print(f"  [{f['fixture']}{turn_label}] ❌ {f['item']}")
            print(f"    → {f['explanation']}")
    else:
        print("✅ All rubric items passed.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    report_path = REPORTS_DIR / f"{skill_name}-{stamp}.json"
    with open(report_path, "w") as f:
        json.dump({
            "skill": skill_name,
            "run_at": now,
            "pass": total_pass,
            "total": total_checks,
            "pct": pct,
            "failures": all_failures,
        }, f, indent=2)
    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    skill_name = args[0]
    fixture_filter = None
    default_timeout = 180

    if "--fixture" in args:
        idx = args.index("--fixture")
        if idx + 1 < len(args):
            fixture_filter = args[idx + 1]

    if "--timeout" in args:
        idx = args.index("--timeout")
        if idx + 1 < len(args):
            default_timeout = int(args[idx + 1])

    run_tests(skill_name, fixture_filter, default_timeout)
