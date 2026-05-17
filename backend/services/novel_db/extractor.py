"""ページ単位テキスト抽出。

- PDF モード: PyMuPDF で縦書きブロックを連結（既存書籍との後方互換用）
- 画像モード: ocr_worker.py を common/ocr/venv の Python でサブプロセス実行（§5.1.1）

詳細は docs/03_詳細設計/小説テキスト検索・RAG機能_バックエンド設計.md §5.1。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import TypedDict

import fitz

_NEWLINE_RE = re.compile(r"\n+")

_OCR_VENV_PYTHON = os.environ.get(
    "OCR_PYTHON",
    r"D:\61.tool\common\ocr\venv\Scripts\python.exe",
)
_OCR_WORKER_SCRIPT = Path(__file__).parent / "ocr_worker.py"


class PageText(TypedDict):
    page_no: int        # 1-indexed
    full_text: str
    char_count: int


def run_ocr_subprocess(images_dirs: list[Path]) -> Iterator[tuple[str, list[PageText]]]:
    """yomitoku OCR を common/ocr/venv で subprocess 実行し、書籍ごとに (book_name, pages) を yield する。

    yomitoku は 1 度だけ初期化して全書籍を連続処理する。
    stderr は backend の stdout に流れる（GPU/モデルロードログが見える）。
    """
    cmd = [_OCR_VENV_PYTHON, str(_OCR_WORKER_SCRIPT)] + [str(d) for d in images_dirs]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8", env=env)
    assert proc.stdout is not None

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        book_name: str = data["book_name"]
        if "error" in data:
            raise RuntimeError(f"OCR worker error for '{book_name}': {data['error']}")
        yield book_name, data["pages"]

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"OCR worker exited with code {proc.returncode}")


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
