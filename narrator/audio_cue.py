"""Short audio cues for mic activation and events."""

import subprocess
import sys
import threading


def play_activation_cue():
    """Play a short audio cue to indicate mic activation.

    Uses macOS system sounds for low-latency feedback. Falls back to
    a no-op on unsupported platforms.
    """
    if sys.platform != "darwin":
        return

    def _play():
        try:
            subprocess.run(
                ["afplay", "/System/Library/Sounds/Glass.aiff"],
                capture_output=True,
                timeout=2,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # Non-blocking: play in background thread
    threading.Thread(target=_play, daemon=True).start()


def play_deactivation_cue():
    """Play a short audio cue when mic stops listening."""
    if sys.platform != "darwin":
        return

    def _play():
        try:
            subprocess.run(
                ["afplay", "/System/Library/Sounds/Pop.aiff"],
                capture_output=True,
                timeout=2,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    threading.Thread(target=_play, daemon=True).start()
