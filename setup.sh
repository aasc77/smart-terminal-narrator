#!/usr/bin/env bash
#
# Smart Terminal Narrator — Setup Script
#
# Installs all required dependencies on macOS.
# Run once before using narrator.py.

set -euo pipefail

echo "=== Smart Terminal Narrator — Setup ==="
echo ""

# ---- Homebrew check ----
if ! command -v brew &>/dev/null; then
    echo "Error: Homebrew is required. Install from https://brew.sh"
    exit 1
fi

# ---- Ollama ----
if ! command -v ollama &>/dev/null; then
    echo "📦 Installing Ollama..."
    brew install ollama
else
    echo "✅ Ollama already installed"
fi

# ---- tmux ----
if ! command -v tmux &>/dev/null; then
    echo "📦 Installing tmux..."
    brew install tmux
else
    echo "✅ tmux already installed"
fi

# ---- Python 3 ----
if ! command -v python3 &>/dev/null; then
    echo "Error: Python 3.10+ is required. Install with: brew install python@3.12"
    exit 1
else
    echo "✅ Python 3 found: $(python3 --version)"
fi

# ---- Python dependencies ----
echo "📦 Installing Python dependencies..."
pip3 install -r "$(dirname "$0")/requirements.txt"

# ---- Pull the default Ollama model ----
echo ""
echo "📦 Pulling llama3.2:3b model (this may take a few minutes on first run)..."
ollama pull llama3.2:3b

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Quick start:"
echo "  1. Start Ollama (if not running):  ollama serve"
echo "  2. Open a tmux session:            tmux new-session -s dev"
echo "  3. Run Claude Code in pane 0:      claude"
echo "  4. In another pane/terminal:       python3 narrator.py --pane 0"
echo ""
