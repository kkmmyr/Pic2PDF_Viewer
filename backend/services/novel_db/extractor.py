"""ページ単位テキスト抽出。

- PDF モード: PyMuPDF で縦書きブロックを連結（既存書籍との後方互換用）
- 画像モード: OCR エンジン（yomitoku）で images/*.png から抽出（§4.2 新規）

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.1。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

import fitz

# D:\61.tool\common\ocr の ocr_engine.py を参照（sys.path 追加方式）
_COMMON_OCR_PATH = r"D:\61.tool\common\ocr"

_NEWLINE_RE = re.compile(r"\n+")


class PageText(TypedDict):
    page_no: int        # 1-indexed
    full_text: str
    char_count: int


def extract_pages_from_images(images_dir: Path, engine: object) -> list[PageText]:
    """画像ディレクトリから OCR エンジンでページテキストを抽出する（§4.2）。

    `engine` は `D:\\61.tool\\common\\ocr\\ocr_engine.py` の
    `BaseOCREngine` サブクラス（初期化済み）。呼び出し側が 1 度だけ初期化して渡す。
    """
    import cv2  # type: ignore[import-untyped]  # GPU 環境のみ利用可

    pages: list[PageText] = []
    for img_path in sorted(images_dir.glob("*.png")):
        try:
            page_no = int(img_path.stem)
        except ValueError:
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        results = engine.extract_text(img)  # type: ignore[union-attr]
        full_text = "\n".join(r["text"] for r in results if r.get("text", "").strip())
        pages.append({
            "page_no": page_no,
            "full_text": full_text,
            "char_count": len(full_text),
        })
    return pages


def load_ocr_engine() -> object:
    """yomitoku OCR エンジンを初期化して返す。

    `D:\\61.tool\\common\\ocr` を sys.path に追加して `ocr_engine.py` を import する。
    GPU 環境（CUDA）前提。複数書籍を処理する場合は 1 度だけ呼ぶこと。
    """
    import sys

    if _COMMON_OCR_PATH not in sys.path:
        sys.path.insert(0, _COMMON_OCR_PATH)

    from ocr_engine import get_ocr_engine  # type: ignore[import-not-found]

    engine = get_ocr_engine("yomitoku")
    engine.initialize()
    return engine


def extract_pages(pdf_path: str | Path) -> list[PageText]:
    pages: list[PageText] = []
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc):
            blocks = page.get_text("blocks")
            parts: list[str] = []
            for b in blocks:
                # blocks タプルの 5 要素目がテキスト本体（PyMuPDF API）
                cleaned = _NEWLINE_RE.sub("", b[4]).strip()
                if cleaned:
                    parts.append(cleaned)
            full_text = "\n".join(parts)
            pages.append({
                "page_no": i + 1,
                "full_text": full_text,
                "char_count": len(full_text),
            })
    return pages
