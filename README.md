# Smart Terminal Narrator

A local voice assistant that watches your Claude Code terminal and speaks only when it needs your attention. Uses a local LLM (via Ollama) to intelligently detect permission prompts, questions, and errors -- so you can look away from the screen and still know when Claude needs you.

## How It Works

```
Claude Code (tmux pane)
        |  tmux pipe-pane streams output to log file
        v
Log File (/tmp/claude-narrator.log)
        |  narrator.py reads new content
        v
Terminal Cleaner (strips ANSI codes, UI noise)
        |  clean text
        v
Filter LLM (Ollama / qwen2.5:14b)
        |  decides: action needed or skip?
        v
TTS Engine (Piper neural voice or macOS say)
```

The narrator only speaks when Claude:
- Asks you a question
- Requests permission to run a command, edit a file, or use a tool
- Presents options for you to choose from
- Reports an error that needs your attention
- Finishes and waits for your next instruction

Everything else (code output, explanations, diffs, progress) is silently skipped.

## Requirements

- macOS (Apple Silicon recommended)
- Python 3.10+
- [Ollama](https://ollama.com) -- local LLM runtime
- tmux -- terminal multiplexer
- iTerm2 (optional, used by `start.sh`)

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/aasc77/smart-terminal-narrator.git
cd smart-terminal-narrator

# 2. Run setup (installs dependencies, pulls models, downloads voice)
chmod +x setup.sh start.sh
./setup.sh

# 3. Launch everything
./start.sh
```

`start.sh` will:
1. Start Ollama if not running
2. Create a tmux session with Claude Code + narrator side by side
3. Open iTerm2 attached to the session

In the narrator pane (right side), press **Enter** when ready. Then use Claude normally in the left pane.

## Manual Usage

If you prefer to set things up yourself:

```bash
# Start Ollama
ollama serve

# In one terminal, start a tmux session
tmux new-session -s dev

# Pipe the pane output to a log file
tmux pipe-pane -t dev:0.0 -o "cat >> /tmp/claude-narrator.log"

# Run Claude Code
claude

# In another terminal, start the narrator
python3 narrator.py --logfile /tmp/claude-narrator.log
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--logfile` | -- | Watch a log file (recommended mode) |
| `--pane` | `0` | tmux pane ID to watch directly (alternative mode) |
| `--interval` | `3.0` | Seconds between captures |
| `--tts` | `piper` | TTS engine: `piper` or `say` |
| `--voice` | `Samantha` | macOS voice name (only used with `--tts say`) |
| `--model` | `qwen2.5:14b` | Ollama model for filtering |
| `--ollama-url` | `http://localhost:11434` | Ollama API endpoint |
| `--max-queue` | `3` | Max pending narrations before dropping stale ones |
| `--dry-run` | -- | Print narrations without speaking |

### Examples

```bash
# Use macOS built-in voice instead of Piper
python3 narrator.py --logfile /tmp/claude.log --tts say --voice Alex

# Faster polling
python3 narrator.py --logfile /tmp/claude.log --interval 1

# Use a different Ollama model
python3 narrator.py --logfile /tmp/claude.log --model llama3.1:8b

# See what would be narrated without hearing it
python3 narrator.py --logfile /tmp/claude.log --dry-run
```

## TTS Engines

**Piper** (default) -- Neural TTS that runs locally. Sounds natural and human-like. The setup script downloads the `en_US-lessac-high` voice model (~109MB) to `~/.local/share/piper-voices/`.

**macOS say** (fallback) -- Built-in macOS speech synthesis. Works out of the box. For better quality, download premium voices in System Settings > Accessibility > Spoken Content > System Voice > Manage Voices.

## Troubleshooting

**Narrator doesn't speak:** Make sure you pressed Enter in the narrator pane to activate it. The narrator waits for you to be ready before it starts listening.

**Narrator speaks too much:** The LLM filter might need a larger model. Try `--model qwen2.5:32b` or `--model llama3.1:70b` if you have the RAM.

**Narrator speaks too little:** Check that `tmux pipe-pane` is active and the log file is growing: `tail -f /tmp/claude-narrator.log`

**Ollama not connecting:** Run `ollama serve` in a separate terminal, or check if it's already running with `curl http://localhost:11434/api/tags`.

## License

MIT
