"""Codex hook payload helpers shared by the shell hooks."""

from __future__ import annotations

import json
import re
import sys


def _payload() -> dict[str, object]:
    try:
        value = json.loads(sys.stdin.read().lstrip("\ufeff"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _tool_input(payload: dict[str, object]) -> dict[str, object]:
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}


def _paths(tool_input: dict[str, object]) -> list[str]:
    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path:
        return [file_path]

    command = tool_input.get("command")
    if not isinstance(command, str):
        return []

    seen: set[str] = set()
    paths: list[str] = []
    pattern = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$")
    for line in command.splitlines():
        match = pattern.match(line)
        if match and match.group(1) not in seen:
            seen.add(match.group(1))
            paths.append(match.group(1))
    return paths


def _added_text(tool_input: dict[str, object]) -> str:
    new_string = tool_input.get("new_string")
    if isinstance(new_string, str):
        return new_string

    command = tool_input.get("command")
    if not isinstance(command, str):
        return ""
    return "\n".join(
        line[1:]
        for line in command.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def main() -> int:
    if len(sys.argv) != 2:
        return 2

    tool_input = _tool_input(_payload())
    mode = sys.argv[1]
    if mode == "paths":
        sys.stdout.write("\n".join(_paths(tool_input)))
    elif mode == "added-text":
        sys.stdout.write(_added_text(tool_input))
    elif mode == "command":
        command = tool_input.get("command")
        if isinstance(command, str):
            sys.stdout.write(command)
    else:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
