#!/usr/bin/env bash
#
# Smart Terminal Narrator — Start Script
#
# Opens iTerm2, creates a tmux session with Claude Code in the left pane
# and the narrator in the right pane. Uses pipe-pane to stream
# Claude's output to a log file, which the narrator watches.

set -euo pipefail

SESSION="dev"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGFILE="/tmp/claude-narrator.log"

# Check Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Starting Ollama..."
    ollama serve &>/dev/null &
    sleep 2
fi

# Kill existing session if present
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Clear the log file
> "$LOGFILE"

# Create session — Claude goes in pane 0
tmux new-session -d -s "$SESSION" -x 200 -y 50

# Pipe pane 0 output to the log file
tmux pipe-pane -t "$SESSION:0.0" -o "cat >> $LOGFILE"

# Split — right pane (1) for narrator
tmux split-window -h -t "$SESSION"

# Start narrator in pane 1, watching the log file
tmux send-keys -t "$SESSION:0.1" "python3 '$SCRIPT_DIR/narrator.py' --logfile '$LOGFILE' --interval 2" Enter

# Start Claude in the left pane
tmux send-keys -t "$SESSION:0.0" "claude" Enter

# Focus the Claude pane
tmux select-pane -t "$SESSION:0.0"

# Launch iTerm2 and attach to the tmux session
open -a iTerm
sleep 1
osascript -e '
tell application "iTerm2"
    activate
    set newWindow to (create window with default profile)
    tell current session of newWindow
        write text "tmux attach -t dev"
    end tell
end tell
'
