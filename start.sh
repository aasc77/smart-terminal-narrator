#!/usr/bin/env bash
#
# Smart Terminal Narrator — Start Script
#
# Opens iTerm2 with two tabs: Claude Code (with output logging via `script`)
# and the narrator. No tmux required — full mouse scrolling preserved.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGFILE="/tmp/claude-narrator.log"

# Check Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Starting Ollama..."
    ollama serve &>/dev/null &
    sleep 2
fi

# Clear the log file
> "$LOGFILE"

# Resolve working directory (optional first argument)
WORK_DIR="$(pwd)"
if [ -n "${1:-}" ] && [ -d "$1" ]; then
    WORK_DIR="$(cd "$1" && pwd)"
fi

NARRATOR_CMD="python3 '$SCRIPT_DIR/narrator.py' --logfile '$LOGFILE' --interval 2"
CLAUDE_CMD="cd '$WORK_DIR' && script -q '$LOGFILE' claude"

osascript <<APPLESCRIPT
tell application "iTerm2"
    activate
    set newWindow to (create window with default profile)

    -- Tab 1: Claude Code (with script logging)
    tell current session of newWindow
        write text "$CLAUDE_CMD"
    end tell

    -- Tab 2: Narrator
    tell newWindow
        set narratorTab to (create tab with default profile)
        tell current session of narratorTab
            write text "$NARRATOR_CMD"
        end tell
    end tell

    -- Focus back on Claude tab
    tell newWindow
        select first tab
    end tell
end tell
APPLESCRIPT
