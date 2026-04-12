#!/bin/bash
# post-edit-hook.sh — PostToolUse hook for Write|Edit on skill.md files.
# Runs harness + updates health when a skill.md is edited.
# Uses printf instead of echo to avoid zsh escape interpretation.

input=$(cat)
file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null)

if printf '%s' "$file" | grep -qE '\.claude/skills/[^/]+/skill\.md$'; then
    skill=$(printf '%s' "$file" | sed -E 's|.*/skills/([^/]+)/skill\.md$|\1|')
    tests="$HOME/.claude/skills/${skill}/tests.json"
    if [ -f "$tests" ]; then
        mkdir -p "$HOME/.claude/skill-test-reports"
        python3 "$HOME/.claude/skills/eval-skill/harness.py" "$skill" 2>&1
        python3 "$HOME/.claude/skills/eval-skill/update-health.py" 2>/dev/null
    fi
fi
