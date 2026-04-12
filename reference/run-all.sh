#!/usr/bin/env bash
# run-all.sh — run all skill harnesses and update skill-health.json
#
# Usage:
#   bash ~/.claude/skills/eval-skill/run-all.sh
#   bash ~/.claude/skills/eval-skill/run-all.sh --quiet   (suppress harness output)

SKILLS_DIR="$HOME/.claude/skills"
HARNESS="$SKILLS_DIR/eval-skill/harness.py"
QUIET="${1:-}"

echo "=== Skill Health Run: $(date '+%Y-%m-%d %H:%M %Z') ==="

for skill_dir in "$SKILLS_DIR"/*/; do
    skill_name=$(basename "$skill_dir")
    [ -f "$skill_dir/tests.json" ] || continue

    echo ""
    echo "── $skill_name ──────────────────────────────────────────"
    if [[ "$QUIET" == "--quiet" ]]; then
        python3 "$HARNESS" "$skill_name" > "/tmp/harness-$skill_name.log" 2>&1 \
            && echo "  done" \
            || echo "  failed (see /tmp/harness-$skill_name.log)"
    else
        python3 "$HARNESS" "$skill_name" 2>&1 || echo "  [harness failed]"
    fi
done

echo ""
echo "=== Updating skill-health.json ==="

# Use the same update-health.py that the PostToolUse hook uses,
# so both paths produce identical health JSON.
python3 "$SKILLS_DIR/eval-skill/update-health.py" 2>/dev/null

# Print the ranked table
python3 - <<'EOF'
import json
from pathlib import Path

health_file = Path.home() / ".claude" / "skill-health.json"
if not health_file.exists():
    print("No health data yet.")
    exit(0)

health = json.loads(health_file.read_text())
if not health:
    print("No health data yet.")
    exit(0)

print("\n╔══ SKILL HEALTH RANKING ══════════════════════════════════╗")
ranked = sorted(health.items(), key=lambda x: x[1].get("pct", 0))
for skill, data in ranked:
    pct = data.get("pct", 0)
    n_fail = len(data.get("failures", []))
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    flag = " ◄ needs work" if pct < 80 else ""
    print(f"║  {pct:3d}%  {bar}  {skill:<26} {n_fail:2d} failures{flag}")
print("╚══════════════════════════════════════════════════════════╝")

worst = ranked[0]
print(f"\nLowest scorer: {worst[0]} ({worst[1]['pct']}%)")
if worst[1].get("failures"):
    print("Failing rubric items:")
    for f in worst[1]["failures"]:
        print(f"  ✗ {f}")
EOF
