#
# Smart Terminal Narrator — Start Script (Windows/WSL)
#
# Creates a tmux session (in WSL) with Claude Code in the left pane
# and the narrator in the right pane.
#
# UNTESTED — Community contributions welcome!
#
# Prerequisites:
#   - WSL2 with a Linux distro installed
#   - tmux, python3, ollama installed inside WSL
#   - Windows Terminal (recommended)
#
# Usage: Run from PowerShell or add to Windows Terminal profile.
#

$Session = "dev"
$LogFile = "/tmp/claude-narrator.log"
$ScriptDir = (wsl wslpath -u (Split-Path -Parent $MyInvocation.MyCommand.Path))

# Check Ollama is running inside WSL
$ollamaCheck = wsl curl -s http://localhost:11434/api/tags 2>$null
if (-not $ollamaCheck) {
    Write-Host "Starting Ollama..."
    wsl bash -c "ollama serve &>/dev/null &"
    Start-Sleep -Seconds 2
}

# Kill existing session
wsl tmux kill-session -t $Session 2>$null

# Clear log file
wsl bash -c "> $LogFile"

# Create tmux session
wsl tmux new-session -d -s $Session -x 200 -y 50

# Pipe pane output to log file
wsl tmux pipe-pane -t "${Session}:0.0" -o "cat >> $LogFile"

# Split pane for narrator
wsl tmux split-window -h -t $Session

# Start narrator in right pane
wsl tmux send-keys -t "${Session}:0.1" "python3 '$ScriptDir/narrator.py' --logfile '$LogFile' --interval 2" Enter

# Start Claude in left pane
wsl tmux send-keys -t "${Session}:0.0" "claude" Enter

# Focus Claude pane
wsl tmux select-pane -t "${Session}:0.0"

# Open Windows Terminal and attach
Write-Host "Attaching to tmux session..."
wsl tmux attach -t $Session
