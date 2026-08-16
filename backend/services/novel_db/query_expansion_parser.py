"""Query Expansion応答を正規化する純粋parser。"""

from __future__ import annotations


def parse_expansions(response: str, *, target_n: int) -> list[str]:
    """LLM応答から短い検索クエリを最大 ``target_n`` 件抽出する。"""
    if not response:
        return []
    out: list[str] = []
    for raw_line in response.split("\n"):
        line = normalize_expansion_line(raw_line)
        if not line or len(line) > 60:
            continue
        out.append(line)
        if len(out) >= target_n:
            break
    return out


def normalize_expansion_line(raw_line: str) -> str:
    """1行分の番号・箇条書き・label・引用符を除去する。"""
    line = _strip_numbering(raw_line.strip())
    while line and line[0] in "-・*>＞→»→ 　":
        line = line[1:].lstrip()
    line = _strip_label(line)
    return line.strip("「」『』\"'")


def _strip_numbering(line: str) -> str:
    if len(line) >= 2 and line[0].isdigit() and line[1] in ".．:：、 ":
        return line[2:].lstrip()
    if not line or not line[0].isdigit():
        return line
    for index, character in enumerate(line):
        if not (character.isdigit() or character in ".．:：、 "):
            return line[index:].lstrip()
    return ""


def _strip_label(line: str) -> str:
    for label in ("検索クエリ", "クエリ", "Query", "query"):
        for separator in (":", "：", " "):
            prefix = label + separator
            if line.startswith(prefix):
                return line[len(prefix) :].lstrip()
    return line
