"""AppleScript helpers for sending text to iTerm2 tabs."""

import re
import subprocess
import sys


def _escape_for_applescript(s: str) -> str:
    """Escape a string for safe interpolation into an AppleScript string literal."""
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    # Strip control characters (newlines, tabs, etc.) that could break the literal
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
    return s


def send_to_claude_tab(text: str, session_id: str = None):
    """Send text to the Claude Code tab in iTerm2 via AppleScript.

    Targets the first tab of the frontmost iTerm2 window and types the
    transcription followed by Enter. If session_id is provided, targets
    that specific session instead.
    """
    if sys.platform != "darwin":
        print("Warning: iTerm2 integration only works on macOS.", file=sys.stderr)
        return

    escaped = _escape_for_applescript(text)

    if session_id:
        # Validate session_id: only allow alphanumeric, hyphens, and underscores
        if not re.match(r"^[\w-]+$", session_id, re.ASCII):
            print(f"Warning: invalid session_id '{session_id}'.", file=sys.stderr)
            return
        script = f'''
tell application "iTerm2"
    tell session id "{session_id}"
        write text "{escaped}"
    end tell
end tell
'''
    else:
        script = f'''
tell application "iTerm2"
    tell current window
        tell first tab
            tell current session
                write text "{escaped}"
            end tell
        end tell
    end tell
end tell
'''

    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
    except FileNotFoundError:
        print("Warning: osascript not found.", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("Warning: AppleScript timed out.", file=sys.stderr)
