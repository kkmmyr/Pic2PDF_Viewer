"""人物関係LLM応答の純粋parser。"""

from __future__ import annotations

import json


def parse_relation_response(response: str) -> list[tuple[str, str, str]]:
    raw = _unwrap_code_fence(response)
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    results: list[tuple[str, str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        left = str(item.get("char_a", "")).strip()
        right = str(item.get("char_b", "")).strip()
        relation = str(item.get("relation", "")).strip()[:20]
        if left and right and relation and left != right:
            results.append((left, right, relation))
    return results


def _unwrap_code_fence(response: str) -> str:
    if "```" not in response:
        return response
    lines: list[str] = []
    inside = False
    for line in response.splitlines():
        if line.startswith("```"):
            inside = not inside
        elif inside:
            lines.append(line)
    return "\n".join(lines)
