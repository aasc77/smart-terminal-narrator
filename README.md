# Smart Terminal Narrator

A local, zero-cost voice narrator that watches your Claude Code terminal and speaks only the important parts aloud. Uses a small local LLM (via Ollama) to intelligently filter out code blocks, file paths, spinners, and terminal noise — so you only hear conversational output, results, and errors.

## Architecture

```
Claude Code (tmux pane 0)
        │  captures output periodically
        ▼
Output Capturer (diffing new lines)
        │  raw terminal text
        ▼
Filter Agent (Ollama / Llama 3.2 3B)
        │  decides what's worth narrating
        ▼
TTS Engine (macOS `say` or Piper)
```

## Requirements

- macOS (Apple Silicon or Intel) — no GPU required
- Python 3.10+
- [Ollama](https://ollama.com) — local LLM runtime
- tmux — terminal multiplexer
- macOS `say` (built-in) or [Piper TTS](https://github.com/rhasspy/piper)

## Quick Setup

```bash
# Run the setup script (installs Ollama, tmux, pulls the model)
chmod +x setup.sh
./setup.sh
```

Or install manually:

```bash
brew install ollama tmux
ollama pull llama3.2:3b
pip3 install -r requirements.txt
```

## Usage

1. Make sure Ollama is running:
   ```bash
   ollama serve
   ```

2. Start a tmux session and run Claude Code:
   ```bash
   tmux new-session -s dev
   claude
   ```

3. In a separate terminal (or tmux pane), start the narrator:
   ```bash
   python3 narrator.py --pane 0
   ```

4. Use Claude Code as usual. The narrator speaks only the important parts.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--pane` | `0` | tmux pane ID to watch |
| `--interval` | `3.0` | Seconds between captures |
| `--voice` | `Samantha` | macOS voice or Piper model name |
| `--model` | `llama3.2:3b` | Ollama model for filtering |
| `--tts` | `say` | TTS engine: `say` or `piper` |
| `--ollama-url` | `http://localhost:11434` | Ollama API endpoint |
| `--logfile` | — | Watch a log file instead of tmux (fallback) |
| `--max-queue` | `3` | Max pending narrations before dropping stale ones |
| `--dry-run` | — | Print narrations without speaking |

### Example commands

```bash
# Use a different voice
python3 narrator.py --pane 0 --voice Alex

# Faster polling, different model
python3 narrator.py --pane 0 --interval 2 --model llama3.2:1b

# Watch a log file instead of tmux
python3 narrator.py --logfile /tmp/claude-output.log

# Dry run (see what would be narrated without hearing it)
python3 narrator.py --pane 0 --dry-run
```

## How It Works

The narrator captures new terminal output every few seconds, strips ANSI codes, and sends it to a local LLM with a prompt that instructs it to classify the content. Conversational responses, errors, and summaries get spoken aloud. Code blocks, diffs, file listings, and progress indicators are silently skipped. TTS runs in a background thread so it never blocks the capture loop, and a bounded queue drops stale narrations if output is coming in faster than it can be spoken.
