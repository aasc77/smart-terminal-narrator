#!/usr/bin/env python3
"""
Smart Terminal Narrator Agent

Watches a tmux pane running Claude Code and uses a local LLM (Ollama)
to intelligently filter what gets spoken aloud via text-to-speech.
Only important conversational output is narrated — not code blocks,
file paths, spinners, or terminal noise.
"""

import argparse
import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# System prompt for the filter LLM
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a terminal watcher for Claude Code. You receive raw terminal output and must detect when Claude is asking the user to take action.

SPEAK when Claude is:
- Asking a question that needs the user's answer
- Requesting permission to run a command, edit a file, or execute a tool
- Showing a Yes/No or Allow/Deny prompt
- Asking the user to choose between options
- Reporting an error that blocks progress and needs user intervention
- Giving a summary of what it did or what happened
- Saying it is done and waiting for the next instruction

SKIP only these:
- Raw code blocks, file contents, diffs
- Directory listings, file paths
- Progress indicators, spinners, status updates
- ANSI escape sequences, terminal noise
- Command echoes and tool execution logs

When you SPEAK, be brief but include key details:
- "Claude wants to edit main.py. Approve?"
- "Claude is asking which database to use. Option 1: PostgreSQL. Option 2: DynamoDB. Option 3: SQLite."
- "Claude wants to run npm install. Allow or deny?"
- "Claude committed the changes and pushed to GitHub. Waiting for input."
- "Error. Claude needs your attention."
- "Claude created 3 files and updated the README. All tests passed."
- "Claude is asking: do you want tests? Yes or no."

IMPORTANT: When there are choices or options listed, always read them out.
IMPORTANT: When Claude gives a summary of completed work, read it out.

If the output is ONLY code, diffs, file contents, or terminal noise, respond with exactly: SKIP

Output ONLY the text to be spoken, or SKIP. Nothing else."""

# ---------------------------------------------------------------------------
# ANSI / control-character stripping + terminal noise filtering
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"""
    \x1b       # ESC
    (?:
        \[     # CSI sequences (colors, cursor, etc.)
        [0-9;?]*
        [A-Za-z]
    |
        \]     # OSC sequences
        .*?
        (?:\x07|\x1b\\)
    |
        [()][AB012]   # charset switching
    |
        [=><=]        # keypad / cursor modes
    )
""", re.VERBOSE)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# High-byte Unicode box-drawing / decorative characters from Claude Code UI
_UNICODE_NOISE_RE = re.compile(r"[\u2500-\u257f\u2580-\u259f\u25a0-\u25ff\u2800-\u28ff\ue000-\uf8ff\U000f0000-\U000fffff]+")

# Lines that are just UI noise from Claude Code
_NOISE_PATTERNS = [
    re.compile(r"^\s*[─━┄┈╌═╍]+\s*$"),           # horizontal rules
    re.compile(r"^\s*[│┃┆┊╎║╏]+\s*$"),           # vertical bars only
    re.compile(r"^\s*[╭╮╰╯┌┐└┘]+"),              # box corners
    re.compile(r"^\s*\?\s*(for\s+shortcuts)?\s*$"), # "? for shortcuts"
    re.compile(r"^\s*Try\s+\".*\"\s*$"),           # autocomplete suggestions
    re.compile(r"^\s*/\w+\s+for\s+"),              # "/ide for Antigravity" etc.
    re.compile(r"^\s*(Welcome\s+back|Recent\s+activity|Tips\s+for)"),  # welcome screen
    re.compile(r"^\s*\d+[smh]\s+ago\s+"),          # "9m ago explain..."
    re.compile(r"^\s*/resume\s+for\s+more"),       # resume prompt
    re.compile(r"^\s*/release-notes"),              # release notes link
    re.compile(r"^\s*(Claude\s+Code|Opus|Sonnet|Haiku)\s+[\d.]+"), # version lines
    re.compile(r"^\s*Claude\s+Max\b"),             # plan info
    re.compile(r"^\s*~/"),                         # path display
    re.compile(r"^\s*What's\s+new"),               # changelog header
    re.compile(r"^\s*Fixed\s+a\s+(crash|bug)"),    # changelog entries
    re.compile(r"^\s*$"),                          # blank lines
]


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences, control characters, and Unicode noise."""
    text = _ANSI_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    text = _UNICODE_NOISE_RE.sub(" ", text)
    # Collapse multiple spaces
    text = re.sub(r"  +", " ", text)
    return text


def clean_terminal_output(text: str) -> str:
    """Strip ANSI codes and filter out Claude Code UI noise lines."""
    text = strip_ansi(text)
    clean_lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(p.search(line) for p in _NOISE_PATTERNS):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines)


# ---------------------------------------------------------------------------
# tmux pane capture
# ---------------------------------------------------------------------------

def capture_pane(pane: str, history_lines: int = 200) -> str:
    """Capture the visible content (plus some scroll-back) of a tmux pane."""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", pane, "-p", "-S", f"-{history_lines}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return ""
        return strip_ansi(result.stdout)
    except FileNotFoundError:
        print("Error: tmux is not installed or not in PATH.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        return ""


def capture_from_file(path: str, last_pos: int = 0) -> tuple[str, int]:
    """Capture new content from a log file, clean terminal noise."""
    try:
        with open(path, "r", errors="replace") as fh:
            fh.seek(last_pos)
            new_text = fh.read()
            new_pos = fh.tell()
        return clean_terminal_output(new_text), new_pos
    except FileNotFoundError:
        return "", last_pos


# ---------------------------------------------------------------------------
# Diff: extract only *new* lines
# ---------------------------------------------------------------------------

def get_new_output(current: str, previous: str) -> Optional[str]:
    """Return only the lines in *current* that weren't in *previous*."""
    if not previous:
        # First capture — skip to avoid narrating stale screen content
        return None

    prev_lines = previous.splitlines()
    cur_lines = current.splitlines()

    if prev_lines == cur_lines:
        return None

    # Try multiple anchor sizes to find where previous content ends in current
    for anchor_size in [5, 3, 2, 1]:
        if len(prev_lines) < anchor_size:
            continue
        # Use the last N non-blank lines of previous as anchor
        anchor = prev_lines[-anchor_size:]

        # Search for the anchor in current (prefer latest match)
        for i in range(len(cur_lines) - anchor_size, -1, -1):
            if cur_lines[i : i + anchor_size] == anchor:
                new_lines = cur_lines[i + anchor_size :]
                new_text = "\n".join(new_lines).strip()
                return new_text if new_text else None

    # Fallback: if content changed but we can't anchor, return the
    # trailing portion that differs
    if len(cur_lines) > len(prev_lines):
        new_lines = cur_lines[len(prev_lines) :]
        new_text = "\n".join(new_lines).strip()
        return new_text if new_text else None

    # Content changed (scrolled) but we can't isolate new lines —
    # return the last chunk as best effort
    tail_size = min(20, len(cur_lines))
    new_text = "\n".join(cur_lines[-tail_size:]).strip()
    return new_text if new_text else None


# ---------------------------------------------------------------------------
# Ollama LLM filter
# ---------------------------------------------------------------------------

def filter_with_llm(
    text: str,
    model: str = "qwen2.5:14b",
    ollama_url: str = "http://localhost:11434",
    timeout: float = 30.0,
) -> Optional[str]:
    """Send captured text to Ollama for intelligent filtering.
    Returns the text to narrate, or None if it should be skipped.
    """
    # Truncate very long inputs to avoid slow inference
    max_input_chars = 3000
    if len(text) > max_input_chars:
        text = text[:max_input_chars] + "\n... (truncated)"

    prompt = f"{SYSTEM_PROMPT}\n\nTerminal output:\n{text}"

    try:
        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 256,
                },
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json().get("response", "").strip()

        if not result or result.upper() == "SKIP":
            return None

        # Truncate overly long narrations
        max_narration = 500
        if len(result) > max_narration:
            result = result[:max_narration].rsplit(" ", 1)[0] + "..."

        return result

    except requests.exceptions.ConnectionError:
        print(
            "Warning: Cannot reach Ollama. Is it running? (ollama serve)",
            file=sys.stderr,
        )
        return None
    except requests.exceptions.Timeout:
        print("Warning: Ollama request timed out.", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"Warning: Ollama error: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# TTS engines
# ---------------------------------------------------------------------------

def speak_say(text: str, voice: str = "Samantha"):
    """Speak using macOS built-in `say` command."""
    try:
        subprocess.run(["say", "-v", voice, text], timeout=60)
    except FileNotFoundError:
        print("Error: macOS `say` command not found.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        pass


if sys.platform == "darwin":
    PIPER_VOICE_DIR = os.path.expanduser("~/.local/share/piper-voices")
else:
    PIPER_VOICE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "piper-voices")
PIPER_DEFAULT_MODEL = os.path.join(PIPER_VOICE_DIR, "en_US-lessac-high.onnx")

import tempfile
_PIPER_WAV = os.path.join(tempfile.gettempdir(), "narrator_piper.wav")


def _play_wav(path: str):
    """Play a WAV file using the platform's native player."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["afplay", path], timeout=60)
        elif sys.platform == "win32":
            # PowerShell one-liner for WAV playback on Windows
            subprocess.run(
                ["powershell", "-c",
                 f"(New-Object Media.SoundPlayer '{path}').PlaySync()"],
                timeout=60,
            )
        else:
            # Linux — try aplay (ALSA), then paplay (PulseAudio)
            for player in ["aplay", "paplay"]:
                try:
                    subprocess.run([player, path], timeout=60)
                    return
                except FileNotFoundError:
                    continue
            print("Warning: No audio player found (tried aplay, paplay).", file=sys.stderr)
    except subprocess.TimeoutExpired:
        pass


def speak_piper(text: str, model: Optional[str] = None):
    """Speak using Piper TTS (neural, high quality, local)."""
    model = model or PIPER_DEFAULT_MODEL
    try:
        subprocess.run(
            ["piper", "--model", model, "--output_file", _PIPER_WAV],
            input=text.encode(),
            capture_output=True,
            timeout=30,
        )
        _play_wav(_PIPER_WAV)
    except FileNotFoundError:
        print("Warning: Piper not found, falling back to macOS say.", file=sys.stderr)
        speak_say(text)
    except subprocess.TimeoutExpired:
        pass


def speak(text: str, voice: str, engine: str):
    """Dispatch to the configured TTS engine. Piper with say fallback."""
    if engine == "piper":
        speak_piper(text)
    else:
        speak_say(text, voice=voice)


# ---------------------------------------------------------------------------
# Narration queue (non-blocking TTS)
# ---------------------------------------------------------------------------

class NarrationQueue:
    """Threaded queue so TTS doesn't block the capture loop."""

    def __init__(self, voice: str, engine: str, max_pending: int = 3):
        self.voice = voice
        self.engine = engine
        self.max_pending = max_pending
        self._queue: deque[str] = deque()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.paused = threading.Event()  # set = paused
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def enqueue(self, text: str):
        if self.paused.is_set():
            return  # silently drop while paused
        with self._lock:
            # Drop stale narrations if queue is backing up
            if len(self._queue) >= self.max_pending:
                dropped = self._queue.popleft()
                print(f"  (skipped stale narration: {dropped[:60]}...)")
            self._queue.append(text)

    def stop(self):
        self._stop.set()

    def _worker(self):
        while not self._stop.is_set():
            if self.paused.is_set():
                time.sleep(0.2)
                continue
            item = None
            with self._lock:
                if self._queue:
                    item = self._queue.popleft()
            if item:
                speak(item, self.voice, self.engine)
            else:
                time.sleep(0.1)


# ---------------------------------------------------------------------------
# Command listener — accepts typed commands in the narrator terminal
# ---------------------------------------------------------------------------

class CommandListener:
    """Listens for typed commands (pause/resume/stop) in a background thread."""

    def __init__(self, narration_queue: NarrationQueue):
        self.queue = narration_queue
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._listener, daemon=True)
        self._thread.start()

    def _listener(self):
        while not self._stop.is_set():
            try:
                cmd = input().strip().lower()
            except EOFError:
                break
            if cmd in ("pause", "p"):
                self.queue.paused.set()
                print("  Narrator paused. Type 'resume' to continue.")
            elif cmd in ("resume", "r"):
                self.queue.paused.clear()
                print("  Narrator resumed.")
            elif cmd in ("stop", "quit", "q"):
                print("  Shutting down...")
                self.queue.stop()
                os._exit(0)
            elif cmd == "help":
                print("  Commands: pause (p), resume (r), stop (q), help")
            elif cmd:
                print("  Unknown command. Type 'help' for options.")

    def stop(self):
        self._stop.set()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Smart Terminal Narrator — watches a tmux pane and narrates important output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python narrator.py --pane 0
  python narrator.py --pane 0 --interval 2 --voice Alex --model qwen2.5:14b
  python narrator.py --logfile /tmp/claude.log   # fallback without tmux
        """,
    )

    parser.add_argument(
        "--pane", default="0",
        help="tmux pane identifier to watch (default: 0)",
    )
    parser.add_argument(
        "--interval", type=float, default=3.0,
        help="Seconds between captures (default: 3.0)",
    )
    parser.add_argument(
        "--voice", default="Samantha",
        help="TTS voice name (default: Samantha)",
    )
    parser.add_argument(
        "--model", default="qwen2.5:14b",
        help="Ollama model for filtering (default: qwen2.5:14b)",
    )
    parser.add_argument(
        "--tts", default="piper", choices=["say", "piper"],
        help="TTS engine (default: piper)",
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434",
        help="Ollama API base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--logfile", default=None,
        help="Watch a log file instead of a tmux pane (fallback mode)",
    )
    parser.add_argument(
        "--max-queue", type=int, default=3,
        help="Max pending narrations before dropping stale ones (default: 3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print narrations to stdout without speaking them",
    )

    args = parser.parse_args()

    # Verify Ollama is reachable
    try:
        r = requests.get(f"{args.ollama_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        if args.model not in models and f"{args.model}:latest" not in models:
            # Check partial match
            found = any(args.model.split(":")[0] in m for m in models)
            if not found:
                print(
                    f"Warning: Model '{args.model}' not found in Ollama. "
                    f"Available: {', '.join(models) or 'none'}",
                    file=sys.stderr,
                )
                print(f"Run: ollama pull {args.model}", file=sys.stderr)
    except requests.exceptions.ConnectionError:
        print(
            "Error: Cannot connect to Ollama. Start it with: ollama serve",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception:
        pass  # Non-fatal; we'll retry on each request

    # Set up TTS queue
    narration_queue = NarrationQueue(
        voice=args.voice,
        engine=args.tts,
        max_pending=args.max_queue,
    )

    use_logfile = args.logfile is not None
    source_desc = f"log file {args.logfile}" if use_logfile else f"tmux pane {args.pane}"

    print(f"🎙️  Narrator ready — watching {source_desc}")
    print(f"    Model: {args.model} | Voice: {args.voice} ({args.tts}) | Interval: {args.interval}s")
    input("\n    Press Enter when you're ready to start narrating...\n")
    print("    Listening! Type 'pause', 'resume', 'stop', or 'help'.\n")

    # Start command listener for pause/resume/stop
    cmd_listener = CommandListener(narration_queue)

    # Set logfile position to end of file so we skip everything before now
    logfile_pos = 0
    if use_logfile:
        try:
            logfile_pos = os.path.getsize(args.logfile)
        except OSError:
            pass

    previous_output = ""
    previous_hash = ""

    try:
        while True:
            # --- Capture ---
            if use_logfile:
                new_text, logfile_pos = capture_from_file(args.logfile, logfile_pos)
                new_text = new_text.strip() if new_text else None
                if args.dry_run and new_text:
                    print(f"  [logfile: captured {len(new_text)} chars]")
            else:
                current_output = capture_pane(args.pane)
                # Quick check: skip if pane content hasn't changed at all
                current_hash = str(hash(current_output))
                if current_hash == previous_hash:
                    time.sleep(args.interval)
                    continue
                previous_hash = current_hash
                new_text = get_new_output(current_output, previous_output)
                previous_output = current_output
                if args.dry_run and new_text:
                    print(f"  [captured {len(new_text)} chars of new text]")

            if not new_text or len(new_text) < 10:
                time.sleep(args.interval)
                continue

            # --- Filter ---
            narration = filter_with_llm(
                new_text,
                model=args.model,
                ollama_url=args.ollama_url,
            )

            if narration:
                print(f"🔊 {narration}")
                if not args.dry_run:
                    narration_queue.enqueue(narration)
            elif args.dry_run:
                print("  [LLM returned SKIP]")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        narration_queue.stop()
        print("\n🛑 Narrator stopped.")


if __name__ == "__main__":
    main()
