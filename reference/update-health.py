#!/usr/bin/env python3
"""update-health.py — merge latest harness reports into skill-health.json.
Called after each harness run by the PostToolUse hook."""
import json
from pathlib import Path
from collections import defaultdict

REPORTS_DIR = Path.home() / ".claude" / "skill-test-reports"
HEALTH_FILE = Path.home() / ".claude" / "skill-health.json"


def main() -> None:
    if not REPORTS_DIR.exists():
        return

    by_skill: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(REPORTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            skill = data.get("skill")
            if skill:
                by_skill[skill].append(data)
        except Exception:
            continue

    health: dict[str, dict] = {}
    for skill, reports in by_skill.items():
        latest = reports[-1]
        health[skill] = {
            "pct": latest.get("pct", 0),
            "pass": latest.get("pass", 0),
            "total": latest.get("total", 0),
            "run_at": latest.get("run_at", ""),
            "failures": [f["item"][:80] for f in latest.get("failures", [])],
        }

    HEALTH_FILE.write_text(json.dumps(health, indent=2))


if __name__ == "__main__":
    main()
