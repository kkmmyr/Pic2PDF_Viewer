from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

_PAGE_FINGERPRINT_SIZE = (64, 64)
_PAGE_CHANGE_MEAN_THRESHOLD = 1.0
_LOCATION_FOOTER_PATTERN = re.compile(
    r"\bLocation\s+(\d+)\s+of\s+\d+\s*[•·]\s*(\d+)%",
    re.IGNORECASE,
)
_NOVEL_PAGE_FOOTER_PATTERN = re.compile(
    r"ページ\s*(\d+)\s*/\s*\d+\s*[•·]\s*(\d+)%",
)


class KindleControllerError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class BookIdentity:
    asin: str
    title: str
    title_normalized: str | None = None
    authors: tuple[str, ...] = ()
    series_name: str | None = None
    volume_number: float | None = None
    volume_label: str | None = None

    @classmethod
    def from_job(cls, job: dict) -> BookIdentity:
        raw = job.get("identity") or {}
        return cls(
            asin=str(raw.get("asin") or job["asin"]),
            title=str(raw.get("title") or job.get("title") or ""),
            title_normalized=raw.get("title_normalized"),
            authors=tuple(str(value) for value in raw.get("authors") or ()),
            series_name=raw.get("series_name"),
            volume_number=raw.get("volume_number"),
            volume_label=raw.get("volume_label"),
        )


@dataclass(frozen=True)
class BookCandidate:
    asin: str | None
    title: str
    authors: tuple[str, ...] = ()
    series_name: str | None = None
    volume_number: float | None = None
    volume_label: str | None = None
    card: object | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ControllerConfig:
    window_title: str = "Kindle"
    window_class_name: str = "Microsoft.UI.Windowing.Window"
    control_search_depth: int = 30
    control_timeout_seconds: float = 10.0
    screen_transition_seconds: float = 2.0
    download_timeout_seconds: float = 1800.0
    download_poll_seconds: float = 2.0
    download_stable_checks: int = 3
    reader_timeout_seconds: float = 30.0
    page_change_timeout_seconds: float = 5.0

    @property
    def content_root(self) -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise KindleControllerError(
                "kindle_ui_unavailable",
                "LOCALAPPDATA を取得できないためKindle保存先を確認できません",
            )
        return (
            Path(local_app_data)
            / "Packages"
            / "AMZNKindle.AmazonKindleReadingApp_m1sc522ngdk36"
            / "LocalState"
            / "Classic"
            / "Content"
        )


def normalize_identity_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def visual_frames_differ(left: Image.Image, right: Image.Image) -> bool:
    """読書領域の縮小画像を比較し、ページ内容が変化したか判定する。"""
    left_gray = left.convert("L").resize(_PAGE_FINGERPRINT_SIZE)
    right_gray = right.convert("L").resize(_PAGE_FINGERPRINT_SIZE)
    difference = ImageChops.difference(left_gray, right_gray)
    return ImageStat.Stat(difference).mean[0] >= _PAGE_CHANGE_MEAN_THRESHOLD


def footer_indicates_cover(source: str, footer_name: str | None) -> bool:
    """source別のKindle表紙ロケーション表示を判定する。"""
    if source not in {"comic", "novel"} or not footer_name:
        return False
    match = _LOCATION_FOOTER_PATTERN.search(footer_name)
    if match is None:
        return False
    location = int(match.group(1))
    progress = int(match.group(2))
    if progress != 0:
        return False
    if source == "novel":
        return location == 1
    return location in {1, 2}


def novel_footer_indicates_first_page(footer_name: str | None) -> bool:
    """リフロー小説の本文先頭ページ表示を判定する。"""
    if not footer_name:
        return False
    match = _NOVEL_PAGE_FOOTER_PATTERN.search(footer_name)
    return match is not None and int(match.group(1)) == 1 and int(match.group(2)) == 0


def footer_indicates_start(source: str, footer_name: str | None) -> bool:
    """直接遷移後のsource別開始表示を判定する。"""
    return footer_indicates_cover(
        source,
        footer_name,
    ) or (source == "novel" and novel_footer_indicates_first_page(footer_name))


def _same_optional_text(left: str | None, right: str | None) -> bool:
    return bool(left and right) and normalize_identity_text(
        left
    ) == normalize_identity_text(right)


def candidate_matches_identity(
    identity: BookIdentity,
    candidate: BookCandidate,
) -> bool:
    """ASINを優先し、ASINなしの場合だけ書誌の複合一致を許可する。"""
    if candidate.asin:
        return candidate.asin.casefold() == identity.asin.casefold()

    expected_titles = {
        normalize_identity_text(identity.title),
        normalize_identity_text(identity.title_normalized),
    }
    expected_titles.discard("")
    if normalize_identity_text(candidate.title) not in expected_titles:
        return False

    expected_authors = {
        normalize_identity_text(author) for author in identity.authors if author
    }
    candidate_authors = {
        normalize_identity_text(author) for author in candidate.authors if author
    }
    author_match = bool(expected_authors & candidate_authors)

    series_match = _same_optional_text(identity.series_name, candidate.series_name)
    volume_match = False
    if identity.volume_number is not None and candidate.volume_number is not None:
        volume_match = identity.volume_number == candidate.volume_number
    elif identity.volume_label and candidate.volume_label:
        volume_match = _same_optional_text(
            identity.volume_label, candidate.volume_label
        )

    return author_match or (series_match and volume_match)


def select_verified_candidate(
    identity: BookIdentity,
    candidates: Sequence[BookCandidate],
) -> BookCandidate:
    matches = [
        candidate
        for candidate in candidates
        if candidate_matches_identity(identity, candidate)
    ]
    if not matches:
        error_code = "book_not_found" if not candidates else "book_identity_unverified"
        raise KindleControllerError(
            error_code,
            "Kindleライブラリで対象書籍を一意に照合できませんでした",
        )
    if len(matches) > 1:
        raise KindleControllerError(
            "book_match_ambiguous",
            "Kindleライブラリで対象書籍の候補が複数見つかりました",
        )
    return matches[0]


def parse_card_name(name: str) -> tuple[str, tuple[str, ...]]:
    title, separator, raw_authors = name.partition(" by ")
    if not separator:
        return name.strip(), ()
    author_text = re.sub(r",\s*新規$", "", raw_authors).strip()
    authors = tuple(
        value.strip() for value in re.split(r"[;/]", author_text) if value.strip()
    )
    return title.strip(), authors
