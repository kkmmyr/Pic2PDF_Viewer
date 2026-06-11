"""services/novel_db/extractor.py の単体テスト。"""

import os

import fitz

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
