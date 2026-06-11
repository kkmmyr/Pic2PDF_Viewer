"""Amazon タイトル正規化ユーティリティ。

巻番号・レーベル・ノイズ記号を除去し、書籍シリーズのベースタイトルを返す。
参照: D:/61.tool/kindle購入履歴/app/backend/src/kindle_viewer/utils/title.py
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# フィルター定数
# ---------------------------------------------------------------------------
_NON_MEANINGFUL = {"not applicable", "not available", ""}


def is_meaningful(v: str | None) -> bool:
    """値が意味のある文字列かどうかを返す。"""
    return bool(v) and v.strip().lower() not in _NON_MEANINGFUL


# ---------------------------------------------------------------------------
# タイトル正規化（巻番号・レーベル・ノイズ除去）
# ---------------------------------------------------------------------------
_BRACKET_PREFIX = re.compile(r"^\s*[【\[][^】\]]{1,40}[】\]]\s*")
_ANY_KAKKO_NOISE = re.compile(r"【[^】]{1,40}】")
_SLASH_NOISE = re.compile(r"[／/][^／/【\[（(]{1,20}(?:付き?|つき|込み)\s*$")
_LABEL_PATTERN = re.compile(r"[（(][^）)]{1,30}[）)]\s*$")
_VOLUME_PATTERNS = [
    re.compile(r"\s*第?\s*\d{1,3}\s*巻\s*$"),
    re.compile(r"\s*\d{1,3}\s*巻\s*$"),
    re.compile(r"\s*[（(]\s*\d{1,3}\s*[）)]\s*$"),
    re.compile(r"\s*[（(]\s*[0-9]{1,3}\s*[）)]\s*$"),
    re.compile(r"\s+[Vv][Oo][Ll]\.?\s*\d{1,3}\s*$"),
    re.compile(r"\s+[Nn][Oo]\.?\s*\d{1,3}\s*$"),
    re.compile(r"\s+\d{1,3}\s*$"),
    re.compile(r"\s*[:：]\s*\d{1,3}\s*$"),
]


def normalize_title(title: str) -> str:
    """タイトルから巻番号・レーベル・ノイズを除去した正規化文字列を返す。"""
    t = unicodedata.normalize("NFKC", title or "").strip()
    t = _BRACKET_PREFIX.sub("", t)
    t = _ANY_KAKKO_NOISE.sub(" ", t)
    t = _SLASH_NOISE.sub("", t).strip()
    t = re.sub(r"[ \t]+", " ", t).strip()

    base = _LABEL_PATTERN.sub("", t).strip()
    for _ in range(3):
        prev = base
        for pat in _VOLUME_PATTERNS:
            base = pat.sub("", base).strip()
        if base == prev:
            break

    base = re.sub(r"[ 　]*[:：\-－—]\s*$", "", base).strip()
    return base or t
