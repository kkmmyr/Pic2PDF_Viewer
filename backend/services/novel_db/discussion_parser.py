"""読書会plan・turn markerの純粋parser。"""

from __future__ import annotations

import json
import re

TURN_RE = re.compile(r"\[([AB])[\]\>）\)]?\s*[:：]")
SEGMENT_RE = re.compile(r"\[S[:：]\s*([a-z0-9_]+)\s*[\]\>]?")


def parse_turns_from_text(text: str) -> list[tuple[str, str]]:
    cleaned = SEGMENT_RE.sub("", text)
    parts = TURN_RE.split(cleaned)
    return [
        (parts[index], parts[index + 1].strip()) for index in range(1, len(parts) - 1, 2) if parts[index + 1].strip()
    ]


def extract_plan_json(text: str) -> dict[str, object]:
    cleaned = re.sub(r"```(?:json)?", "", text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("構成メモの JSON が見つかりません")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("構成メモのJSON rootはobjectである必要があります")
    return payload


def validate_plan(plan: dict[str, object]) -> None:
    themes = plan.get("themes")
    if not isinstance(themes, list) or len(themes) != 2:
        raise ValueError("構成メモの themes は 2 件必要です")
    for theme in themes:
        if not isinstance(theme, dict) or not theme.get("title") or not theme.get("question"):
            raise ValueError("構成メモの themes に title / question がありません")
    stances = plan.get("stances")
    if not isinstance(stances, dict) or not stances.get("a") or not stances.get("b"):
        raise ValueError("構成メモの stances に a / b がありません")
    cards = plan.get("cards")
    if not isinstance(cards, list) or len(cards) < 1:
        raise ValueError("構成メモの cards は 1 件以上必要です")
