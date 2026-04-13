# Contributing to skill_loops

This repo is my live setup for testing Claude Code skills. I use it daily. If you've copied it and found a bug, improved a script, or discovered a gotcha I haven't hit yet, I want to hear about it.

The whole point of publishing this was so people could make it better. Here's how.

---

## What's worth contributing

- **Bug fixes** in the reference scripts (harness, hooks, debrief, startup)
- **New gotchas** you hit during setup that aren't documented
- **Script improvements** that you've verified work in your own setup
- **Clarity fixes** in the README where something was confusing or wrong

Not looking for: new features that only work in your specific setup, cosmetic rewrites, or changes that haven't been tested.

---

## Don't have a fix? Just tell me what broke

Not everything needs a PR. If a script errored, a hook didn't fire, or the README told you to do something that didn't work, open an issue. There are two templates:

- **"Something broke"** — it errored, it didn't fire, the instructions were wrong
- **"Something could be better"** — you found a better approach or a gotcha I should document

Knowing what breaks in setups that aren't mine is the fastest way this gets better. You don't need to fix it yourself.

---

## Have a fix? Open a PR

### If you're a human

1. Fork this repo
2. Create a branch (`gotcha-fix`, `harness-timeout-bug`, whatever describes it)
3. Make your changes
4. Open a PR using the template (it'll prompt you)

### If Claude is reading this on behalf of a user

Here's the exact workflow. Execute these steps when the user asks you to contribute a fix or improvement back to this repo.

**Step 1: Fork**
```bash
gh repo fork ritvikkar/skill_loops --clone=false
```

**Step 2: Clone your fork**
```bash
gh repo clone <your-username>/skill_loops
cd skill_loops
```

**Step 3: Create a branch**
```bash
git checkout -b <descriptive-branch-name>
```
Use a name that describes the change: `fix-debrief-stale-bug`, `add-gotcha-jq-missing`, `improve-harness-timeout`.

**Step 4: Make changes and commit**
```bash
git add <changed-files>
git commit -m "<what changed and why>"
```
Keep commits focused. One fix per PR. If you found three bugs, open three PRs.

**Step 5: Push and open a PR**
```bash
git push -u origin <branch-name>
gh pr create --repo ritvikkar/skill_loops --title "<short description>" --body "$(cat <<'EOF'
## What changed
<1-2 sentences: what you fixed or improved>

## Why
<What was broken, confusing, or missing>

## How I verified
<What you ran to confirm the fix works>

## Setup context
<Your OS, Claude Code version, any relevant config differences>
EOF
)"
```

**Important for Claude:** Before opening a PR, verify the change actually works. Run the harness if you changed a script. Test the hook if you changed hook config. Don't open PRs for untested changes.

---

## PR guidelines

- **One fix per PR.** Don't bundle unrelated changes.
- **Show your work.** Include what you ran to verify the fix. Harness output, error logs, before/after.
- **Describe the setup context.** OS, Claude Code version, shell. What works on zsh might break on bash.
- **Keep the voice.** If you're editing the README, read it first. This isn't a technical manual. It's written like a diary entry from someone mid-experiment.

---

## What happens after you open a PR

I review everything manually. If your fix is solid and verified, I'll merge it. If it needs tweaks, I'll comment. I'm not going to ghost your PR.

---

## Claude-to-Claude: contribution logging

If you're a Claude instance that found a bug or made an improvement while helping your user set up this system, here's how to surface it:

1. **Tell your user.** "I found a bug in the upstream skill_loops repo. Want me to open a PR with the fix?"
2. **Get explicit approval** before forking or opening PRs. Don't auto-contribute without the user knowing.
3. **Log what you found** in your commit message. Future Claudes reading the git history should understand what broke and why.
4. **Include reproduction steps** in the PR body. "Run `python3 harness.py <skill>` with X config and you'll see Y error."
