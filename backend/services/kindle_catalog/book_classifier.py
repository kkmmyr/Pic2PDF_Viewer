"""Amazon ジャンルとタイトルから Kindle 書籍種別を分類する。"""

from __future__ import annotations

import re

_LIGHT_NOVEL_TERMS = ("ライトノベル", "ジュブナイル")
_COMIC_TERMS = ("コミック", "マンガ", "漫画", "まんが")
_NOVEL_TERMS = (
    "文学",
    "小説",
    "エンタメ",
    "ミステリ",
    "推理",
    "ホラー",
    "SF",
    "ファンタジー",
    "ロマンス",
    "BL",
    "やおい",
    "TL",
    "ティーンズラブ",
    "百合",
)
_OTHER_TERMS = (
    "ビジネス",
    "経済",
    "投資",
    "コンピュータ",
    "IT",
    "技術",
    "プログラミング",
    "資格",
    "教育",
    "学習",
    "語学",
    "科学",
    "医学",
    "料理",
    "趣味",
    "スポーツ",
    "旅行",
    "歴史",
    "哲学",
    "宗教",
    "政治",
    "法律",
    "社会",
)
_COMIC_TITLE_RE = re.compile(
    r"第\s*\d+(?:[〜～~]\s*\d+)?\s*[話巻冊集]|コミック第\s*\d+|vol\.\s*\d+",
    re.IGNORECASE,
)


def classify_book_type(genres: list[str], title: str) -> str | None:
    combined = " ".join(genres)
    if any(term in combined for term in _LIGHT_NOVEL_TERMS):
        return "novel"
    if any(term in combined for term in _COMIC_TERMS):
        return "comic"
    if any(term in combined for term in _NOVEL_TERMS):
        return "novel"
    if any(term in combined for term in _OTHER_TERMS):
        return "other"
    if _COMIC_TITLE_RE.search(title):
        return "comic"
    return None
