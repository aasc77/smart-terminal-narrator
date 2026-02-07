"""Terminal output capture — log file and tmux pane modes."""

import os
import subprocess
import sys
from typing import Optional

from narrator.clean import clean_terminal_output, strip_ansi


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


def get_new_output(current: str, previous: str) -> Optional[str]:
    """Return only the lines in *current* that weren't in *previous*."""
    if not previous:
        # First capture -- skip to avoid narrating stale screen content
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

    # Content changed (scrolled) but we can't isolate new lines --
    # return the last chunk as best effort
    tail_size = min(20, len(cur_lines))
    new_text = "\n".join(cur_lines[-tail_size:]).strip()
    return new_text if new_text else None
