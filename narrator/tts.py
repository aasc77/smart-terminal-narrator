"""Text-to-speech engines and narration queue."""

import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from typing import Callable, Optional

if sys.platform == "darwin":
    PIPER_VOICE_DIR = os.path.expanduser("~/.local/share/piper-voices")
else:
    PIPER_VOICE_DIR = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "piper-voices",
    )
PIPER_DEFAULT_MODEL = os.path.join(PIPER_VOICE_DIR, "en_US-lessac-high.onnx")

_PIPER_WAV = os.path.join(
    tempfile.gettempdir(), f"narrator_piper_{os.getpid()}.wav"
)

# Module-level handle for the currently playing audio process (for interrupt)
_current_audio_proc: Optional[subprocess.Popen] = None
_audio_lock = threading.Lock()


def interrupt_audio():
    """Kill any currently playing audio process."""
    global _current_audio_proc
    with _audio_lock:
        if _current_audio_proc and _current_audio_proc.poll() is None:
            _current_audio_proc.terminate()
            _current_audio_proc = None


def speak_say(text: str, voice: str = "Samantha"):
    """Speak using macOS built-in `say` command."""
    global _current_audio_proc
    try:
        with _audio_lock:
            _current_audio_proc = subprocess.Popen(["say", "-v", voice, text])
        _current_audio_proc.wait(timeout=60)
    except FileNotFoundError:
        print("Error: macOS `say` command not found.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        with _audio_lock:
            if _current_audio_proc:
                _current_audio_proc.terminate()
    finally:
        with _audio_lock:
            _current_audio_proc = None


def _play_wav(path: str):
    """Play a WAV file using the platform's native player."""
    global _current_audio_proc
    try:
        if sys.platform == "darwin":
            with _audio_lock:
                _current_audio_proc = subprocess.Popen(["afplay", path])
            _current_audio_proc.wait(timeout=60)
        elif sys.platform == "win32":
            # Use a PowerShell script block with param to avoid string injection
            ps_script = (
                "param($p); (New-Object Media.SoundPlayer $p).PlaySync()"
            )
            with _audio_lock:
                _current_audio_proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", ps_script,
                     "-p", os.path.normpath(path)],
                )
            _current_audio_proc.wait(timeout=60)
        else:
            # Linux -- try aplay (ALSA), then paplay (PulseAudio)
            for player in ["aplay", "paplay"]:
                try:
                    with _audio_lock:
                        _current_audio_proc = subprocess.Popen([player, path])
                    _current_audio_proc.wait(timeout=60)
                    return
                except FileNotFoundError:
                    continue
            print("Warning: No audio player found (tried aplay, paplay).", file=sys.stderr)
    except subprocess.TimeoutExpired:
        with _audio_lock:
            if _current_audio_proc:
                _current_audio_proc.terminate()
    finally:
        with _audio_lock:
            _current_audio_proc = None


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


class NarrationQueue:
    """Threaded queue so TTS doesn't block the capture loop."""

    def __init__(
        self,
        voice: str,
        engine: str,
        max_pending: int = 3,
        on_question_spoken: Optional[Callable[[str], None]] = None,
    ):
        self.voice = voice
        self.engine = engine
        self.max_pending = max_pending
        self.on_question_spoken = on_question_spoken
        # Each item is (text, is_question)
        self._queue: deque[tuple[str, bool]] = deque()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.paused = threading.Event()  # set = paused
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def enqueue(self, text: str, is_question: bool = False):
        if self.paused.is_set():
            return  # silently drop while paused
        with self._lock:
            # Drop stale narrations if queue is backing up
            if len(self._queue) >= self.max_pending:
                dropped = self._queue.popleft()
                print(f"  (skipped stale narration: {dropped[0][:60]}...)")
            self._queue.append((text, is_question))

    def interrupt(self):
        """Stop current playback and clear pending narrations."""
        with self._lock:
            self._queue.clear()
        interrupt_audio()

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
                text, is_question = item
                speak(text, self.voice, self.engine)
                if is_question and self.on_question_spoken:
                    self.on_question_spoken(text)
            else:
                time.sleep(0.1)
