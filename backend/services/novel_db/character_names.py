"""pages.main_characters に保存されたキャラクター名の共通パーサー。"""

from __future__ import annotations

NAME_MAX_LENGTH = 30


def parse_character_names(raw: str | None) -> list[str]:
    """区切り・括弧の表記揺れを吸収し、重複のない名前一覧を返す。"""
    if not raw:
        return []

    text = raw.replace("、", ",").replace("・", ",")
    names: list[str] = []
    seen: set[str] = set()
    for part in text.split(","):
        name = part.strip().strip("「」『』\"'.。 ")
        if not name or len(name) > NAME_MAX_LENGTH or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names
