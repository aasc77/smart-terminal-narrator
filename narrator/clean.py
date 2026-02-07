"""ANSI / control-character stripping + terminal noise filtering."""

import re

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
