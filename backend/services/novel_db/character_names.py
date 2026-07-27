"""pages.main_characters に保存されたキャラクター名の共通パーサー。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

NAME_MAX_LENGTH = 30

_WRAPPERS = "「」『』\"'.。 "
_PARENTHETICAL_SUFFIX_RE = re.compile(r"\s*[（(][^）)]{1,30}[）)]\s*$")
_TITLE_PREFIX_RE = re.compile(
    r"^(?:第[0-9一二三四五六七八九十百]+皇子|皇太子|皇女|皇子|皇帝|皇后|"
    r"国王|王妃|公爵|侯爵|伯爵|子爵|男爵)\s*"
)
_HONORIFIC_SUFFIX_RE = re.compile(r"(?:さん|さま|様|殿|君|くん|ちゃん|陛下|閣下|嬢)$")
_ANONYMOUS_ROLES = frozenset(
    {
        "皇帝",
        "皇后",
        "皇太子",
        "皇子",
        "皇女",
        "国王",
        "王妃",
        "武官",
        "文官",
        "官吏",
        "女官",
        "女官長",
        "侍女",
        "兵",
        "兵士",
        "護衛",
        "宦官",
        "側近",
        "店主",
        "主人",
        "母",
        "父",
        "兄",
        "姉",
        "弟",
        "妹",
    }
)
_ANONYMOUS_ROLE_PHRASE_RE = re.compile(r"^.{1,12}(?:国|宮|家|軍)の(?:皇帝|皇后|国王|王妃|武官|文官|官吏|女官|兵|護衛)$")
_CJK_NAME_RE = re.compile(r"^[\u3400-\u9fff々〆ヵヶ]{3,5}$")


@dataclass(frozen=True)
class NormalizedCharacter:
    """Canonical character entry with source aliases retained for evidence lookup."""

    name: str
    summary: str
    aliases: tuple[str, ...]


def normalize_character_name(raw: str | None) -> str | None:
    """Normalize a named character and reject anonymous role-only labels."""
    if not raw:
        return None

    name = raw.strip().strip(_WRAPPERS)
    name = _PARENTHETICAL_SUFFIX_RE.sub("", name).strip()
    name = _TITLE_PREFIX_RE.sub("", name).strip()
    while True:
        stripped = _HONORIFIC_SUFFIX_RE.sub("", name).strip()
        if stripped == name:
            break
        name = stripped

    if not name or len(name) > NAME_MAX_LENGTH or name in _ANONYMOUS_ROLES or _ANONYMOUS_ROLE_PHRASE_RE.fullmatch(name):
        return None
    return name


def parse_character_names(raw: str | None) -> list[str]:
    """区切り・括弧の表記揺れを吸収し、重複のない名前一覧を返す。"""
    if not raw:
        return []

    text = raw.replace("、", ",")
    names: list[str] = []
    seen: set[str] = set()
    for part in text.split(","):
        name = normalize_character_name(part)
        if name is None or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def normalize_character_entries(entries: Mapping[str, str]) -> list[NormalizedCharacter]:
    """Normalize and merge LLM-generated character dictionary entries."""
    merged: dict[str, dict[str, list[str]]] = {}
    for raw_name, raw_summary in entries.items():
        name = normalize_character_name(raw_name)
        summary = str(raw_summary or "").strip()
        if name is None or not summary:
            continue
        bucket = merged.setdefault(name, {"summaries": [], "aliases": []})
        if summary not in bucket["summaries"]:
            bucket["summaries"].append(summary)
        alias = str(raw_name).strip().strip(_WRAPPERS)
        if alias and alias not in bucket["aliases"]:
            bucket["aliases"].append(alias)
        if name not in bucket["aliases"]:
            bucket["aliases"].append(name)

    return [
        NormalizedCharacter(
            name=name,
            summary="\n".join(values["summaries"]),
            aliases=tuple(values["aliases"]),
        )
        for name, values in merged.items()
    ]


def derive_character_evidence_aliases(name: str) -> tuple[str, ...]:
    """Return conservative short forms used only when repeated page evidence exists."""
    if _CJK_NAME_RE.fullmatch(name):
        return (name[1:],)
    if "・" in name:
        first_component = name.split("・", 1)[0].strip()
        if len(first_component) >= 4:
            return (first_component,)
    return ()
