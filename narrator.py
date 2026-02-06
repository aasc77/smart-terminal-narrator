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
You are a terminal narrator assistant. You receive raw terminal output from a Claude Code session.

Your job:
1. IDENTIFY what type of content this is (conversational response, code, file operation, error, progress indicator, etc.)
2. EXTRACT only the parts worth speaking aloud
3. SUMMARIZE if the output is long

Rules:
- SPEAK: Claude's conversational responses, important results, summaries, confirmations, questions to the user, errors/warnings that need attention
- SKIP: Code blocks, file contents, directory listings, git diffs, progress bars/spinners, ANSI escape sequences, command echoes, file paths
- SUMMARIZE: If Claude wrote a long code file, say something like "Created a Python file called main.py with 120 lines"
- SUMMARIZE: If Claude ran multiple commands, say "Ran 3 commands successfully" rather than reading each one
- Keep narration brief and natural — like a helpful assistant sitting next to you
- If there's nothing worth narrating, respond with exactly: SKIP

Output ONLY the text to be spoken, or SKIP. No explanations, no markdown, no formatting."""

# ---------------------------------------------------------------------------
# ANSI / control-character stripping
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"""
    \x1b       # ESC
    (?:
        \[     # CSI
        [0-9;]*
        [A-Za-z]
    |
        \]     # OSC
        .*?
        (?:\x07|\x1b\\)
    |
        [()][AB012]   # charset
    |
        [=><=]        # keypad / cursor modes
    )
""", re.VERBOSE)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences and control characters."""
    text = _ANSI_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    return text


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
    """Fallback: capture new content from a log file instead of tmux."""
    try:
        with open(path, "r", errors="replace") as fh:
            fh.seek(last_pos)
            new_text = fh.read()
            new_pos = fh.tell()
        return strip_ansi(new_text), new_pos
    except FileNotFoundError:
        return "", last_pos


# ---------------------------------------------------------------------------
# Diff: extract only *new* lines
# ---------------------------------------------------------------------------

def get_new_output(current: str, previous: str) -> Optional[str]:
    """Return only the lines in *current* that weren't in *previous*."""
    if not previous:
        # First capture — treat everything as new
        return current.strip() or None

    prev_lines = previous.splitlines()
    cur_lines = current.splitlines()

    # Find the longest suffix of prev_lines that appears in cur_lines
    # to figure out where new content starts.
    overlap = 0
    for i in range(min(len(prev_lines), len(cur_lines))):
        # Walk backwards through prev to find matching tail in cur
        pass

    # Simple approach: find where previous content ends in current
    # Use the last N lines of previous as an anchor
    anchor_size = min(5, len(prev_lines))
    anchor = prev_lines[-anchor_size:] if anchor_size > 0 else []

    if anchor:
        # Search for the anchor block in current lines
        for i in range(len(cur_lines) - anchor_size, -1, -1):
            if cur_lines[i : i + anchor_size] == anchor:
                new_lines = cur_lines[i + anchor_size :]
                new_text = "\n".join(new_lines).strip()
                return new_text if new_text else None

    # Fallback: if we can't find the anchor, diff by length
    if len(cur_lines) > len(prev_lines):
        new_lines = cur_lines[len(prev_lines) :]
        new_text = "\n".join(new_lines).strip()
        return new_text if new_text else None

    return None


# ---------------------------------------------------------------------------
# Ollama LLM filter
# ---------------------------------------------------------------------------

def filter_with_llm(
    text: str,
    model: str = "llama3.2:3b",
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


def speak_piper(text: str, model: str = "en_US-lessac-medium"):
    """Speak using Piper TTS (better quality, requires piper-tts)."""
    try:
        # Piper outputs raw PCM; pipe through aplay/afplay
        piper_proc = subprocess.Popen(
            ["piper", "--model", model, "--output-raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        audio_data, _ = piper_proc.communicate(input=text.encode(), timeout=60)

        # Try afplay on macOS, aplay on Linux
        player = "afplay" if sys.platform == "darwin" else "aplay"
        play_proc = subprocess.Popen(
            [player, "-"],
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        play_proc.communicate(input=audio_data, timeout=60)

    except FileNotFoundError:
        print("Error: Piper TTS not found. Install with: pip install piper-tts", file=sys.stderr)
    except subprocess.TimeoutExpired:
        pass


def speak(text: str, voice: str, engine: str):
    """Dispatch to the configured TTS engine."""
    if engine == "piper":
        speak_piper(text, model=voice)
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
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def enqueue(self, text: str):
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
            item = None
            with self._lock:
                if self._queue:
                    item = self._queue.popleft()
            if item:
                speak(item, self.voice, self.engine)
            else:
                time.sleep(0.1)


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
  python narrator.py --pane 0 --interval 2 --voice Alex --model llama3.2:3b
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
        "--model", default="llama3.2:3b",
        help="Ollama model for filtering (default: llama3.2:3b)",
    )
    parser.add_argument(
        "--tts", default="say", choices=["say", "piper"],
        help="TTS engine (default: say)",
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

    print(f"🎙️  Narrator active — watching {source_desc}")
    print(f"    Model: {args.model} | Voice: {args.voice} ({args.tts}) | Interval: {args.interval}s")
    print(f"    Press Ctrl+C to stop.\n")

    previous_output = ""
    logfile_pos = 0

    try:
        while True:
            # --- Capture ---
            if use_logfile:
                new_text, logfile_pos = capture_from_file(args.logfile, logfile_pos)
                new_text = new_text.strip() if new_text else None
            else:
                current_output = capture_pane(args.pane)
                new_text = get_new_output(current_output, previous_output)
                previous_output = current_output

            if not new_text:
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

            time.sleep(args.interval)

    except KeyboardInterrupt:
        narration_queue.stop()
        print("\n🛑 Narrator stopped.")


if __name__ == "__main__":
    main()
