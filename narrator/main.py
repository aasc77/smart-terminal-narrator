"""CLI entrypoint and main capture loop."""

import argparse
import os
import sys
import threading
import time

import requests

from narrator.capture import capture_from_file, capture_pane, get_new_output
from narrator.llm import filter_with_llm
from narrator.tts import NarrationQueue


class CommandListener:
    """Listens for typed commands (pause/resume/stop/voice) in a background thread."""

    def __init__(self, narration_queue: NarrationQueue, voice_trigger=None):
        self.queue = narration_queue
        self._voice_trigger = voice_trigger
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
                sys.exit(0)
            elif cmd in ("voice", "v"):
                if self._voice_trigger:
                    threading.Thread(
                        target=self._voice_trigger, daemon=True
                    ).start()
                else:
                    print("  Voice input not enabled. Use --voice-input flag.")
            elif cmd == "help":
                cmds = "pause (p), resume (r), stop (q)"
                if self._voice_trigger:
                    cmds += ", voice (v)"
                print(f"  Commands: {cmds}, help")
            elif cmd:
                print("  Unknown command. Type 'help' for options.")

    def stop(self):
        self._stop.set()


def main():
    parser = argparse.ArgumentParser(
        description="Smart Terminal Narrator -- watches terminal output and narrates important events",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python narrator.py --logfile /tmp/claude.log
  python narrator.py --logfile /tmp/claude.log --voice-input
  python narrator.py --logfile /tmp/claude.log --voice-input --wake-word
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

    # Voice input flags
    parser.add_argument(
        "--voice-input", action="store_true",
        help="Enable voice input -- listen for spoken responses after questions",
    )
    parser.add_argument(
        "--stt-model", default="mlx-community/whisper-tiny",
        help="mlx-whisper model for transcription (default: mlx-community/whisper-tiny)",
    )
    parser.add_argument(
        "--silence-timeout", type=float, default=1.5,
        help="Seconds of silence before ending recording (default: 1.5)",
    )
    parser.add_argument(
        "--listen-timeout", type=float, default=10.0,
        help="Max seconds to wait for speech (default: 10.0)",
    )
    parser.add_argument(
        "--iterm-session", default=None,
        help="iTerm2 session ID to send transcriptions to (auto-detected if omitted)",
    )

    # Wake word flags
    parser.add_argument(
        "--wake-word", action="store_true",
        help="Enable always-on wake word detection",
    )
    parser.add_argument(
        "--wake-phrase", default="hey jarvis",
        help="Wake word phrase (default: 'hey jarvis')",
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

    # ------------------------------------------------------------------
    # Voice input setup
    # ------------------------------------------------------------------
    voice_input = None
    voice_trigger = None  # callable for manual "v" command

    if args.voice_input:
        from narrator.audio_cue import play_activation_cue, play_deactivation_cue
        from narrator.iterm import send_to_claude_tab
        from narrator.stt import VoiceInput

        voice_input = VoiceInput(
            stt_model=args.stt_model,
            silence_timeout=args.silence_timeout,
            listen_timeout=args.listen_timeout,
        )
        iterm_session = args.iterm_session or os.environ.get("NARRATOR_ITERM_SESSION")

        def _do_voice_input(context: str = ""):
            play_activation_cue()
            print("  🎤 Listening...")
            text = voice_input.listen_and_transcribe()
            play_deactivation_cue()
            if text:
                print(f"  🗣️  Heard: {text}")
                send_to_claude_tab(text, session_id=iterm_session)
            else:
                print("  🎤 No speech detected.")

        def on_question_spoken(question_text: str):
            _do_voice_input(context=question_text)

        voice_trigger = _do_voice_input
    else:
        on_question_spoken = None

    # ------------------------------------------------------------------
    # Narration queue
    # ------------------------------------------------------------------
    narration_queue = NarrationQueue(
        voice=args.voice,
        engine=args.tts,
        max_pending=args.max_queue,
        on_question_spoken=on_question_spoken if args.voice_input else None,
    )

    # ------------------------------------------------------------------
    # Wake word setup
    # ------------------------------------------------------------------
    wakeword_listener = None
    if args.wake_word:
        from narrator.wakeword import WakeWordListener

        if not args.voice_input:
            print(
                "Warning: --wake-word requires --voice-input. Enabling voice input.",
                file=sys.stderr,
            )
            # Re-initialize voice input if it wasn't set up
            if voice_input is None:
                from narrator.audio_cue import play_activation_cue, play_deactivation_cue
                from narrator.iterm import send_to_claude_tab
                from narrator.stt import VoiceInput

                voice_input = VoiceInput(
                    stt_model=args.stt_model,
                    silence_timeout=args.silence_timeout,
                    listen_timeout=args.listen_timeout,
                )
                iterm_session = args.iterm_session or os.environ.get("NARRATOR_ITERM_SESSION")

                def _do_voice_input(context: str = ""):
                    play_activation_cue()
                    print("  🎤 Listening...")
                    text = voice_input.listen_and_transcribe()
                    play_deactivation_cue()
                    if text:
                        print(f"  🗣️  Heard: {text}")
                        send_to_claude_tab(text, session_id=iterm_session)
                    else:
                        print("  🎤 No speech detected.")

                voice_trigger = _do_voice_input

        wakeword_listener = WakeWordListener(
            wake_phrase=args.wake_phrase,
            on_wake=voice_trigger,
            on_speech_interrupt=narration_queue.interrupt,
        )
        wakeword_listener.start()
        print(f"    Wake word: '{args.wake_phrase}' active")

    # ------------------------------------------------------------------
    # Global hotkey (Escape to interrupt)
    # ------------------------------------------------------------------
    try:
        from pynput import keyboard

        def _on_press(key):
            if key == keyboard.Key.esc:
                narration_queue.interrupt()
                print("  (interrupted)")

        hotkey_listener = keyboard.Listener(on_press=_on_press)
        hotkey_listener.daemon = True
        hotkey_listener.start()
    except ImportError:
        pass  # pynput not installed; skip hotkey

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    use_logfile = args.logfile is not None
    source_desc = f"log file {args.logfile}" if use_logfile else f"tmux pane {args.pane}"

    features = []
    if args.voice_input:
        features.append("voice-input")
    if args.wake_word:
        features.append(f"wake-word({args.wake_phrase})")
    features_str = f" | Features: {', '.join(features)}" if features else ""

    print(f"🎙️  Narrator ready — watching {source_desc}")
    print(f"    Model: {args.model} | Voice: {args.voice} ({args.tts}) | Interval: {args.interval}s{features_str}")
    input("\n    Press Enter when you're ready to start narrating...\n")

    cmds = "'pause', 'resume', 'stop'"
    if voice_trigger:
        cmds += ", 'voice'"
    print(f"    Listening! Type {cmds}, or 'help'.\n")

    # Start command listener for pause/resume/stop/voice
    cmd_listener = CommandListener(narration_queue, voice_trigger=voice_trigger)

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
            result = filter_with_llm(
                new_text,
                model=args.model,
                ollama_url=args.ollama_url,
            )

            if result:
                narration, is_question = result
                tag = "[Q]" if is_question else "[S]"
                print(f"🔊 {tag} {narration}")
                if not args.dry_run:
                    narration_queue.enqueue(narration, is_question=is_question)
            elif args.dry_run:
                print("  [LLM returned SKIP]")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        narration_queue.stop()
        if wakeword_listener:
            wakeword_listener.stop()
        print("\n🛑 Narrator stopped.")
