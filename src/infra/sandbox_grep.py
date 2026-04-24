"""Shared grep helpers for sandbox backends."""

from __future__ import annotations

import shlex

from deepagents.backends.protocol import ExecuteResponse, GrepMatch

_DEFAULT_GREP_TIMEOUT = 30


def get_sandbox_grep_timeout(settings_obj: object) -> int:
    """Return the configured grep timeout with a stable fallback."""
    value = getattr(settings_obj, "SANDBOX_GREP_TIMEOUT", _DEFAULT_GREP_TIMEOUT)
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_GREP_TIMEOUT
    return max(1, timeout)


def build_grep_command(pattern: str, path: str | None = None, glob: str | None = None) -> str:
    """Build a literal recursive grep command."""
    search_path = shlex.quote(path or ".")
    pattern_escaped = shlex.quote(pattern)
    include_clause = f"--include={shlex.quote(glob)} " if glob else ""
    return f"grep -rHnF {include_clause}-e {pattern_escaped} {search_path} 2>/dev/null || true"


def parse_grep_response(result: ExecuteResponse, timeout: int) -> list[GrepMatch] | str:
    """Parse grep output or surface a user-facing timeout error."""
    output = result.output.rstrip()
    if result.exit_code == -1 and "timed out" in output.lower():
        return f"Error: grep timed out after {timeout}s. Try a more specific pattern or a narrower path."

    if not output:
        return []

    matches: list[GrepMatch] = []
    for line in output.split("\n"):
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        try:
            line_number = int(parts[1])
        except ValueError:
            continue
        matches.append({"path": parts[0], "line": line_number, "text": parts[2]})

    return matches
