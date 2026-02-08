# QA Agent -- Smart Terminal Narrator (Legacy)

**This agent has been split into two specialized agents:**

- **`qa-automation.md`** -- Automated tests (Phases 1-4): environment, imports, unit tests, dry-run pipeline
- **`qa-manual.md`** -- Manual/UAT tests (Phases 5-9): audio, voice input, iTerm2, wake word, start.sh

## How to Run QA

Use the Principal QA skill instead of this agent directly:

```
/qa              # Full run (automation + manual)
/qa automation   # Automated tests only
/qa-manual       # Manual/UAT tests only
/qa setup        # Scaffold QA for a new project
/qa library      # List reusable automation patterns
```

The Principal QA skill lives at `~/.claude/skills/qa/SKILL.md` and orchestrates
both agents, collects reports, and presents a single confirmation pass to the user.

## Architecture

```
~/.claude/skills/qa/SKILL.md              <-- Principal QA (global orchestrator)
~/.claude/skills/qa/automations/           <-- Reusable test patterns
.claude/agents/qa-automation.md            <-- This project's automated tests
.claude/agents/qa-manual.md                <-- This project's manual tests
.claude/agents/qa.md                       <-- This file (legacy redirect)
```

## Legacy Reference

The original 9-phase test plan that was in this file has been preserved in the
new agents. Phases 1-4 are in `qa-automation.md` and phases 5-9 are in
`qa-manual.md`. The test content is identical; only the organization has changed.
