# Quick Start Guide

Get Smart Terminal Narrator running in under 5 minutes on macOS (Apple Silicon).

## Prerequisites

- macOS with Apple Silicon (M1/M2/M3/M4)
- [Homebrew](https://brew.sh) installed
- [iTerm2](https://iterm2.com) installed
- Python 3.10+

## 1. Clone and set up

```bash
git clone https://github.com/aasc77/smart-terminal-narrator.git
cd smart-terminal-narrator
chmod +x setup.sh start.sh
./setup.sh
```

This installs Ollama, pulls the `qwen2.5:14b` model (~9 GB), installs Python
packages, and downloads the Piper TTS voice model.

## 2. Launch

```bash
./start.sh
```

iTerm2 opens two tabs:

| Tab | What it does |
|-----|-------------|
| **Tab 1** (Claude Code) | Runs `claude` with output logged to `/tmp/claude-narrator.log` |
| **Tab 2** (Narrator) | Watches the log, filters with LLM, speaks important events |

Switch to the **Narrator tab**, press **Enter** to start listening, then switch
back to the **Claude tab** and work normally.

## 3. What you'll hear

The narrator speaks when Claude:

- Asks a question or requests permission
- Presents options for you to choose from
- Reports an error that blocks progress
- Gives a summary of completed work
- Finishes and waits for your next instruction

Everything else (code, diffs, progress bars) is silently skipped.

## 4. Controls

Type these in the **Narrator tab**:

| Key | Action |
|-----|--------|
| `p` | Pause narration |
| `r` | Resume narration |
| `q` | Quit narrator |
| `v` | Trigger voice input (needs `--voice-input`) |
| **Esc** | Interrupt current narration |

## 5. Enable voice input (optional)

Speak your answers instead of typing. After the narrator reads a question,
your mic activates, you speak, and your answer is transcribed and sent to
Claude Code automatically.

```bash
./start.sh --voice
```

Or manually:

```bash
python3 narrator.py --logfile /tmp/claude.log --voice-input
```

First run downloads the Whisper model (~460 MB). macOS will ask for microphone
permission -- grant it to iTerm2.

### How the voice loop works

```
Narrator speaks question  -->  audio cue (ding)  -->  mic opens
       |                                                   |
       |                                        you speak your answer
       |                                                   |
       |                                        silence detected (1.5 s)
       |                                                   |
       |                                        mlx-whisper transcribes
       |                                                   |
       +---<---  transcription sent to Claude Code via AppleScript
```

## 6. Enable wake word (optional)

Say "hey Jarvis" at any time to trigger voice input -- not just after
questions.

```bash
python3 narrator.py --logfile /tmp/claude.log --voice-input --wake-word
```

Custom wake phrase:

```bash
python3 narrator.py --logfile /tmp/claude.log --voice-input --wake-word --wake-phrase "hey computer"
```

Speaking while the narrator is talking will also interrupt it.

## 7. Common tweaks

```bash
# Use macOS built-in voice instead of Piper
./start.sh    # then in narrator tab, restart with:
python3 narrator.py --logfile /tmp/claude-narrator.log --tts say --voice Alex

# Faster response (poll every 1 second)
python3 narrator.py --logfile /tmp/claude-narrator.log --interval 1

# Smaller/faster LLM if qwen2.5:14b is slow
ollama pull qwen2.5:7b
python3 narrator.py --logfile /tmp/claude-narrator.log --model qwen2.5:7b

# Preview without audio (dry run)
python3 narrator.py --logfile /tmp/claude-narrator.log --dry-run

# Better transcription accuracy (larger Whisper model, ~1.5 GB)
python3 narrator.py --logfile /tmp/claude-narrator.log --voice-input \
    --stt-model mlx-community/whisper-large-v3
```

## 8. Shell alias (optional)

Add to `~/.zshrc`:

```bash
narrator() { /path/to/smart-terminal-narrator/start.sh "$@"; }
```

Then use from anywhere:

```bash
narrator                      # current directory
narrator ~/my-project         # specific project
narrator --voice              # with voice input
narrator ~/my-project --voice # both
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No audio | Press Enter in narrator tab first. Type `r` if paused. |
| Ollama not connecting | Run `ollama serve` in a separate terminal. |
| Voice input silent | Grant mic access: System Settings > Privacy & Security > Microphone > iTerm2. |
| Narration too verbose | Use a larger model: `--model qwen2.5:32b` |
| Narration too quiet | Check log is growing: `tail -f /tmp/claude-narrator.log` |

See the full [README](README.md) for all options, platform support, and
advanced configuration.
