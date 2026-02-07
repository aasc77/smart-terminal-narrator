#!/usr/bin/env bash
#
# Smart Terminal Narrator — Setup Script
#
# Installs all required dependencies on macOS.
# Run once before using narrator.py.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VOICE_DIR="$HOME/.local/share/piper-voices"

echo "=== Smart Terminal Narrator — Setup ==="
echo ""

# ---- Homebrew check ----
if ! command -v brew &>/dev/null; then
    echo "Error: Homebrew is required. Install from https://brew.sh"
    exit 1
fi

# ---- Ollama ----
if ! command -v ollama &>/dev/null; then
    echo "Installing Ollama..."
    brew install ollama
else
    echo "OK: Ollama already installed"
fi

# ---- Python 3 ----
if ! command -v python3 &>/dev/null; then
    echo "Error: Python 3.10+ is required. Install with: brew install python@3.12"
    exit 1
else
    echo "OK: Python 3 found: $(python3 --version)"
fi

# ---- Python dependencies ----
echo "Installing Python dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt"

# ---- Pull the default Ollama model ----
echo ""
echo "Pulling qwen2.5:14b model (this may take a few minutes on first run)..."
ollama pull qwen2.5:14b

# ---- Download Piper TTS voice model ----
echo ""
echo "Downloading Piper TTS voice model..."
mkdir -p "$VOICE_DIR"
if [ ! -f "$VOICE_DIR/en_US-lessac-high.onnx" ]; then
    curl -sL "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx" \
        -o "$VOICE_DIR/en_US-lessac-high.onnx"
    curl -sL "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx.json" \
        -o "$VOICE_DIR/en_US-lessac-high.onnx.json"
    echo "OK: Piper voice model downloaded"
else
    echo "OK: Piper voice model already exists"
fi

# ---- Microphone permissions note ----
echo ""
echo "NOTE: Voice input requires microphone access."
echo "      macOS will prompt for permission on first use."
echo "      Grant access to Terminal/iTerm2 in:"
echo "      System Settings > Privacy & Security > Microphone"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To start:  ./start.sh"
echo "With voice: ./start.sh --voice"
echo ""
