# Smart Terminal Narrator

A local voice assistant that watches your Claude Code terminal and speaks only when it needs your attention. Uses a local LLM (via Ollama) to intelligently detect permission prompts, questions, and errors -- so you can look away from the screen and still know when Claude needs you.

Optionally, speak your answers back and the narrator will transcribe and send them to Claude Code automatically.

## How It Works

```
Claude Code (iTerm2 tab)
        |  `script` command logs output to file
        v
Log File (/tmp/claude-narrator.log)
        |  narrator.py reads new content
        v
Terminal Cleaner (strips ANSI codes, UI noise)
        |  clean text
        v
Filter LLM (Ollama / qwen2.5:14b)
        |  classifies: [Q]uestion or [S]ummary or SKIP
        v
TTS Engine (Piper neural voice or macOS say)
        |  speaks the narration
        v
Voice Input (optional, --voice-input)
        |  after a [Q]uestion: mic activates, Silero VAD + mlx-whisper
        v
iTerm2 AppleScript
        |  transcription sent to Claude Code tab
        v
Claude Code receives your spoken answer
```

The narrator speaks when Claude:
- Asks you a question
- Requests permission to run a command, edit a file, or use a tool
- Presents options for you to choose from
- Reports an error that needs your attention
- Gives a summary of completed work
- Finishes and waits for your next instruction

Everything else (code output, raw diffs, file contents, progress indicators) is silently skipped.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) -- local LLM runtime

### macOS

- iTerm2 (used by `start.sh` for auto-launch)
- macOS `say` available as TTS fallback
- No tmux needed -- uses `script` command + iTerm2 tabs
- For voice input: microphone access (macOS will prompt on first use)

### Windows (untested)

- WSL2 with a Linux distro (Ubuntu recommended)
- tmux, python3, ollama installed inside WSL
- Windows Terminal recommended
- See [Windows/WSL Setup](#windowswsl-setup-untested) below
- Voice input not supported on Windows/WSL

### Linux

- tmux, python3, ollama
- ALSA (`aplay`) or PulseAudio (`paplay`) for audio playback

## Quick Start (macOS)

```bash
# 1. Clone the repo
git clone https://github.com/aasc77/smart-terminal-narrator.git
cd smart-terminal-narrator

# 2. Run setup (installs dependencies, pulls models, downloads voice)
chmod +x setup.sh start.sh
./setup.sh

# 3. Launch everything
./start.sh                    # uses current directory
./start.sh ~/my-project       # launches Claude in a specific folder
./start.sh --voice            # enable voice input (speak answers back)
./start.sh ~/my-project --voice
```

You can also add a shell alias for quick access from any terminal:

```bash
# Add to ~/.zshrc or ~/.bashrc
narrator() { /path/to/smart-terminal-narrator/start.sh "$@"; }
```

Then run `narrator`, `narrator ~/my-project`, or `narrator --voice` from anywhere.

`start.sh` will:
1. Start Ollama if not running
2. Open iTerm2 with two tabs: Claude Code + narrator
3. Log Claude's output via `script` (no tmux -- full mouse scrolling preserved)

In the narrator tab, press **Enter** when ready. Then switch to the Claude tab and use it normally.

### Narrator Controls

While the narrator is running, switch to the narrator tab and type:

| Command | Short | Description |
|---------|-------|-------------|
| `pause` | `p` | Temporarily stop narrating |
| `resume` | `r` | Continue narrating |
| `stop` | `q` | Quit the narrator |
| `voice` | `v` | Manually trigger voice input (requires `--voice-input`) |
| `help` | -- | Show available commands |

Press **Escape** to interrupt the current narration (requires `pynput`).

## Voice Input

When enabled with `--voice-input`, the narrator listens for your spoken response after Claude asks a question:

1. Claude asks a question (detected by the LLM filter as `[Q]`)
2. TTS speaks the question aloud
3. A short audio cue plays and the mic activates
4. You speak your answer
5. Silero VAD detects when you stop talking
6. mlx-whisper transcribes your speech locally on Apple Silicon
7. The transcription is sent to Claude Code's iTerm2 tab via AppleScript

You can also trigger voice input manually by typing `v` in the narrator tab.

### Voice Input Options

| Flag | Default | Description |
|------|---------|-------------|
| `--voice-input` | off | Enable voice input |
| `--stt-model` | `mlx-community/whisper-tiny` | mlx-whisper model for transcription |
| `--silence-timeout` | `1.5` | Seconds of silence before ending recording |
| `--listen-timeout` | `10.0` | Max seconds to wait for speech |
| `--iterm-session` | auto | iTerm2 session ID (auto-detected if omitted) |

### Example

```bash
# Voice input with default settings
python3 narrator.py --logfile /tmp/claude.log --voice-input

# Voice input with longer listen timeout
python3 narrator.py --logfile /tmp/claude.log --voice-input --listen-timeout 15

# Voice input with a larger Whisper model for better accuracy
python3 narrator.py --logfile /tmp/claude.log --voice-input --stt-model mlx-community/whisper-large-v3
```

## Wake Word

When enabled with `--wake-word`, the narrator listens for a wake phrase to trigger voice input at any time -- not just after questions.

| Flag | Default | Description |
|------|---------|-------------|
| `--wake-word` | off | Enable always-on wake word detection |
| `--wake-phrase` | `hey jarvis` | The phrase to listen for |

```bash
# Wake word with default phrase
python3 narrator.py --logfile /tmp/claude.log --voice-input --wake-word

# Custom wake phrase
python3 narrator.py --logfile /tmp/claude.log --voice-input --wake-word --wake-phrase "hey computer"
```

When the wake word is detected:
1. Audio cue plays
2. Mic activates for voice input
3. Your speech is transcribed and sent to Claude Code

Additionally, if you speak while the narrator is talking, it will interrupt the current narration (speech-based interrupt).

## Interrupting Narration

There are three ways to interrupt narration:

1. **Escape key** -- press Escape to immediately stop the current narration and clear the queue (requires `pynput`)
2. **Speech interrupt** -- speak while the narrator is talking (requires `--wake-word`)
3. **Pause command** -- type `p` in the narrator tab to pause all narration

## Windows/WSL Setup (untested)

> **Note:** Windows support is experimental and untested. Community contributions and bug reports are welcome.

1. Install [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) with Ubuntu
2. Inside WSL, install dependencies:
   ```bash
   sudo apt update && sudo apt install -y tmux
   curl -fsSL https://ollama.com/install.sh | sh
   pip3 install -r requirements.txt
   ```
3. Pull the Ollama model and download the Piper voice:
   ```bash
   ollama pull qwen2.5:14b
   mkdir -p ~/.local/share/piper-voices
   curl -sL "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx" \
       -o ~/.local/share/piper-voices/en_US-lessac-high.onnx
   curl -sL "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx.json" \
       -o ~/.local/share/piper-voices/en_US-lessac-high.onnx.json
   ```
4. Launch from PowerShell:
   ```powershell
   .\start.ps1
   ```
   Or manually inside WSL:
   ```bash
   tmux new-session -s dev
   # In one pane: claude
   # tmux pipe-pane -t dev:0.0 -o "cat >> /tmp/claude-narrator.log"
   # In another pane: python3 narrator.py --logfile /tmp/claude-narrator.log
   ```

**Known limitations on Windows/WSL:**
- Audio playback uses PowerShell's `SoundPlayer` which only supports WAV
- WSL audio passthrough may require PulseAudio or PipeWire configuration
- The `start.ps1` script assumes WSL is the default distro
- Voice input and wake word are macOS-only (mlx-whisper requires Apple Silicon)

## Manual Usage

If you prefer to set things up yourself:

```bash
# Start Ollama
ollama serve

# In one terminal, run Claude with output logging
script -q /tmp/claude-narrator.log claude

# In another terminal, start the narrator
python3 narrator.py --logfile /tmp/claude-narrator.log

# Or with voice input
python3 narrator.py --logfile /tmp/claude-narrator.log --voice-input
```

Alternatively, you can use tmux with `pipe-pane` if you prefer:

```bash
tmux new-session -s dev
tmux pipe-pane -t dev:0.0 -o "cat >> /tmp/claude-narrator.log"
claude
# In another pane: python3 narrator.py --logfile /tmp/claude-narrator.log
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
| `--voice-input` | off | Enable voice input (speak answers back) |
| `--stt-model` | `mlx-community/whisper-tiny` | Whisper model for STT |
| `--silence-timeout` | `1.5` | Seconds of silence to end recording |
| `--listen-timeout` | `10.0` | Max seconds to wait for speech |
| `--iterm-session` | auto | iTerm2 session ID |
| `--wake-word` | off | Enable always-on wake word detection |
| `--wake-phrase` | `hey jarvis` | Wake word phrase |

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

# Full voice interaction
python3 narrator.py --logfile /tmp/claude.log --voice-input --wake-word

# Voice input with custom wake phrase
python3 narrator.py --logfile /tmp/claude.log --voice-input --wake-word --wake-phrase "hey computer"
```

## TTS Engines

**Piper** (default) -- Neural TTS that runs locally. Sounds natural and human-like. The setup script downloads the `en_US-lessac-high` voice model (~109MB) to `~/.local/share/piper-voices/`. Works on macOS, Linux, and Windows.

**macOS say** (fallback) -- Built-in macOS speech synthesis. Works out of the box. For better quality, download premium voices in System Settings > Accessibility > Spoken Content > System Voice > Manage Voices.

## Platform Support

| Platform | Status | Launcher | Audio | Voice Input |
|----------|--------|----------|-------|-------------|
| macOS (Apple Silicon) | Tested | `start.sh` + iTerm2 | `afplay` / Piper | mlx-whisper |
| macOS (Intel) | Should work | `start.sh` + iTerm2 | `afplay` / Piper | Not supported |
| Linux | Should work | Manual tmux | `aplay` / `paplay` / Piper | Not supported |
| Windows (WSL2) | **Untested** | `start.ps1` | PowerShell `SoundPlayer` / Piper | Not supported |

## Troubleshooting

**Narrator doesn't speak:** Make sure you pressed Enter in the narrator tab to activate it. The narrator waits for you to be ready before it starts listening. Also check it's not paused -- type `resume` in the narrator tab.

**Narrator speaks too much:** The LLM filter might need a larger model. Try `--model qwen2.5:32b` or `--model llama3.1:70b` if you have the RAM.

**Narrator speaks too little:** Check that the log file is growing: `tail -f /tmp/claude-narrator.log`

**Ollama not connecting:** Run `ollama serve` in a separate terminal, or check if it's already running with `curl http://localhost:11434/api/tags`.

**No audio on Linux:** Install ALSA utilities (`sudo apt install alsa-utils`) or PulseAudio (`sudo apt install pulseaudio-utils`).

**No audio on WSL:** WSL doesn't pass through audio by default. You may need to configure PulseAudio or PipeWire to route audio to the Windows host.

**Voice input not working:** Check that your terminal app (iTerm2/Terminal) has microphone access in System Settings > Privacy & Security > Microphone.

**Whisper model download slow:** Models are downloaded on first use from Hugging Face. The `whisper-tiny` model is ~150MB. For faster startup on subsequent runs, models are cached in `~/.cache/huggingface/`.

**Wake word not detecting:** Try speaking the phrase clearly and at a normal volume. Adjust `--wake-phrase` if needed. openWakeWord models are downloaded on first use.

## Contributing

Contributions welcome -- especially for:
- Windows/WSL testing and fixes
- Linux distribution testing
- Additional TTS engine support
- Better terminal output parsing
- Additional wake word models
- Voice input on non-Apple-Silicon platforms

## License

MIT
