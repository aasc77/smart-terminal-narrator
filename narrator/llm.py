"""Ollama LLM filter for terminal output."""

import re
import sys
from typing import Optional

import requests

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

When you SPEAK, prefix your response:
- [Q] if Claude is asking a question, requesting permission, or needs the user to act
- [S] if Claude is giving a summary or status update

Be brief but include key details:
- "[Q] Claude wants to edit main.py. Approve?"
- "[Q] Claude is asking which database to use. Option 1: PostgreSQL. Option 2: DynamoDB. Option 3: SQLite."
- "[Q] Claude wants to run npm install. Allow or deny?"
- "[S] Claude committed the changes and pushed to GitHub. Waiting for input."
- "[Q] Error. Claude needs your attention."
- "[S] Claude created 3 files and updated the README. All tests passed."
- "[Q] Claude is asking: do you want tests? Yes or no."

IMPORTANT: When there are choices or options listed, always read them out.
IMPORTANT: When Claude gives a summary of completed work, read it out.
IMPORTANT: Always start with [Q] or [S] -- never omit the prefix.

If the output is ONLY code, diffs, file contents, or terminal noise, respond with exactly: SKIP

Output ONLY the prefixed text to be spoken, or SKIP. Nothing else."""

_PREFIX_RE = re.compile(r"^\[([QS])\]\s*", re.IGNORECASE)


def filter_with_llm(
    text: str,
    model: str = "qwen2.5:14b",
    ollama_url: str = "http://localhost:11434",
    timeout: float = 30.0,
) -> Optional[tuple[str, bool]]:
    """Send captured text to Ollama for intelligent filtering.

    Returns (narration_text, is_question) or None if it should be skipped.
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

        # Parse [Q] / [S] prefix
        is_question = False
        m = _PREFIX_RE.match(result)
        if m:
            is_question = m.group(1).upper() == "Q"
            result = result[m.end():]

        # Truncate overly long narrations
        max_narration = 500
        if len(result) > max_narration:
            result = result[:max_narration].rsplit(" ", 1)[0] + "..."

        return (result, is_question)

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
