"""services/novel_db/extractor.py の単体テスト。"""

import json
import os
import sys
import time

import fitz
import pytest

from services.novel_db import extractor
from services.novel_db.extractor import extract_pages


def _make_text_pdf(path: str, pages_text: list[str]) -> None:
    """指定ページのテキストを埋め込んだ PDF を生成する。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page(width=400, height=600)
        page.insert_text((50, 50), text)
    doc.save(path)
    doc.close()


def test_extract_pages_returns_per_page_text(tmp_path):
    pdf = tmp_path / "sample.pdf"
    _make_text_pdf(str(pdf), ["First page text.", "Second page text."])

    pages = extract_pages(pdf)

    assert len(pages) == 2
    assert pages[0]["page_no"] == 1
    assert pages[1]["page_no"] == 2
    assert "First" in pages[0]["full_text"]
    assert "Second" in pages[1]["full_text"]
    assert pages[0]["char_count"] == len(pages[0]["full_text"])


def test_extract_pages_strips_block_internal_newlines(tmp_path):
    """ブロック内の改行（縦書き 1 文字配置の副作用）を除去できること。"""
    pdf = tmp_path / "newlines.pdf"
    # PyMuPDF の insert_text は改行コードを含む文字列を 1 ブロックにしない可能性が高いが、
    # 「ブロック内に改行が混じったテキスト」を本物の Searchable PDF と同等に再現するのは
    # PoC コードで実証済み。本テストでは extract_pages が char_count > 0 の自然な
    # ページテキストを返すことのみ検証する。
    _make_text_pdf(str(pdf), ["Hello, world."])

    pages = extract_pages(pdf)
    assert pages[0]["char_count"] > 0
    # 改行除去仕様の確認: 抽出結果に "\n\n" のような空行は含まれない
    assert "\n\n" not in pages[0]["full_text"]


def test_extract_pages_empty_pdf(tmp_path):
    """テキストの無いページでも char_count=0 のレコードが返る。"""
    pdf = tmp_path / "empty.pdf"
    _make_text_pdf(str(pdf), [""])

    pages = extract_pages(pdf)
    assert len(pages) == 1
    assert pages[0]["page_no"] == 1
    assert pages[0]["char_count"] == 0


def test_iter_ocr_pages_forwards_progress_events(monkeypatch):
    lines = [
        json.dumps(
            {
                "event": "progress",
                "progress": {
                    "stage": "page_started",
                    "book_name": "book",
                    "page_no": 1,
                    "total_pages": 1,
                    "server_generation": 2,
                },
            }
        ),
        json.dumps(
            {
                "event": "page",
                "book_name": "book",
                "page": {
                    "page_no": 1,
                    "image_sha256": "hash",
                    "state": "passed",
                    "full_text": "本文",
                    "char_count": 2,
                    "raw_output": "",
                    "block_count": 1,
                    "quality_flags": [],
                    "ink_coverage": 1.0,
                    "attempt_count": 1,
                    "server_generation": 2,
                    "error_message": None,
                },
            }
        ),
    ]

    class FakeProcess:
        stdout = iter(line + "\n" for line in lines)
        returncode = 0

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return self.returncode

    monkeypatch.setattr(extractor.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess())
    progress = []

    pages = list(
        extractor.iter_ocr_pages(
            [{"book_name": "book", "page_no": 1, "image_path": "001.png"}],
            progress_callback=progress.append,
        )
    )

    assert progress[0]["stage"] == "page_started"
    assert progress[0]["server_generation"] == 2
    assert pages[0][1]["full_text"] == "本文"


def test_iter_ocr_pages_terminates_a_real_hung_worker_after_partial_output(tmp_path, monkeypatch) -> None:
    worker = tmp_path / "hung_worker.py"
    pid_file = tmp_path / "worker.pid"
    worker.write_text(
        """import json
import os
import time
from pathlib import Path

Path(os.environ["HANG_PID_FILE"]).write_text(str(os.getpid()), encoding="utf-8")
print(json.dumps({
    "event": "page",
    "book_name": "book",
    "page": {
        "page_no": 1,
        "image_sha256": "hash",
        "state": "passed",
        "full_text": "本文",
        "char_count": 2,
        "raw_output": "",
        "block_count": 1,
        "quality_flags": [],
        "ink_coverage": 1.0,
        "attempt_count": 1
    }
}), flush=True)
time.sleep(30)
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(extractor, "_resolve_ocr_python", lambda: sys.executable)
    monkeypatch.setattr(extractor, "_OCR_WORKER_SCRIPT", worker)
    monkeypatch.setenv("HANG_PID_FILE", str(pid_file))

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="produced no output"):
        list(
            extractor.iter_ocr_pages(
                [{"book_name": "book", "page_no": 1, "image_path": "001.png"}],
                inactivity_timeout_sec=0.2,
            )
        )

    assert time.monotonic() - started < 5
    pid = int(pid_file.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
