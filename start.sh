#!/usr/bin/env bash
#
# Smart Terminal Narrator — Start Script
#
# Opens iTerm2 with two tabs: Claude Code (with output logging via `script`)
# and the narrator. No tmux required — full mouse scrolling preserved.
#
# Usage:
#   ./start.sh [working-dir] [--voice] [--dangerously-skip-permissions]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGFILE="$(mktemp /tmp/claude-narrator.XXXXXX)"

# Parse flags
VOICE_FLAGS=""
CLAUDE_FLAGS=""
for arg in "$@"; do
    case "$arg" in
        --voice)
            VOICE_FLAGS="--voice-input"
            ;;
        --dangerously-skip-permissions)
            CLAUDE_FLAGS="--dangerously-skip-permissions"
            ;;
    esac
done

# Check Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Starting Ollama..."
    ollama serve &>/dev/null &
    sleep 2
fi

# Set restrictive permissions on log file (contains terminal output)
chmod 600 "$LOGFILE"

# Resolve working directory (optional first positional argument)
WORK_DIR="$(pwd)"
if [ -n "${1:-}" ] && [[ "$1" != --* ]]; then
    if [ -d "$1" ]; then
        WORK_DIR="$(cd "$1" && pwd)"
    else
        echo "Error: directory not found: $1" >&2
        exit 1
    fi
fi

# Escape paths for AppleScript string interpolation
escape_applescript() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
SAFE_SCRIPT_DIR="$(escape_applescript "$SCRIPT_DIR")"
SAFE_WORK_DIR="$(escape_applescript "$WORK_DIR")"
SAFE_LOGFILE="$(escape_applescript "$LOGFILE")"

NARRATOR_CMD="python3 '${SAFE_SCRIPT_DIR}/narrator.py' --logfile '${SAFE_LOGFILE}' --interval 2 $VOICE_FLAGS"
CLAUDE_CMD="cd '${SAFE_WORK_DIR}' && script -q '${SAFE_LOGFILE}' claude $CLAUDE_FLAGS"

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
